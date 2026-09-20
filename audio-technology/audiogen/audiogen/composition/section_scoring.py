from __future__ import annotations
from audiogen_core.config import resolve_config

import math
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from composition.evaluation import score_song


@dataclass(frozen=True)
class SectionScoreComponents:
    """
    Named deltas from `score_song` base through each scoring stage (structural path only).

    ``song_base`` is the raw output from ``score_song``; each ``*_adjustment`` is the
    score delta contributed by that stage (same units as ``SectionScore.score``).
    """

    song_base: float
    cadence_adjustment: float = 0.0
    arp_melody_compat_adjustment: float = 0.0
    melody_harmony_agreement_adjustment: float = 0.0
    lane_register_adjustment: float = 0.0
    density_curve_adjustment: float = 0.0
    breath_cadence_adjustment: float = 0.0
    pop_hook_adjustment: float = 0.0

    def structural_total(self) -> float:
        return (
            float(self.song_base)
            + float(self.cadence_adjustment)
            + float(self.arp_melody_compat_adjustment)
            + float(self.melody_harmony_agreement_adjustment)
            + float(self.lane_register_adjustment)
            + float(self.density_curve_adjustment)
            + float(self.breath_cadence_adjustment)
            + float(self.pop_hook_adjustment)
        )


@dataclass(frozen=True)
class SectionScore:
    """Aggregate section quality; ``score`` remains the scalar used for ranking."""

    score: float
    details: Dict[str, Any]
    components: Optional[SectionScoreComponents] = None


def _nearest_scale_degree(midi: int, *, root_note: int, scale_intervals: Sequence[int]) -> int:
    pcs = [int(x) % 12 for x in list(scale_intervals or [])]
    if not pcs:
        pcs = [0, 2, 4, 5, 7, 9, 11]
    root_pc = int(root_note) % 12
    rel = (int(midi) % 12 - int(root_pc)) % 12

    def _pc_dist(a: int, b: int) -> int:
        d = abs(int(a) - int(b)) % 12
        return int(min(d, 12 - d))

    best_i = 0
    best_d = 99
    for i, pc in enumerate(pcs):
        d = _pc_dist(int(rel), int(pc))
        if d < best_d:
            best_i = int(i)
            best_d = int(d)
    return int(best_i)


def melody_tokens_for_lyrical_score(
    events: Sequence[Sequence[Any]],
    *,
    emotion: Any,
    root_note: int,
) -> List[Tuple[int, float]]:
    scale = list(getattr(emotion, "scale_intervals", []) or [])
    rows: List[Tuple[float, float, int]] = []
    for ev in events:
        if not ev or len(ev) != 6:
            continue
        try:
            if int(ev[0]) != 2:
                continue
            st = float(ev[3])
            dur = float(ev[4])
            notes = ev[5]
            midi = int(notes[0]) if isinstance(notes, list) and notes else int(ev[1])
        except Exception:
            continue
        if dur <= 1e-9:
            continue
        rows.append((float(st), float(dur), int(midi)))
    rows.sort(key=lambda x: (float(x[0]), int(x[2])))
    tokens: List[Tuple[int, float]] = []
    prev_end: Optional[float] = None
    for st, dur, midi in rows:
        if prev_end is not None:
            gap = float(st) - float(prev_end)
            if gap >= 0.24:
                tokens.append((-1, float(min(4.0, gap))))
        deg = _nearest_scale_degree(int(midi), root_note=int(root_note), scale_intervals=scale)
        tokens.append((int(deg), float(max(0.125, min(4.0, dur)))))
        prev_end = max(float(prev_end or 0.0), float(st) + float(dur))
    return tokens


