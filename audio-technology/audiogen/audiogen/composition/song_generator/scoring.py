# composition/song_generator/scoring.py
# best-of-k candidate scoring: slices a song's flat event list back into
# per-section windows, evaluates each section, and combines section-level
# metrics with song-level heuristics (register lift, cadence landings, blueprint
# adherence, optional audit-aligned rerank blend) into one scalar score.

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from audiogen_core.config import resolve_config
from data.music_data import EMOTION_BY_NAME

from ..policies import ArrangementPolicy
from .models import SongRender


class ScoringMixin:
    """Candidate-song scoring used by `generate_song_best_of_k`."""

    @staticmethod
    def _slice_section_events(events: Sequence[Tuple], start_beat: float, end_beat: float) -> List[Tuple]:
        out: List[Tuple] = []
        for ev in events:
            if not ev or len(ev) != 6:
                continue
            st = float(ev[3])
            if start_beat - 1e-9 <= st < end_beat - 1e-9:
                ch, midi, vel, _start, dur, notes = ev
                out.append((ch, midi, vel, st - start_beat, dur, list(notes)))
        return out

    @staticmethod
    def _log_rerank_candidate_row(
        *,
        emotion: str,
        seed: int,
        candidate_index: int,
        score: float,
        details: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        pass

    @classmethod
    def _score_candidate_song(
        cls,
        song: SongRender,
        *,
        arrangement_form: str,
    ) -> Tuple[float, Dict[str, Any]]:
        from composition.evaluation import evaluate_song, score_song

        total_bars = int(sum(int(s.bars) for s in song.sections)) if song.sections else None
        # Events are expected in beats, but some tests construct SongRender events in "bar units"
        # (i.e. timestamps run ~0..total_bars). Detect and adapt so scoring is robust.
        bpb = 4.0
        try:
            if song.events and total_bars is not None and total_bars > 0:
                max_t = max(float(ev[3]) + float(ev[4]) for ev in song.events if ev and len(ev) == 6)
                # If the timeline is ~0..total_bars, treat 1 "time unit" as 1 bar (bpb=1.0).
                if max_t <= float(total_bars) * 1.25:
                    bpb = 1.0
        except Exception:
            bpb = 4.0
        base_score, details = score_song(song.events, beats_per_bar=float(bpb), bars=total_bars)

        seq = ArrangementPolicy._FORM_SEQUENCES.get(arrangement_form) or ArrangementPolicy._FORM_SEQUENCES["default"]
        section_metrics: List[Dict[str, Any]] = []
        beat_offset = 0.0
        verse_like_lead: List[float] = []
        chorus_like_lead: List[float] = []
        verse_like_arp: List[float] = []
        chorus_like_arp: List[float] = []

        for idx, spec in enumerate(song.sections):
            role = seq[idx] if idx < len(seq) else seq[-1]
            end = beat_offset + float(spec.bars) * float(bpb)
            section_events = cls._slice_section_events(song.events, beat_offset, end)
            metrics = evaluate_song(section_events, beats_per_bar=float(bpb), bars=int(spec.bars)).to_dict()
            metrics["role"] = role
            metrics["emotion_name"] = spec.emotion_name
            # Extra per-section signals for reranking.
            try:
                lead_pitches = []
                for ev in section_events:
                    if not ev or len(ev) != 6:
                        continue
                    if int(ev[0]) != 2:
                        continue
                    notes = ev[5]
                    if isinstance(notes, list) and notes and isinstance(notes[0], int):
                        lead_pitches.append(int(notes[0]))
                if lead_pitches:
                    xs = sorted(int(x) for x in lead_pitches)
                    k = int(round(0.95 * (len(xs) - 1)))
                    k = max(0, min(len(xs) - 1, k))
                    metrics["lead_pitch_p95"] = int(xs[k])
                    metrics["lead_pitch_max"] = int(max(xs))
                else:
                    metrics["lead_pitch_p95"] = 0
                    metrics["lead_pitch_max"] = 0
            except Exception:
                metrics["lead_pitch_p95"] = 0
                metrics["lead_pitch_max"] = 0

            # Cadence landing accuracy (phrase ends): does the last lead note land as intended?
            try:
                phrase_len = 4
                # Use the inferred timeline units.
                eps = 0.65
                tonic_pc = int(spec.root_note) % 12
                role_lc = str(role or "").lower()
                hits = 0
                total = 0
                # Precompute chord pcs by bar from chord events.
                chord_pcs_by_bar: List[set] = [set() for _ in range(int(spec.bars))]
                for ev in section_events:
                    if not ev or len(ev) != 6:
                        continue
                    if int(ev[0]) != 1:
                        continue
                    st = float(ev[3])
                    bar = int(st // bpb)
                    if 0 <= bar < len(chord_pcs_by_bar):
                        notes = ev[5]
                        if isinstance(notes, list) and notes:
                            for n in notes:
                                if isinstance(n, int) and int(n) > 0:
                                    chord_pcs_by_bar[bar].add(int(n) % 12)
                for bar in range(int(spec.bars)):
                    is_phrase_end = ((bar + 1) % phrase_len) == 0
                    if not is_phrase_end:
                        continue
                    pcs = chord_pcs_by_bar[bar]
                    if not pcs:
                        continue
                    bar_end = float((bar + 1) * float(bpb))
                    # Find last lead note reaching into final eps beats.
                    last_m = None
                    last_st = -1.0
                    for ev in section_events:
                        if not ev or len(ev) != 6 or int(ev[0]) != 2:
                            continue
                        st = float(ev[3])
                        dur = float(ev[4])
                        if not (float(bar * float(bpb)) - 1e-6 <= st < float((bar + 1) * float(bpb)) + 1e-6):
                            continue
                        if st + dur < float(bar_end) - float(eps):
                            continue
                        if st >= last_st:
                            last_st = st
                            notes = ev[5]
                            if isinstance(notes, list) and notes and isinstance(notes[0], int):
                                last_m = int(notes[0])
                    if last_m is None:
                        continue
                    total += 1
                    pc = int(last_m) % 12
                    if role_lc in {"pre_chorus"}:
                        # "Open": avoid tonic if possible.
                        ok = bool(int(pc) != int(tonic_pc))
                    elif role_lc in {"b", "tag", "outro"}:
                        # "Closed": prefer tonic when available.
                        ok = bool(int(pc) == int(tonic_pc)) if int(tonic_pc) in pcs else bool(int(pc) in pcs)
                    else:
                        ok = bool(int(pc) in pcs)
                    if ok:
                        hits += 1
                metrics["cadence_landing_hit_rate"] = float(hits / max(1, total)) if total else 0.0
            except Exception:
                metrics["cadence_landing_hit_rate"] = 0.0
            section_metrics.append(metrics)
            if role in {"a", "intro"}:
                verse_like_lead.append(float(metrics.get("lead_activity", 0.0)))
                verse_like_arp.append(float(metrics.get("arp_activity", 0.0)))
            if role in {"b", "tag"}:
                chorus_like_lead.append(float(metrics.get("lead_activity", 0.0)))
                chorus_like_arp.append(float(metrics.get("arp_activity", 0.0)))

            # Opening signatures: penalize excessive identical 1-bar openings between
            # structurally different roles (verse vs chorus), which reads as “loop”.
            try:
                bar0_end = float(bpb)
                chord_pcs = set()
                lead_open = []
                for ev in section_events:
                    if not ev or len(ev) != 6:
                        continue
                    ch, midi, _vel, st, _dur, notes = ev
                    st = float(st)
                    if not (0.0 <= st < bar0_end - 1e-6):
                        continue
                    if int(ch) == 1:
                        if isinstance(notes, list) and notes:
                            for n in notes:
                                if isinstance(n, int):
                                    chord_pcs.add(int(n) % 12)
                        else:
                            try:
                                if isinstance(midi, int) and int(midi) > 0:
                                    chord_pcs.add(int(midi) % 12)
                            except Exception:
                                pass
                    if int(ch) == 2:
                        try:
                            if isinstance(notes, list) and notes and isinstance(notes[0], int):
                                lead_open.append(int(notes[0]))
                        except Exception:
                            pass
                sig = (tuple(sorted(chord_pcs))[:5], tuple(lead_open[:3]))
                metrics["opening_sig"] = sig
            except Exception:
                pass
            beat_offset = end

        unique_emotions = len({str(s.emotion_name).lower() for s in song.sections})
        unique_scale_shapes = len(
            {
                tuple(int(iv) % 12 for iv in EMOTION_BY_NAME.get(str(s.emotion_name).lower(), EMOTION_BY_NAME[song.sections[0].emotion_name.lower()]).scale_intervals)
                for s in song.sections
            }
        ) if song.sections else 0

        score = float(base_score)
        score += 0.05 * max(0, unique_emotions - 1)
        score += 0.04 * max(0, unique_scale_shapes - 1)

        verse_lead = (sum(verse_like_lead) / len(verse_like_lead)) if verse_like_lead else 0.0
        chorus_lead = (sum(chorus_like_lead) / len(chorus_like_lead)) if chorus_like_lead else 0.0
        verse_arp = (sum(verse_like_arp) / len(verse_like_arp)) if verse_like_arp else 0.0
        chorus_arp = (sum(chorus_like_arp) / len(chorus_like_arp)) if chorus_like_arp else 0.0

        if chorus_like_lead:
            score += 0.30 * max(0.0, chorus_lead - verse_lead)
        if chorus_like_arp:
            score += 0.18 * max(0.0, chorus_arp - verse_arp)

        if section_metrics:
            lead_span = max(float(m.get("lead_activity", 0.0)) for m in section_metrics) - min(float(m.get("lead_activity", 0.0)) for m in section_metrics)
            chord_span = max(float(m.get("chord_change_rate_per_bar", 0.0)) for m in section_metrics) - min(float(m.get("chord_change_rate_per_bar", 0.0)) for m in section_metrics)
            score += 0.22 * max(0.0, lead_span - 0.08)
            score += 0.12 * max(0.0, chord_span - 0.10)

            final_metrics = section_metrics[-1]
            peak_lead = max(float(m.get("lead_activity", 0.0)) for m in section_metrics)
            final_lead = float(final_metrics.get("lead_activity", 0.0))
            score += 0.10 * max(0.0, peak_lead - final_lead)

            # Penalize harshness and masking (these correlate strongly with “random” feel).
            try:
                avg_rep = sum(float(m.get("lead_repeat_frac", 0.0)) for m in section_metrics) / float(len(section_metrics))
                score -= 0.18 * max(0.0, float(avg_rep) - 0.18)
            except Exception:
                pass
            try:
                avg_ov = sum(float(m.get("lead_arp_overlap", 0.0)) for m in section_metrics) / float(len(section_metrics))
                score -= 0.14 * max(0.0, float(avg_ov) - 0.45)
            except Exception:
                pass
            try:
                avg_ch_rep = sum(float(m.get("chord_repeat_frac", 0.0)) for m in section_metrics) / float(len(section_metrics))
                score -= 0.10 * max(0.0, float(avg_ch_rep) - 0.35)
            except Exception:
                pass

            # Role-contrast: verse vs chorus should not share the exact same opening signature too often.
            try:
                a_sigs = [m.get("opening_sig") for m in section_metrics if m.get("role") in {"a", "intro"} and m.get("opening_sig") is not None]
                b_sigs = [m.get("opening_sig") for m in section_metrics if m.get("role") in {"b", "tag"} and m.get("opening_sig") is not None]
                if a_sigs and b_sigs:
                    collisions = 0
                    for s in a_sigs:
                        if s in b_sigs:
                            collisions += 1
                    if collisions:
                        score -= 0.22 * float(collisions)
            except Exception:
                pass

            # New targets: register peak + cadence accuracy + modulation success.
            try:
                # Register peak: final chorus should be higher than verse (in p95).
                verse_p95 = [int(m.get("lead_pitch_p95", 0) or 0) for m in section_metrics if m.get("role") in {"a", "intro"}]
                chorus_p95 = [int(m.get("lead_pitch_p95", 0) or 0) for m in section_metrics if m.get("role") in {"b", "tag"}]
                if verse_p95 and chorus_p95:
                    v = max(verse_p95)
                    c = max(chorus_p95)
                    lift = int(c) - int(v)
                    # Reward meaningful lift, but don't overweight.
                    score += 0.06 * max(0.0, min(12.0, float(lift - 2)) / 10.0)
                    details["register_lift_semitones"] = int(lift)
            except Exception:
                pass
            try:
                # Cadence landing accuracy: prefer higher hit rate in chorus/outro, avoid tonic in pre.
                cad_rates = [float(m.get("cadence_landing_hit_rate", 0.0) or 0.0) for m in section_metrics]
                if cad_rates:
                    score += 0.08 * max(0.0, (sum(cad_rates) / len(cad_rates)) - 0.55)
            except Exception:
                pass
            try:
                # Modulation success: small positive lift into final chorus is a plus.
                md = dict(song.metadata or {})
                if bool(md.get("modulation_lift_applied")):
                    d = int(md.get("modulation_lift_semitones", 0) or 0)
                    if 1 <= d <= 3:
                        score += 0.05
                    elif d >= 4:
                        score += 0.02
                    elif d <= -1:
                        score -= 0.03
            except Exception:
                pass
            # Song blueprint adherence: reward candidates that follow planned narrative.
            bp_weight = resolve_config("composition", "whole_song_rerank_blueprint_weight", 0.55, float)
            bp_on = resolve_config("composition", "whole_song_rerank_enabled", True, bool)
            if bp_on and bp_weight > 1e-6:
                try:
                    md = dict(song.metadata or {})
                    bp = dict(md.get("song_blueprint", {}) or {})
                    expected_stages = list(bp.get("motif_stages", []) or [])
                    expected_cad = list(bp.get("cadence_styles", []) or [])
                    if expected_stages or expected_cad:
                        s_bonus = 0.0
                        for i, m in enumerate(list(section_metrics)):
                            stage = str(expected_stages[i] if i < len(expected_stages) else "")
                            cad = str(expected_cad[i] if i < len(expected_cad) else "")
                            lead_a = float(m.get("lead_activity", 0.0) or 0.0)
                            arp_a = float(m.get("arp_activity", 0.0) or 0.0)
                            cad_hit = float(m.get("cadence_landing_hit_rate", 0.0) or 0.0)
                            motif_like = 0.5 * float(lead_a) + 0.5 * float(arp_a)
                            if stage in {"introduce", "state"}:
                                # Clear motif statements should not be hyper-busy.
                                s_bonus += 0.05 * max(0.0, 0.70 - abs(float(motif_like) - 0.55))
                            elif stage in {"build", "develop"}:
                                s_bonus += 0.05 * max(0.0, float(motif_like) - 0.45)
                            elif stage in {"restate", "payoff"}:
                                s_bonus += 0.07 * max(0.0, float(motif_like) - 0.50)
                            elif stage in {"fragment"}:
                                s_bonus += 0.04 * max(0.0, 0.60 - float(lead_a))
                            if cad in {"closed", "authentic"}:
                                s_bonus += 0.08 * max(0.0, float(cad_hit) - 0.55)
                            elif cad in {"open"}:
                                s_bonus += 0.04 * max(0.0, 0.70 - float(cad_hit))
                            elif cad in {"deceptive"}:
                                # Deceptive sections should avoid sounding fully closed.
                                s_bonus += 0.03 * max(0.0, 0.75 - float(cad_hit))
                        score += float(bp_weight) * float(s_bonus)
                        details["blueprint_adherence_bonus"] = float(s_bonus)
                except Exception:
                    pass

        details = dict(details)
        details["section_metrics"] = section_metrics
        details["section_emotion_variety"] = int(unique_emotions)
        details["section_scale_variety"] = int(unique_scale_shapes)
        details["verse_lead_activity"] = float(verse_lead)
        details["chorus_lead_activity"] = float(chorus_lead)
        details["verse_arp_activity"] = float(verse_arp)
        details["chorus_arp_activity"] = float(chorus_arp)
        details["score"] = float(score)

        audit_on = resolve_config("composition", "audit_aligned_rerank_enabled", False, bool)
        audit_w = resolve_config("composition", "audit_aligned_rerank_weight", 0.55, float)
        raw_rerank_model_path = resolve_config("composition", "song_rerank_model_path", '', str)
        if audit_on:
            try:
                from composition.audit_aligned_score import (
                    blend_rerank_scores,
                    enrich_rerank_details_from_song,
                )

                seq = ArrangementPolicy._FORM_SEQUENCES.get(arrangement_form) or ArrangementPolicy._FORM_SEQUENCES["default"]
                roles = [seq[i] if i < len(seq) else seq[-1] for i in range(len(song.sections))]
                sec_bars = [int(s.bars) for s in song.sections]
                details = enrich_rerank_details_from_song(
                    details,
                    events=list(song.events or []),
                    section_roles=roles,
                    section_bars=sec_bars,
                    metadata=dict(song.metadata or {}),
                    beats_per_bar=float(bpb),
                    bars=total_bars,
                )
                score, blend_meta = blend_rerank_scores(
                    float(score),
                    details,
                    weight=float(audit_w),
                    model_path=str(raw_rerank_model_path),
                )
                details.update(blend_meta)
                details["score"] = float(score)
                details["picked_by_audit_aligned_rerank"] = True
            except Exception:
                pass

        return float(score), details