def sampler_musical_adjustment(
    *,
    base_score: float,
    events: Sequence[Sequence[Any]],
    emotion: Any,
    root_note: int,
    section_role: str,
    candidate_song_memory: Any,
    baseline_song_memory: Any,
) -> Tuple[float, Dict[str, Any]]:
    enabled = resolve_config("composition", "section_sampler_musical_rerank_enabled", True, bool)
    lyrical_w = resolve_config("composition", "section_sampler_lyrical_weight", 0.30, float)
    lyrical_target = resolve_config("composition", "section_sampler_lyrical_target", 0.58, float)
    repeat_w = resolve_config("composition", "section_sampler_harmony_repeat_penalty", 0.10, float)
    register_w = resolve_config("composition", "section_sampler_register_stasis_penalty", 0.06, float)
    novelty_on = resolve_config("composition", "section_sampler_novelty_enabled", False, bool)
    novelty_w = resolve_config("composition", "section_sampler_novelty_weight", 0.18, float)
    chord_novelty_w = resolve_config("composition", "section_sampler_chord_novelty_weight", 0.10, float)
    reg_novelty_w = resolve_config("composition", "section_sampler_register_novelty_weight", 0.08, float)
    reg_target = resolve_config("composition", "section_sampler_register_drift_target_semitones", 4.0, float)
    reg_sigma = resolve_config("composition", "section_sampler_register_drift_sigma_semitones", 3.0, float)

    details: Dict[str, Any] = {"sampler_base_score": float(base_score)}
    if not enabled:
        details["sampler_adjusted_score"] = float(base_score)
        details["sampler_musical_rerank_enabled"] = False
        return float(base_score), details

    score = float(base_score)
    role = str(section_role or "").strip().lower()
    lyrical_w = max(0.0, min(1.0, float(lyrical_w)))
    lyrical_target = max(0.0, min(1.0, float(lyrical_target)))
    repeat_w = max(0.0, min(0.5, float(repeat_w)))
    register_w = max(0.0, min(0.35, float(register_w)))
    novelty_w = max(0.0, min(0.75, float(novelty_w)))
    chord_novelty_w = max(0.0, min(0.50, float(chord_novelty_w)))
    reg_novelty_w = max(0.0, min(0.50, float(reg_novelty_w)))
    reg_target = max(0.5, min(18.0, float(reg_target)))
    reg_sigma = max(0.5, min(18.0, float(reg_sigma)))

    try:
        from ai.markov.melody.beauty import score_lyrical_melody

        tokens = melody_tokens_for_lyrical_score(events, emotion=emotion, root_note=int(root_note))
        lyrical, components = score_lyrical_melody(tokens, cadence_degree=0)
        role_mult = {
            "b": 1.18,
            "chorus": 1.18,
            "hook": 1.18,
            "tag": 1.10,
            "pre_chorus": 1.08,
            "a_prime": 1.06,
            "a": 0.96,
            "verse": 0.96,
            "intro": 0.84,
            "outro": 1.00,
        }.get(role, 1.0)
        lyrical_bonus = float(lyrical_w) * float(role_mult) * (float(lyrical) - float(lyrical_target))
        score += float(lyrical_bonus)
        details["sampler_lyrical_score"] = float(lyrical)
        details["sampler_lyrical_target"] = float(lyrical_target)
        details["sampler_lyrical_bonus"] = float(lyrical_bonus)
        details["sampler_lyrical_components"] = dict(components)
    except Exception:
        details["sampler_lyrical_score"] = None

    try:
        sig = tuple(getattr(candidate_song_memory, "last_chord_signature", ()) or ())
        recent = [tuple(x) for x in list(getattr(baseline_song_memory, "recent_chord_signatures", []) or [])]
        if sig and sig in recent:
            score -= float(repeat_w)
            details["sampler_harmony_repeat_penalty"] = float(repeat_w)
        else:
            details["sampler_harmony_repeat_penalty"] = 0.0
    except Exception:
        details["sampler_harmony_repeat_penalty"] = 0.0

    try:
        cand_center = getattr(candidate_song_memory, "last_register_center", None)
        recent_centers = list(getattr(baseline_song_memory, "recent_register_centers", []) or [])
        if cand_center is not None and recent_centers:
            prev = float(recent_centers[-1])
            dist = abs(float(cand_center) - float(prev))
            if dist < 2.0 and role in {"a", "verse", "intro", "pre_chorus", "outro"}:
                pen = float(register_w) * float((2.0 - dist) / 2.0)
                score -= float(pen)
                details["sampler_register_stasis_penalty"] = float(pen)
            else:
                details["sampler_register_stasis_penalty"] = 0.0
            details["sampler_register_distance_from_previous"] = float(dist)
    except Exception:
        details["sampler_register_stasis_penalty"] = 0.0

    novelty_bonus = 0.0
    if novelty_on and novelty_w > 1e-9:
        try:
            sig = tuple(getattr(candidate_song_memory, "last_chord_signature", ()) or ())
            recent = [tuple(x) for x in list(getattr(baseline_song_memory, "recent_chord_signatures", []) or [])]

            def _jaccard(a: Tuple[str, ...], b: Tuple[str, ...]) -> float:
                sa = set(str(x) for x in (a or ()) if x)
                sb = set(str(x) for x in (b or ()) if x)
                if not sa and not sb:
                    return 1.0
                u = len(sa | sb)
                if u <= 0:
                    return 0.0
                return float(len(sa & sb)) / float(u)

            if sig and recent:
                max_sim = max(_jaccard(sig, r) for r in recent) if recent else 0.0
                chord_novelty = max(0.0, min(1.0, 1.0 - float(max_sim)))
                role_mult = 0.75 if role in {"b", "chorus", "tag"} else (0.90 if role in {"pre_chorus", "a_prime"} else 1.0)
                novelty_bonus += float(chord_novelty_w) * float(role_mult) * float(chord_novelty)
                details["sampler_chord_novelty"] = float(chord_novelty)
                details["sampler_chord_max_similarity"] = float(max_sim)
            else:
                details["sampler_chord_novelty"] = 0.0
        except Exception:
            details["sampler_chord_novelty"] = 0.0

        try:
            cand_center = getattr(candidate_song_memory, "last_register_center", None)
            recent_centers = list(getattr(baseline_song_memory, "recent_register_centers", []) or [])
            if cand_center is not None and recent_centers:
                prev = float(recent_centers[-1])
                dist = abs(float(cand_center) - float(prev))
                z = (float(dist) - float(reg_target)) / float(reg_sigma)
                peak = math.exp(-0.5 * float(z * z))
                if dist < 1.0:
                    peak *= 0.35
                role_mult = 0.70 if role in {"intro", "outro", "b", "chorus", "tag"} else 1.0
                novelty_bonus += float(reg_novelty_w) * float(role_mult) * float(max(0.0, min(1.0, peak)))
                details["sampler_register_drift_semitones"] = float(dist)
                details["sampler_register_drift_peak"] = float(peak)
            else:
                details["sampler_register_drift_semitones"] = None
        except Exception:
            details["sampler_register_drift_semitones"] = None

        novelty_bonus = float(novelty_bonus) * float(novelty_w)
        score += float(novelty_bonus)

    details["sampler_novelty_enabled"] = bool(novelty_on)
    details["sampler_novelty_bonus"] = float(novelty_bonus)

    details["sampler_adjusted_score"] = float(score)
    details["sampler_musical_rerank_enabled"] = True
    return float(score), details


def score_section_with_sampler_adjustments(
    events: Sequence[Sequence[Any]],
    *,
    beats_per_bar: float = 4.0,
    bars: Optional[int] = None,
    timeline_targets: Optional[Dict[str, List[float]]] = None,
    section_role: Optional[str] = None,
    emotion_name: Optional[str] = None,
    emotion: Any = None,
    root_note: int = 60,
    candidate_song_memory: Any = None,
    baseline_song_memory: Any = None,
) -> SectionScore:
    """
    Single entrypoint for best-of-K picking: structural `score_section` plus sampler rerank terms.

    Use this from `run_best_of_k_section_build` so tuning/tests target one pipeline.
    """
    base = score_section(
        events,
        beats_per_bar=beats_per_bar,
        bars=bars,
        timeline_targets=timeline_targets,
        section_role=section_role,
        emotion_name=emotion_name,
    )
    adj, samp = sampler_musical_adjustment(
        base_score=float(base.score),
        events=events,
        emotion=emotion,
        root_note=int(root_note),
        section_role=str(section_role or ""),
        candidate_song_memory=candidate_song_memory,
        baseline_song_memory=baseline_song_memory,
    )
    merged: Dict[str, Any] = dict(base.details or {})
    merged.update(samp)
    merged["section_score_before_sampler"] = float(base.score)
    merged["final_pick_score"] = float(adj)
    return SectionScore(
        score=float(adj),
        details=merged,
        components=base.components,
    )


def _pop_hook_lead_shape(
    events: Sequence[Sequence[Any]],
    *,
    beats_per_bar: float,
    max_bars: int = 2,
) -> Dict[str, Any]:
    """
    Score how "hooky" the lead opening is for chorus-style picking: first `max_bars`
    of channel-2 onsets, pitch classes only. Favors a dominant pitch class and a
    compact (not over-scattered) PC set. Neutral when < 2 notes.
    """
    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    w_end = max(0.0, float(max_bars)) * bpb
    pcs: List[int] = []
    for ev in events:
        if not ev or len(ev) < 6:
            continue
        if int(ev[0]) != 2:
            continue
        st = float(ev[3])
        if st < 0.0 or st >= w_end - 1e-9:
            continue
        notes = ev[5] if len(ev) > 5 else None
        if not notes or not isinstance(notes, list):
            continue
        try:
            pcs.append(int(notes[0]) % 12)
        except Exception:
            continue
    n = int(len(pcs))
    out: Dict[str, Any] = {
        "pop_hook_opening_n": n,
    }
    if n < 2:
        out["pop_hook_mode_frac"] = 0.0
        out["pop_hook_shape"] = 0.5
        out["pop_hook_unique_pcs"] = 0
        return out
    c = Counter(pcs)
    mode_count = c.most_common(1)[0][1]
    unique = int(len(c))
    dom = float(mode_count) / float(n)
    out["pop_hook_mode_frac"] = float(dom)
    out["pop_hook_unique_pcs"] = int(unique)
    if n > 1:
        compact = 1.0 - float(max(0, unique - 1)) / float(n - 1)
    else:
        compact = 0.0
    compact = float(max(0.0, min(1.0, float(compact))))
    raw = 0.55 * float(dom) + 0.45 * float(compact)
    if unique > 7:
        raw *= 0.85
    out["pop_hook_shape"] = float(max(0.0, min(1.0, raw)))
    return out


def _arp_melody_compat(
    events: Sequence[Sequence[Any]],
    *,
    beats_per_bar: float,
    bars: Optional[int],
) -> Dict[str, Any]:
    """
    Return lightweight arp↔melody compatibility metrics for best-of-K picking.

    Metrics focus on the lead (ch=2) vs arp bed (ch=3):
    - overlap_time_frac: how much lead time is covered by arp time
    - pc_collision_frac: fraction of overlapped lead time where pitch class matches
    - register_sep_ok_frac: fraction of overlapped lead time where arp is below lead by margin
    - strongbeat_masked_frac: fraction of lead strong-beat onsets that occur while arp is active
    """
    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0

    # Infer bars if not provided.
    if bars is None:
        mx = 0.0
        for ev in events:
            if not ev or len(ev) != 6:
                continue
            try:
                mx = max(mx, float(ev[3]) + float(ev[4]))
            except Exception:
                continue
        bars_n = int(max(1, round(mx / bpb))) if mx > 1e-6 else 0
    else:
        bars_n = int(bars)
    bars_n = max(0, int(bars_n))

    # Config knobs (all optional).
    sep_margin = resolve_config("composition", "arp_melody_register_separation_semitones", 5, int)
    strong_eps = resolve_config("composition", "strong_beat_epsilon_beats", 0.06, float)
    sep_margin = max(0, min(24, int(sep_margin)))
    strong_eps = max(0.0, min(0.15, float(strong_eps)))

    # Collect lead intervals + pitches, arp intervals + pitches, grouped by bar.
    lead_by_bar: List[List[Tuple[float, float, int, float]]] = [[] for _ in range(bars_n)]
    arp_by_bar: List[List[Tuple[float, float, int]]] = [[] for _ in range(bars_n)]
    for ev in events:
        if not ev or len(ev) != 6:
            continue
        try:
            ch = int(ev[0])
            st = float(ev[3])
            dur = float(ev[4])
            notes = ev[5] if len(ev) > 5 else None
        except Exception:
            continue
        if dur <= 1e-9:
            continue
        bar = int(st // bpb) if bpb > 1e-9 else 0
        if bar < 0 or bar >= bars_n:
            continue
        st_local = float(st - float(bar) * bpb)
        en_local = float(min(st_local + dur, bpb))
        if en_local <= st_local + 1e-9:
            continue
        try:
            pitch = int(notes[0]) if isinstance(notes, list) and notes else int(ev[1])
        except Exception:
            continue

        if ch == 2:
            lead_by_bar[bar].append((st_local, en_local, int(pitch), float(st_local)))
        elif ch == 3:
            arp_by_bar[bar].append((st_local, en_local, int(pitch)))

    # Sort by start for deterministic overlap accounting.
    for b in range(bars_n):
        lead_by_bar[b].sort(key=lambda x: float(x[0]))
        arp_by_bar[b].sort(key=lambda x: float(x[0]))

    def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
        lo = max(float(a0), float(b0))
        hi = min(float(a1), float(b1))
        return float(max(0.0, hi - lo))

    lead_total = 0.0
    lead_overlapped = 0.0
    pc_collide_time = 0.0
    sep_ok_time = 0.0
    strong_total = 0
    strong_masked = 0

    for bar in range(bars_n):
        arp_ints = arp_by_bar[bar]
        if not lead_by_bar[bar]:
            continue
        for ls, le, lp, l_on in lead_by_bar[bar]:
            ldur = float(max(0.0, float(le) - float(ls)))
            if ldur <= 1e-9:
                continue
            lead_total += ldur

            # strong-beat onset? (near integer beat)
            try:
                nearest = round(float(l_on))
                if abs(float(l_on) - float(nearest)) <= strong_eps:
                    strong_total += 1
                    # masked if any arp interval covers the onset
                    for as0, as1, _ap in arp_ints:
                        if float(as0) - 1e-6 <= float(l_on) <= float(as1) + 1e-6:
                            strong_masked += 1
                            break
            except Exception:
                pass

            if not arp_ints:
                continue

            # Overlap with arp intervals, tracking pc collisions + register separation.
            overl = 0.0
            collide = 0.0
            sep_ok = 0.0
            for as0, as1, ap in arp_ints:
                ol = _overlap(ls, le, as0, as1)
                if ol <= 1e-9:
                    continue
                overl += ol
                if (int(lp) % 12) == (int(ap) % 12):
                    collide += ol
                if int(ap) <= int(lp) - int(sep_margin):
                    sep_ok += ol
            if overl > 1e-9:
                lead_overlapped += overl
                pc_collide_time += collide
                sep_ok_time += sep_ok

    out: Dict[str, Any] = {}
    out["compat_lead_total_time_beats"] = float(lead_total)
    out["compat_lead_overlapped_time_beats"] = float(lead_overlapped)
    out["compat_overlap_time_frac"] = float(lead_overlapped / lead_total) if lead_total > 1e-9 else 0.0
    out["compat_pc_collision_frac"] = float(pc_collide_time / lead_overlapped) if lead_overlapped > 1e-9 else 0.0
    out["compat_register_sep_ok_frac"] = float(sep_ok_time / lead_overlapped) if lead_overlapped > 1e-9 else 1.0
    out["compat_strongbeat_total"] = int(strong_total)
    out["compat_strongbeat_masked"] = int(strong_masked)
    out["compat_strongbeat_masked_frac"] = float(strong_masked / strong_total) if strong_total > 0 else 0.0
    # Guardrail: clamp metric fractions to 0..1 (avoid drift from float error / edge cases).
    try:
        for k in ("compat_overlap_time_frac", "compat_pc_collision_frac", "compat_register_sep_ok_frac", "compat_strongbeat_masked_frac"):
            out[k] = float(max(0.0, min(1.0, float(out.get(k, 0.0) or 0.0))))
    except Exception:
        pass
    return out


def _melody_harmony_agreement(
    events: Sequence[Sequence[Any]],
    *,
    beats_per_bar: float,
    bars: Optional[int],
    timeline_targets: Optional[Dict[str, List[float]]],
) -> Dict[str, Any]:
    """
    Lightweight melody↔harmony agreement metrics for section reranking.

    Metrics:
    - strongbeat_chord_tone_frac: strong-beat melody onsets on active chord tones
    - onset_chord_tone_frac: all melody onsets on active chord tones
    - phrase_end_chord_tone_frac: phrase/cadence-ending melody landings on chord tones
    """
    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0

    # Infer bars when omitted.
    if bars is None:
        mx = 0.0
        for ev in events:
            if not ev or len(ev) != 6:
                continue
            try:
                mx = max(mx, float(ev[3]) + float(ev[4]))
            except Exception:
                continue
        bars_n = int(max(1, round(mx / bpb))) if mx > 1e-6 else 0
    else:
        bars_n = int(bars)
    bars_n = max(0, int(bars_n))

    # Tolerances.
    strong_eps = resolve_config("composition", "strong_beat_epsilon_beats", 0.06, float)
    phrase_end_eps = resolve_config("composition", "melody_phrase_cadence_landing_eps_beats", 0.65, float)
    strong_eps = max(0.0, min(0.15, float(strong_eps)))
    phrase_end_eps = max(0.20, min(1.00, float(phrase_end_eps)))

    # Per-bar chord windows and fallback pitch-class sets.
    chord_by_bar: List[List[Tuple[float, float, set[int]]]] = [[] for _ in range(bars_n)]
    chord_pcs_by_bar: List[set[int]] = [set() for _ in range(bars_n)]
    melody_by_bar: List[List[Tuple[float, float, int]]] = [[] for _ in range(bars_n)]

    for ev in events:
        if not ev or len(ev) != 6:
            continue
        try:
            ch = int(ev[0])
            st = float(ev[3])
            dur = float(ev[4])
            notes = ev[5] if len(ev) > 5 else None
        except Exception:
            continue
        if dur <= 1e-9:
            continue
        bar = int(st // bpb) if bpb > 1e-9 else 0
        if bar < 0 or bar >= bars_n:
            continue
        st_local = float(st - float(bar) * bpb)
        en_local = float(min(st_local + dur, bpb))
        if en_local <= st_local + 1e-9:
            continue

        if ch == 1:
            pcs = set()
            if isinstance(notes, list):
                for n in notes:
                    if isinstance(n, int):
                        pcs.add(int(n) % 12)
            if pcs:
                chord_by_bar[bar].append((st_local, en_local, set(pcs)))
                chord_pcs_by_bar[bar].update(set(pcs))
        elif ch == 2:
            try:
                pitch = int(notes[0]) if isinstance(notes, list) and notes else int(ev[1])
            except Exception:
                continue
            melody_by_bar[bar].append((st_local, en_local, int(pitch)))

    for bi in range(bars_n):
        chord_by_bar[bi].sort(key=lambda x: float(x[0]))
        melody_by_bar[bi].sort(key=lambda x: float(x[0]))

    # Phrase-ending bars: explicit cadence bars first; fallback to 4-bar phrase tails.
    cadence_w = list((timeline_targets or {}).get("cadence_window", []) or [])
    phrase_end_bars = set()
    if cadence_w:
        for bi in range(min(bars_n, len(cadence_w))):
            try:
                if float(cadence_w[bi]) >= 0.95:
                    phrase_end_bars.add(int(bi))
            except Exception:
                continue
    if not phrase_end_bars and bars_n > 0:
        for bi in range(bars_n):
            if (int(bi) % 4) == 3 or int(bi) == int(bars_n) - 1:
                phrase_end_bars.add(int(bi))

    def _active_pcs_for_onset(bar: int, onset_local: float) -> set[int]:
        if bar < 0 or bar >= bars_n:
            return set()
        # Prefer active chord window at onset.
        for s0, s1, pcs in chord_by_bar[bar]:
            if float(s0) - 1e-6 <= float(onset_local) <= float(s1) + 1e-6:
                return set(pcs)
        # Fallback to any chord pcs in that bar.
        return set(chord_pcs_by_bar[bar])

    strong_total = 0
    strong_hit = 0
    onset_total = 0
    onset_hit = 0
    phrase_total = 0
    phrase_hit = 0

    for bi in range(bars_n):
        mel = melody_by_bar[bi]
        if not mel:
            continue
        # Onset + strong-beat agreement.
        for st0, _en0, mp in mel:
            pcs = _active_pcs_for_onset(int(bi), float(st0))
            if not pcs:
                continue
            onset_total += 1
            if (int(mp) % 12) in pcs:
                onset_hit += 1
            nearest = round(float(st0))
            if abs(float(st0) - float(nearest)) <= strong_eps:
                strong_total += 1
                if (int(mp) % 12) in pcs:
                    strong_hit += 1

        # Phrase/cadence ending landing: last melody onset near end of bar.
        if int(bi) in phrase_end_bars:
            last = mel[-1]
            st_last, _en_last, mp_last = last
            if float(st_last) >= float(bpb) - float(phrase_end_eps):
                pcs_last = _active_pcs_for_onset(int(bi), float(st_last))
                if pcs_last:
                    phrase_total += 1
                    if (int(mp_last) % 12) in pcs_last:
                        phrase_hit += 1

    out: Dict[str, Any] = {}
    out["mh_onset_total"] = int(onset_total)
    out["mh_onset_hit"] = int(onset_hit)
    out["mh_onset_chord_tone_frac"] = float(onset_hit / onset_total) if onset_total > 0 else 0.5
    out["mh_strongbeat_total"] = int(strong_total)
    out["mh_strongbeat_hit"] = int(strong_hit)
    out["mh_strongbeat_chord_tone_frac"] = float(strong_hit / strong_total) if strong_total > 0 else 0.5
    out["mh_phrase_end_total"] = int(phrase_total)
    out["mh_phrase_end_hit"] = int(phrase_hit)
    out["mh_phrase_end_chord_tone_frac"] = float(phrase_hit / phrase_total) if phrase_total > 0 else 0.5
    try:
        for k in ("mh_onset_chord_tone_frac", "mh_strongbeat_chord_tone_frac", "mh_phrase_end_chord_tone_frac"):
            out[k] = float(max(0.0, min(1.0, float(out.get(k, 0.5) or 0.5))))
    except Exception:
        pass
    return out


def score_section(
    events: Sequence[Sequence[Any]],
    *,
    beats_per_bar: float = 4.0,
    bars: Optional[int] = None,
    timeline_targets: Optional[Dict[str, List[float]]] = None,
    section_role: Optional[str] = None,
    emotion_name: Optional[str] = None,
) -> SectionScore:
    """
    Section-level scorer used by best-of-K section picking.
    Starts with the existing lightweight song scorer and adds a small penalty
    when the realized lead density deviates heavily from timeline targets.
    """
    base, details = score_song(events, beats_per_bar=beats_per_bar, bars=bars)
    song_base = float(base)
    score = song_base
    anchor = score

    # Cadence clarity: cadence bars should open space (less arp/counter clutter).
    # This uses timeline_targets cadence_window when available, and is deterministic.
    try:
        cad = list((timeline_targets or {}).get("cadence_window", []) or [])
    except Exception:
        cad = []

    if cad:
        try:
            bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
            bars_n = int(bars) if bars is not None else int(len(cad))
            bars_n = max(0, min(int(bars_n), int(len(cad))))
        except Exception:
            bpb = 4.0
            bars_n = int(len(cad))
        if bars_n > 0 and bpb > 1e-9 and events:
            try:
                # Per-bar onset counts for accompaniment layers.
                chord_hits = [0 for _ in range(bars_n)]
                arp_hits = [0 for _ in range(bars_n)]
                ctr_hits = [0 for _ in range(bars_n)]
                for ev in events:
                    if not ev or len(ev) != 6:
                        continue
                    try:
                        ch = int(ev[0])
                        st = float(ev[3])
                    except Exception:
                        continue
                    bar = int(st // float(bpb)) if bpb > 1e-9 else 0
                    if bar < 0 or bar >= bars_n:
                        continue
                    if ch == 1:
                        chord_hits[bar] += 1
                    elif ch == 3:
                        arp_hits[bar] += 1
                    elif ch == 5:
                        ctr_hits[bar] += 1

                cad_bars = [i for i in range(bars_n) if float(cad[i] or 0.0) >= 0.95]
                if cad_bars:
                    # Penalize excessive activity on cadence bars.
                    pen = 0.0
                    for i in cad_bars:
                        pen += max(0.0, float(chord_hits[i]) - 2.0) / 6.0
                        pen += max(0.0, float(arp_hits[i]) - 2.0) / 8.0
                        pen += max(0.0, float(ctr_hits[i]) - 1.0) / 6.0
                    pen = float(pen) / float(max(1, len(cad_bars)))
                    # Small weight: cadence shaping is one aspect of overall quality.
                    cad_w = 0.18
                    score -= float(cad_w) * float(pen)
                    details["cadence_bars"] = int(len(cad_bars))
                    details["cadence_clarity_penalty"] = float(pen)
                    details["cadence_clarity_weight"] = float(cad_w)
            except Exception:
                pass

    cadence_adjustment = score - anchor
    anchor = score

    # Arp↔melody compatibility: prefer a bed that supports the lead.
    compat_enabled = resolve_config("composition", "arp_melody_compat_scoring_enabled", True, bool)
    compat_w = resolve_config("composition", "arp_melody_compat_weight", 0.25, float)
    pc_w = resolve_config("composition", "arp_melody_pc_collision_weight", 1.0, float)
    strong_w = resolve_config("composition", "arp_melody_strongbeat_mask_weight", 0.75, float)
    sep_w = resolve_config("composition", "arp_melody_register_sep_weight", 0.65, float)
    compat_w = max(0.0, min(1.25, float(compat_w)))
    if compat_enabled and compat_w > 1e-9:
        try:
            cm = _arp_melody_compat(events, beats_per_bar=float(beats_per_bar), bars=bars)
            details.update(cm)
            pc_frac = float(cm.get("compat_pc_collision_frac", 0.0) or 0.0)
            strong_frac = float(cm.get("compat_strongbeat_masked_frac", 0.0) or 0.0)
            sep_ok = float(cm.get("compat_register_sep_ok_frac", 1.0) or 1.0)

            # Convert metrics to a penalty:
            # - pc collisions: harsh, penalize once > ~0.15 of overlapped time
            # - strongbeat masking: prefer melody downbeats to be clear (penalize > ~0.55)
            # - register separation: penalize when separation frequently fails (< ~0.70 ok)
            pen = 0.0
            pen += float(pc_w) * max(0.0, pc_frac - 0.15) / 0.85
            pen += float(strong_w) * max(0.0, strong_frac - 0.55) / 0.45
            pen += float(sep_w) * max(0.0, 0.70 - sep_ok) / 0.70
            pen = max(0.0, float(pen))
            score -= float(compat_w) * float(pen)
            details["compat_penalty"] = float(pen)
            details["compat_weight"] = float(compat_w)
        except Exception:
            pass

    arp_melody_compat_adjustment = score - anchor
    anchor = score

    # Melody↔harmony agreement: reward chord-tone alignment at structurally important moments.
    mh_enabled = resolve_config("composition", "melody_harmony_agreement_scoring_enabled", True, bool)
    mh_w = resolve_config("composition", "melody_harmony_agreement_weight", 0.28, float)
    strong_w = resolve_config("composition", "melody_harmony_strongbeat_weight", 1.0, float)
    phrase_w = resolve_config("composition", "melody_harmony_phrase_end_weight", 1.2, float)
    onset_w = resolve_config("composition", "melody_harmony_onset_weight", 0.65, float)
    mh_w = max(0.0, min(1.5, float(mh_w)))
    if mh_enabled and mh_w > 1e-9:
        try:
            role_lc = str(section_role or "").strip().lower()
            emo_lc = str(emotion_name or "").strip().lower()
            preset_lc = "balanced"
            preset_lc = resolve_config("composition", "melody_harmony_agreement_preset", 'balanced')
            rm = {
                "pre_chorus": 1.05,
                "b": 1.22,
                "chorus": 1.22,
                "hook": 1.20,
                "tag": 1.15,
                "a_prime": 1.10,
                "a": 0.95,
                "verse": 0.95,
                "intro": 0.85,
                "outro": 1.05,
            }.get(role_lc, 1.0)
            target = {
                "b": 0.70,
                "chorus": 0.70,
                "hook": 0.70,
                "tag": 0.68,
                "pre_chorus": 0.64,
                "a_prime": 0.66,
                "a": 0.58,
                "verse": 0.58,
                "intro": 0.56,
                "outro": 0.62,
            }.get(role_lc, 0.60)

            # Macro preset for fast auditioning.
            # Apply before emotion-specific tuning so per-emotion refinements stay relative.
            if preset_lc == "tight":
                mh_w *= 1.18
                strong_w *= 1.15
                phrase_w *= 1.18
                onset_w *= 0.92
                target = min(0.86, float(target) + 0.03)
                rm *= 1.08
            elif preset_lc == "loose":
                mh_w *= 0.78
                strong_w *= 0.92
                phrase_w *= 0.90
                onset_w *= 0.88
                target = max(0.48, float(target) - 0.03)
                rm *= 0.90
            else:
                preset_lc = "balanced"

            # Emotion-tuned agreement pressure (phase 5 refinement):
            # - optimism/joy: slightly tighter hook alignment
            # - love: still clear, but less rigid than bright anthemic moods
            if emo_lc == "optimism":
                mh_w *= 1.18
                strong_w *= 1.10
                phrase_w *= 1.14
                if role_lc in {"b", "chorus", "hook", "tag"}:
                    target = min(0.82, float(target) + 0.05)
                    rm *= 1.10
                elif role_lc in {"pre_chorus"}:
                    target = min(0.78, float(target) + 0.03)
            elif emo_lc == "joy":
                mh_w *= 1.15
                strong_w *= 1.12
                phrase_w *= 1.08
                if role_lc in {"b", "chorus", "hook", "tag"}:
                    target = min(0.81, float(target) + 0.04)
                    rm *= 1.08
                elif role_lc in {"pre_chorus"}:
                    target = min(0.77, float(target) + 0.03)
            elif emo_lc == "love":
                mh_w *= 1.06
                strong_w *= 1.04
                phrase_w *= 1.06
                if role_lc in {"b", "chorus", "hook", "tag"}:
                    target = min(0.78, float(target) + 0.02)
                    rm *= 1.03
                elif role_lc in {"pre_chorus"}:
                    target = min(0.74, float(target) + 0.01)

            mh_w = max(0.0, min(1.5, float(mh_w)))

            mh = _melody_harmony_agreement(
                events,
                beats_per_bar=float(beats_per_bar),
                bars=bars,
                timeline_targets=timeline_targets,
            )
            details.update(mh)
            strong_frac = float(mh.get("mh_strongbeat_chord_tone_frac", 0.5) or 0.5)
            phrase_frac = float(mh.get("mh_phrase_end_chord_tone_frac", 0.5) or 0.5)
            onset_frac = float(mh.get("mh_onset_chord_tone_frac", 0.5) or 0.5)

            num = (
                float(strong_w) * strong_frac
                + float(phrase_w) * phrase_frac
                + float(onset_w) * onset_frac
            )
            den = max(1e-9, float(strong_w) + float(phrase_w) + float(onset_w))
            agr = float(max(0.0, min(1.0, num / den)))

            # Centered bonus/penalty around role target: good agreement helps, poor hurts.
            delta = float(agr) - float(target)
            # Slightly stronger downside for hook-like roles when phrase-end agreement is weak.
            if role_lc in {"b", "chorus", "hook", "tag"} and phrase_frac < 0.55:
                delta -= float(0.10 * (0.55 - phrase_frac))
            bonus = float(mh_w) * float(rm) * float(delta)
            score += float(bonus)
            details["mh_agreement_score"] = float(agr)
            details["mh_agreement_target"] = float(target)
            details["mh_agreement_role_mult"] = float(rm)
            details["mh_agreement_bonus"] = float(bonus)
            details["mh_agreement_weight"] = float(mh_w)
            details["mh_agreement_emotion"] = str(emo_lc)
            details["mh_agreement_preset"] = str(preset_lc)
        except Exception:
            pass

    melody_harmony_agreement_adjustment = score - anchor
    anchor = score

    # Register-lane adherence (produced stability): penalize when realized registers
    # drift far from configured lane targets.
    mel_center = resolve_config("composition", "melody_lane_center_midi", 72, int)
    mel_hw = resolve_config("composition", "melody_lane_half_width", 10, int)
    ch_off = resolve_config("composition", "chords_lane_offset_from_melody", 12, int)
    ch_hw = resolve_config("composition", "chords_lane_half_width", 10, int)
    mel_hw = max(4, min(24, int(mel_hw)))
    ch_hw = max(4, min(24, int(ch_hw)))

    lead_pitches: List[int] = []
    chord_centers: List[int] = []
    mud_low_notes = 0
    mud_thr = resolve_config("composition", "chord_voicing_mud_threshold_midi", 40, int)
    for ev in events:
        if not ev or len(ev) != 6:
            continue
        ch = int(ev[0])
        notes = ev[5]
        if not notes or not isinstance(notes, list):
            continue
        if ch == 2:
            try:
                lead_pitches.append(int(notes[0]))
            except Exception:
                pass
        if ch == 1:
            try:
                nn = sorted(int(n) for n in notes if isinstance(n, int))
                if nn:
                    chord_centers.append(int(nn[len(nn) // 2]))
                    mud_low_notes += sum(1 for n in nn if int(n) < int(mud_thr))
            except Exception:
                pass

    if lead_pitches:
        lead_med = sorted(lead_pitches)[len(lead_pitches) // 2]
        d = abs(int(lead_med) - int(mel_center))
        lane_pen = max(0.0, float(d - mel_hw)) / max(1.0, float(mel_hw))
        score -= 0.12 * float(lane_pen)
        details["lane_lead_median_midi"] = int(lead_med)
        details["lane_lead_deviation"] = float(d)
        details["lane_lead_penalty"] = float(lane_pen)

    if chord_centers and lead_pitches:
        chord_med = sorted(chord_centers)[len(chord_centers) // 2]
        expected = int(mel_center) - int(ch_off)
        d2 = abs(int(chord_med) - int(expected))
        chord_lane_pen = max(0.0, float(d2 - ch_hw)) / max(1.0, float(ch_hw))
        score -= 0.08 * float(chord_lane_pen)
        details["lane_chord_median_midi"] = int(chord_med)
        details["lane_chord_expected_center_midi"] = int(expected)
        details["lane_chord_deviation"] = float(d2)
        details["lane_chord_penalty"] = float(chord_lane_pen)

    if mud_low_notes > 0:
        # Light penalty: mud should be rare in produced comping.
        score -= 0.02 * float(min(20, int(mud_low_notes))) / 20.0
        details["chord_mud_low_notes"] = int(mud_low_notes)

    lane_register_adjustment = score - anchor
    anchor = score

    # Density fit: compare intended melody density curve vs realized lead activity.
    try:
        if timeline_targets and timeline_targets.get("melody_density"):
            t = [float(x) for x in (timeline_targets.get("melody_density") or [])]
            # Normalize target curve around 1.0 mean for comparison.
            mean_t = sum(t) / max(1, len(t))
            mean_t = mean_t if abs(mean_t) > 1e-9 else 1.0
            t_norm = [x / mean_t for x in t]
            # Realized lead activity is already [0..1] occupancy fraction.
            lead_act = float(details.get("lead_activity", 0.0))
            # Heuristic: if target wants very sparse or very dense, reward matching.
            target_sparse = sum(1 for x in t_norm if x < 0.85) / max(1, len(t_norm))
            target_dense = sum(1 for x in t_norm if x > 1.15) / max(1, len(t_norm))
            # Penalize when intended sparse but realized very active, and vice versa.
            score -= 0.20 * max(0.0, (target_sparse - 0.25)) * max(0.0, lead_act - 0.45)
            score -= 0.14 * max(0.0, (target_dense - 0.25)) * max(0.0, 0.22 - lead_act)
            details["density_target_sparse_frac"] = float(target_sparse)
            details["density_target_dense_frac"] = float(target_dense)
    except Exception:
        pass

    density_curve_adjustment = score - anchor
    anchor = score

    # Breath / cadence contrast: reward leaving space on structural bars.
    # This helps best-of-K align with “composed” phrasing even when realtime runs K=1.
    try:
        bpb = float(beats_per_bar)
        bpb = 4.0 if bpb <= 0 else bpb
        total_bars = int(bars) if bars is not None else None
        if total_bars is None:
            # Best-effort infer.
            mx = 0.0
            for ev in events:
                if not ev or len(ev) != 6:
                    continue
                try:
                    mx = max(mx, float(ev[3]) + float(ev[4]))
                except Exception:
                    continue
            total_bars = int(max(1, round(mx / bpb)))

        breath = list((timeline_targets or {}).get("breath_window", []) or [])
        cadence = list((timeline_targets or {}).get("cadence_window", []) or [])
        if (breath or cadence) and total_bars and total_bars > 0:
            lead_onsets = [0 for _ in range(int(total_bars))]
            for ev in events:
                if not ev or len(ev) != 6:
                    continue
                try:
                    if int(ev[0]) != 2:
                        continue
                    st = float(ev[3])
                    bi = int(st // bpb)
                    if 0 <= bi < len(lead_onsets):
                        lead_onsets[bi] += 1
                except Exception:
                    continue

            breath_pen = 0.0
            breath_reward = 0.0
            cad_pen = 0.0
            for bi in range(int(total_bars)):
                bw = float(breath[bi]) if 0 <= bi < len(breath) else 0.0
                cw = float(cadence[bi]) if 0 <= bi < len(cadence) else 0.0
                n = int(lead_onsets[bi])
                if bw >= 0.90:
                    # Prefer 0–1 lead onsets on breath bars.
                    if n <= 1:
                        breath_reward += 0.04 * float(1.0 if n == 0 else 0.5)
                    else:
                        breath_pen += 0.06 * float(n - 1)
                if cw >= 0.95:
                    # Prefer modest activity on strong cadence bars.
                    if n >= 4:
                        cad_pen += 0.04 * float(n - 3)
            score += float(breath_reward)
            score -= float(breath_pen + cad_pen)
            details["breath_lead_onsets_by_bar"] = list(lead_onsets)
            details["breath_reward"] = float(breath_reward)
            details["breath_penalty"] = float(breath_pen)
            details["cadence_penalty"] = float(cad_pen)
    except Exception:
        pass

    breath_cadence_adjustment = score - anchor
    anchor = score

    # Pop-style hook opening: chorus-like roles get a small best-of-K bonus when
    # the first two bars of lead show concentrated pitch use (default off).
    ph_s = resolve_config("composition", "pop_hook_scoring_strength", 0.0, float)
    ph_s = max(0.0, min(1.0, float(ph_s)))
    if ph_s > 1e-9 and events:
        try:
            role_lc2 = str(section_role or "").strip().lower()
        except Exception:
            role_lc2 = ""
        if role_lc2 in {"b", "chorus", "hook", "tag"}:
            try:
                ph = _pop_hook_lead_shape(
                    events,
                    beats_per_bar=float(beats_per_bar),
                    max_bars=2,
                )
                details.update(ph)
                shape = float(ph.get("pop_hook_shape", 0.5) or 0.5)
                bonus = float(ph_s) * 0.16 * max(0.0, float(shape) - 0.42)
                score += float(bonus)
                details["pop_hook_scoring_bonus"] = float(bonus)
            except Exception:
                pass

    pop_hook_adjustment = score - anchor

    components = SectionScoreComponents(
        song_base=float(song_base),
        cadence_adjustment=float(cadence_adjustment),
        arp_melody_compat_adjustment=float(arp_melody_compat_adjustment),
        melody_harmony_agreement_adjustment=float(melody_harmony_agreement_adjustment),
        lane_register_adjustment=float(lane_register_adjustment),
        density_curve_adjustment=float(density_curve_adjustment),
        breath_cadence_adjustment=float(breath_cadence_adjustment),
        pop_hook_adjustment=float(pop_hook_adjustment),
    )
    details["section_score"] = float(score)
    details["section_score_components"] = asdict(components)
    return SectionScore(score=float(score), details=dict(details), components=components)