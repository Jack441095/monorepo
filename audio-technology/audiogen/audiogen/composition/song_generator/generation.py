# composition/song_generator/generation.py
# Core song-generation pipeline: `SongGenerator.__init__` (owns/wraps a
# `CompositionGenerator`), `generate_song` / `_generate_song_impl` (stitches
# per-section renders into one global event timeline, applying song-level
# cohesion: locked chord progressions per role family, one climax section,
# whole-song postprocess, and metadata/metrics), and `generate_song_best_of_k`
# (seeded best-of-k candidate search plus optional closed-loop WAV-analysis
# regeneration).

from __future__ import annotations

import logging
import random
from typing import Any, Dict, List, Optional, Sequence, Tuple

from audiogen_core.config import resolve_config
from data.audit import normalize_emotion_scalars
from data.emotion_aliases import canonical_emotion_name
from data.music_data import EMOTION_BY_NAME

from ..engine import CompositionGenerator
from ..policies import ArrangementPolicy
from ..song_postprocess_pipeline import run_whole_song_postprocess
from ..transition_handoff import extract_last_bar_harmonic_context
from .models import SongRender, SongSectionSpec

logger = logging.getLogger(__name__)


class GenerationMixin:
    """Owns the composer and drives whole-song generation / best-of-k search."""

    def __init__(self, composer: Optional[CompositionGenerator] = None):
        self._owns_composer = composer is None
        self.composer = composer or CompositionGenerator()


    def generate(self, *args, **kwargs) -> SongRender:
        return self.generate_song(*args, **kwargs)

    def generate_song(
        self,
        sections: Sequence[SongSectionSpec],
        *,
        base_tempo_bpm: float = 70.0,
        arrangement_form: str = "default",
        seed: Optional[int] = None,
        feedback_constraints: Optional[dict] = None,
    ) -> SongRender:
        flags = (feedback_constraints or {}).get("flags") if feedback_constraints else None
        if flags:
            from composition.analysis_feedback_adapter import feedback_adaptation_context, adapt_song_sections
            from audiogen_core.config import CONFIG
            sections = adapt_song_sections(sections, flags)
            with feedback_adaptation_context(CONFIG, flags):
                return self._generate_song_impl(
                    sections=sections,
                    base_tempo_bpm=base_tempo_bpm,
                    arrangement_form=arrangement_form,
                    seed=seed,
                )
        return self._generate_song_impl(
            sections=sections,
            base_tempo_bpm=base_tempo_bpm,
            arrangement_form=arrangement_form,
            seed=seed,
        )

    def _generate_song_impl(
        self,
        sections: Sequence[SongSectionSpec],
        *,
        base_tempo_bpm: float = 70.0,
        arrangement_form: str = "default",
        seed: Optional[int] = None,
    ) -> SongRender:
        """
        arrangement_form: ``default`` | ``pop`` | ``pop_ext`` | ``rondo`` | ``ballad`` | ``wave`` | ``anthem``
        — must match the section list. Ambient uses ``default``.
        """
        # Determinism (seeded renders): seed Python/NumPy and use a fresh composer so
        # initialization-time randomness and prior state can't leak across runs.
        _old_py_random_state = None
        _old_config_state = {}
        if seed is not None:
            try:
                _old_py_random_state = random.getstate()
                random.seed(int(seed))
            except Exception:
                _old_py_random_state = None
            try:
                import numpy as _np  # type: ignore[import-not-found]

                _np.random.seed(int(seed))
            except Exception:
                pass
            try:
                from audiogen_core.config import CONFIG

                _old_config_state["section_pick_use_wall_clock"] = getattr(
                    CONFIG.composition, "section_pick_use_wall_clock", True
                )
                _old_config_state["joint_generation_use_wall_clock"] = getattr(
                    CONFIG.composition, "joint_generation_use_wall_clock", False
                )
                _old_config_state["voice_leading_time_budget_s"] = getattr(
                    CONFIG.composition, "voice_leading_time_budget_s", 0.40
                )

                CONFIG.composition.section_pick_use_wall_clock = False
                CONFIG.composition.joint_generation_use_wall_clock = False
                CONFIG.composition.voice_leading_time_budget_s = 0.0
            except Exception:
                pass
            if getattr(self, "_owns_composer", False):
                self.composer = CompositionGenerator()
        form = arrangement_form or "default"
        self.composer.arrangement_policy.form_mode = form
        if hasattr(self.composer.arrangement_policy, "set_song_identity_seed"):
            try:
                self.composer.arrangement_policy.set_song_identity_seed(seed)
            except Exception:
                pass
        if seed is not None and hasattr(self.composer, "reseed"):
            try:
                self.composer.reseed(int(seed))
            except Exception:
                pass
        self.composer.reset_song_arrangement_state()

        # ------------------------------------------------------------------
        # Song-level cohesion: pick one arp "mode identity" per song (optionally per role)
        # so sections feel like one arrangement instead of stitched fragments.
        # SectionPlanner will consume this via composer._song_arp_mode_by_role.
        # ------------------------------------------------------------------
        try:
            rng = getattr(self.composer, "rng", random)
        except Exception:
            rng = random
        try:
            roles = list(
                (ArrangementPolicy._FORM_SEQUENCES.get(form) or ArrangementPolicy._FORM_SEQUENCES["default"])
            )
        except Exception:
            roles = []
        # Pick a small palette once per song.
        try:
            verse_mode = str(rng.choice(["up", "down", "updown_excl", "converge"]))
        except Exception:
            verse_mode = "up"
        try:
            chorus_mode = str(rng.choice(["updown", "downup", "updown_excl"]))
        except Exception:
            chorus_mode = "updown"
        # Make pre-chorus feel like a lift/lead-in without changing the song identity too much.
        pre_mode = "converge" if verse_mode in {"up", "updown_excl"} else "up"
        outro_mode = "down"
        intro_mode = "converge"
        by_role = {
            "intro": intro_mode,
            "a": verse_mode,
            "verse": verse_mode,
            "pre_chorus": pre_mode,
            "b": chorus_mode,
            "chorus": chorus_mode,
            "hook": chorus_mode,
            "tag": chorus_mode,
            "a_prime": chorus_mode,
            "outro": outro_mode,
        }
        try:
            setattr(self.composer, "_song_arp_mode_by_role", dict(by_role))
            setattr(self.composer, "_song_arp_mode", str(verse_mode))
        except Exception:
            pass

        seq = ArrangementPolicy._FORM_SEQUENCES.get(form) or ArrangementPolicy._FORM_SEQUENCES["default"]
        if seq and len(sections) != len(seq):
            # Shorter section lists are valid for previews (e.g. live cold-start generates the
            # first 1–2 roles of a form). Only warn when the section count exceeds the form
            # definition, since that indicates a likely caller mistake.
            if len(sections) > len(seq):
                logger.warning(
                    "Section count %s > arrangement roles %s for form %r (extra sections will not have role curves).",
                    len(sections),
                    len(seq),
                    form,
                )

        events: List[Tuple] = []
        tempo_map: List[Tuple[float, float]] = []
        motif_development_sections: List[Dict[str, Any]] = []
        section_signatures: List[Dict[str, Any]] = []
        song_blueprint = None
        song_blueprint_sections = []
        bp_on = resolve_config("composition", "song_blueprint_enabled", True, bool)
        if bp_on:
            try:
                from composition.song_blueprint import build_song_blueprint

                song_blueprint = build_song_blueprint(sections, form_mode=str(form))
                song_blueprint_sections = list(getattr(song_blueprint, "sections", []) or [])
            except Exception:
                song_blueprint = None
                song_blueprint_sections = []
        try:
            setattr(self.composer, "_song_blueprint", song_blueprint)
            setattr(self.composer, "_song_blueprint_sections", list(song_blueprint_sections or []))
        except Exception:
            pass

        beat_offset = 0.0
        handoff_ctx: Optional[Dict[str, Any]] = None
        # ------------------------------------------------------------------
        # Song-level chord progression cohesion.
        #
        # Within one song, repeated roles should reuse the same progression so
        # choruses match and verses feel like variations over a stable skeleton.
        # Across songs (different seeds), progressions can differ naturally.
        # ------------------------------------------------------------------
        locked_progressions: Dict[str, List[str]] = {}
        section_chord_progressions: List[List[str]] = []
        role_counts: Dict[str, int] = {}
        section_phrase_spans: List[Dict[str, Any]] = []

        def _role_family(role_name: str) -> str:
            rlc = str(role_name or "").strip().lower()
            if rlc in {"b", "chorus", "hook", "tag"}:
                return "chorus"
            if rlc in {"pre_chorus"}:
                return "pre_chorus"
            if rlc in {"a", "verse", "a_prime"}:
                return "verse"
            return rlc or "other"

        def _fit_progression(chords: List[str], bars: int) -> List[str]:
            if not chords:
                return []
            b = max(1, int(bars))
            if len(chords) == b:
                return list(chords)
            # Cycle the progression to fit the target bar count.
            return [str(chords[i % len(chords)]) for i in range(b)]

        primary_emotion_name = ""
        try:
            roles_for_primary = [str(seq[i]) if i < len(seq) else "" for i in range(len(sections))]
            preferred_roles = {"a", "verse", "a_prime"}
            for i, role in enumerate(roles_for_primary):
                if str(role).strip().lower() in preferred_roles and i < len(sections):
                    primary_emotion_name = canonical_emotion_name(str(sections[i].emotion_name))
                    break
            if not primary_emotion_name:
                secondary_roles = {"b", "chorus", "hook", "tag", "pre_chorus"}
                for i, role in enumerate(roles_for_primary):
                    if str(role).strip().lower() in secondary_roles and i < len(sections):
                        primary_emotion_name = canonical_emotion_name(str(sections[i].emotion_name))
                        break
            if not primary_emotion_name and sections:
                primary_emotion_name = canonical_emotion_name(str(sections[0].emotion_name))
        except Exception:
            primary_emotion_name = ""
        try:
            setattr(self.composer, "_song_primary_emotion_name", str(primary_emotion_name))
            if hasattr(self.composer, "arrangement_policy") and hasattr(
                self.composer.arrangement_policy, "set_song_primary_emotion"
            ):
                self.composer.arrangement_policy.set_song_primary_emotion(primary_emotion_name)
        except Exception:
            pass

        # Song-level climax section (2026-07-02, docs/AUDIOGEN_COMPOSITION_PLAN.md item 13):
        # `_enforce_climax` (ai/markov/melody/generator.py) already raises a phrase's peak
        # note near its 2/3 point — but it was only reachable via `enforce_melody_climax`,
        # which defaulted to False everywhere, so the song's climax was never a deliberate,
        # single moment. Reuse that exact existing mechanism, but schedule it correctly:
        # fire it only for the LAST chorus-family section in the song's form (the
        # conventional "final chorus" climax point), not never and not on every section.
        climax_section_index = -1
        try:
            for i in range(len(sections)):
                role_i = str(seq[i]) if i < len(seq) else ""
                if _role_family(role_i) == "chorus":
                    climax_section_index = i
        except Exception:
            climax_section_index = -1

        for section_index, spec in enumerate(sections):
            emo_name = canonical_emotion_name(spec.emotion_name)
            emotion = EMOTION_BY_NAME.get(emo_name)
            if emotion is None:
                raise ValueError(f"Unknown emotion '{spec.emotion_name}' (canonical '{emo_name}')")

            tempo_m, _, _ = normalize_emotion_scalars(emotion)
            bpm = float(base_tempo_bpm) * float(tempo_m)
            tempo_map.append((beat_offset, bpm))
            bp_sec = song_blueprint_sections[section_index] if section_index < len(song_blueprint_sections) else None
            try:
                setattr(self.composer, "_current_song_blueprint_section", bp_sec)
                setattr(self.composer, "_song_blueprint_motif_stage", str(getattr(bp_sec, "motif_stage", "") or ""))
                setattr(self.composer, "_song_blueprint_cadence_style", str(getattr(bp_sec, "cadence_style", "") or ""))
            except Exception:
                pass

            # Determine the role and its family for song-level cohesion.
            try:
                role = str(seq[section_index]) if section_index < len(seq) else ""
            except Exception:
                role = ""
            fam = _role_family(role)
            role_counts[fam] = int(role_counts.get(fam, 0)) + 1

            # Verse variation: later verse-like sections get a small temperature lift.
            temp = float(spec.temperature)
            if fam == "verse" and int(role_counts.get(fam, 0)) > 1:
                temp = float(min(1.25, temp + 0.05))
            if fam == "pre_chorus" and int(role_counts.get(fam, 0)) > 1:
                temp = float(min(1.25, temp + 0.03))

            chord_progression = None
            if fam in locked_progressions:
                chord_progression = _fit_progression(list(locked_progressions.get(fam) or []), int(spec.bars))

            # NOTE: composer.enforce_melody_climax is NOT read per-section — every section
            # re-applies its own emotion's melody params (`apply_emotion_params`, called from
            # section_planner/planner.py) INCLUDING that emotion's own `enforce_climax` value
            # (13/28 emotions have it on, 15 off, in data/emotion_melody_parameters.py), which
            # unconditionally overwrites whatever's set here before generation runs. The actual
            # override hook is `_force_song_climax_this_section`, read by planner.py right after
            # apply_emotion_params so it wins regardless of that emotion's own default.
            is_climax_section = section_index == climax_section_index
            if is_climax_section:
                self.composer._force_song_climax_this_section = True
            try:
                section_events = self.composer.generate_section(
                    emotion=emotion,
                    root_note=spec.root_note,
                    bars=spec.bars,
                    temperature=float(temp),
                    target_notes_per_bar=spec.target_notes_per_bar,
                    melody_style=spec.melody_style,
                    chord_progression=chord_progression,
                    section_index=section_index,
                    transition_handoff_context=handoff_ctx,
                )
            finally:
                if is_climax_section:
                    self.composer._force_song_climax_this_section = False
            # Capture / lock the chord progression used for this role family.
            try:
                plan = getattr(self.composer, "_last_section_plan", None)
                chords_used = list(getattr(plan, "chords", []) or []) if plan is not None else []
            except Exception:
                chords_used = []
            section_chord_progressions.append(list(chords_used))
            if fam not in locked_progressions and chords_used:
                locked_progressions[fam] = list(chords_used)
            try:
                md = dict(getattr(self.composer, "_last_section_motif_development", {}) or {})
                if md:
                    md["absolute_start_beats"] = float(beat_offset)
                    motif_development_sections.append(md)
            except Exception:
                pass
            try:
                sig = dict(getattr(self.composer, "_last_section_signature", {}) or {})
                if sig:
                    sig["section_index"] = int(section_index)
                    sig["role"] = str(role or sig.get("role", ""))
                    if bp_sec is not None:
                        sig.setdefault("motif_stage", str(getattr(bp_sec, "motif_stage", "") or ""))
                    section_signatures.append(sig)
                else:
                    section_signatures.append({"section_index": int(section_index), "role": str(role or "")})
            except Exception:
                pass
            try:
                plan = getattr(self.composer, "_last_section_plan", None)
                phrase_spans_local = list(getattr(plan, "phrase_spans", []) or []) if plan is not None else []
                for span in phrase_spans_local:
                    row = dict(span or {})
                    row["section_index"] = int(section_index)
                    row["section_role"] = str(role or "")
                    row["section_emotion"] = str(emo_name)
                    row["absolute_start_beats"] = float(beat_offset) + float(row.get("start_beats", 0.0) or 0.0)
                    if "end_beats" in row and row.get("end_beats") is not None:
                        row["absolute_end_beats"] = float(beat_offset) + float(row.get("end_beats", 0.0) or 0.0)
                    else:
                        row["absolute_end_beats"] = float(row["absolute_start_beats"]) + float(row.get("length_beats", 0.0) or 0.0)
                    section_phrase_spans.append(row)
            except Exception:
                pass

            for ev in section_events:
                if len(ev) != 6:
                    continue
                ch, midi, vel, start, dur, notes = ev
                events.append((ch, midi, vel, float(start) + beat_offset, float(dur), list(notes)))

            beat_offset += float(spec.bars) * 4.0
            if section_events:
                handoff_ctx = extract_last_bar_harmonic_context(
                    section_events, total_bars=spec.bars, beats_per_bar=4.0
                )
            else:
                handoff_ctx = None

        events.sort(key=lambda e: e[3])
        roles_for_post = [str(seq[i]) if i < len(seq) else "" for i in range(len(sections))]
        section_bars_for_post = [int(s.bars) for s in sections]
        events, song_postprocess, primary_emotion_for_post = run_whole_song_postprocess(
            events,
            sections=sections,
            roles_for_post=roles_for_post,
            section_bars_for_post=section_bars_for_post,
            section_phrase_spans=section_phrase_spans,
            composer=self.composer,
            beats_per_bar=4.0,
        )
        try:
            from audiogen_core.repro import generation_metadata

            meta = generation_metadata(seed=seed)
            meta["arrangement_form"] = form
        except Exception:
            meta = {"seed": int(seed) if seed is not None else None, "arrangement_form": form}
        if song_postprocess:
            meta["song_postprocess"] = dict(song_postprocess)
        meta["primary_emotion_for_postprocess"] = str(primary_emotion_for_post)
        # Expose the per-section chord progressions and the role-family locks so
        # we can audit "chorus 1 matches chorus 2" at the song level.
        try:
            if section_chord_progressions:
                meta["section_chord_progressions"] = list(section_chord_progressions)
            if locked_progressions:
                meta["locked_progressions_by_family"] = {k: list(v) for k, v in dict(locked_progressions).items()}
            if section_phrase_spans:
                meta["section_phrase_spans"] = list(section_phrase_spans)
        except Exception:
            pass
        try:
            from composition.evaluation import evaluate_song, quality_report

            total_bars = int(sum(int(s.bars) for s in sections)) if sections else None
            meta["metrics"] = evaluate_song(events, beats_per_bar=4.0, bars=total_bars).to_dict()
            meta["quality_report"] = quality_report(
                events,
                section_roles=[str(seq[i]) if i < len(seq) else "" for i in range(len(sections))],
                section_bars=[int(s.bars) for s in sections],
                metadata=meta,
                beats_per_bar=4.0,
                bars=total_bars,
            )
        except Exception:
            pass
        meta["section_emotions"] = [canonical_emotion_name(str(s.emotion_name)) for s in sections]
        try:
            roles = []
            roots = []
            for i, s in enumerate(list(sections)):
                roles.append(seq[i] if i < len(seq) else (seq[-1] if seq else "neutral"))
                roots.append(int(s.root_note))
            meta["section_roles"] = list(roles)
            meta["section_roots"] = list(roots)
            # Modulation heuristic: did the final chorus ("b") lift relative to earlier chorus?
            b_idx = [i for i, r in enumerate(roles) if r == "b"]
            if len(b_idx) >= 2:
                delta = int(roots[b_idx[-1]]) - int(roots[b_idx[0]])
                meta["modulation_lift_semitones"] = int(delta)
                meta["modulation_lift_applied"] = bool(abs(int(delta)) >= 1)
            else:
                meta["modulation_lift_semitones"] = 0
                meta["modulation_lift_applied"] = False
        except Exception:
            pass
        try:
            if song_blueprint is not None:
                meta["song_blueprint"] = {
                    "form_mode": str(getattr(song_blueprint, "form_mode", form) or form),
                    "section_roles": [str(getattr(x, "section_role", "") or "") for x in song_blueprint_sections],
                    "motif_stages": [str(getattr(x, "motif_stage", "") or "") for x in song_blueprint_sections],
                    "cadence_styles": [str(getattr(x, "cadence_style", "") or "") for x in song_blueprint_sections],
                    "harmony_hints": [str(getattr(x, "harmony_function_hint", "") or "") for x in song_blueprint_sections],
                }
        except Exception:
            pass
        if motif_development_sections:
            meta["motif_development"] = list(motif_development_sections)
            try:
                from composition.evaluation import quality_report

                total_bars = int(sum(int(s.bars) for s in sections)) if sections else None
                meta["quality_report"] = quality_report(
                    events,
                    section_roles=list(meta.get("section_roles", []) or [str(seq[i]) if i < len(seq) else "" for i in range(len(sections))]),
                    section_bars=[int(s.bars) for s in sections],
                    metadata=meta,
                    beats_per_bar=4.0,
                    bars=total_bars,
                )
            except Exception:
                pass
        if section_signatures:
            meta["section_signatures"] = list(section_signatures)
        out = SongRender(sections=list(sections), events=events, tempo_map=tempo_map, metadata=meta)
        if _old_py_random_state is not None:
            try:
                random.setstate(_old_py_random_state)
            except Exception:
                pass
        if _old_config_state:
            try:
                from audiogen_core.config import CONFIG

                for k, v in _old_config_state.items():
                    setattr(CONFIG.composition, k, v)
            except Exception:
                pass
        return out

    def generate_song_best_of_k(
        self,
        sections: Sequence[SongSectionSpec],
        *,
        base_tempo_bpm: float = 70.0,
        arrangement_form: str = "default",
        seed: Optional[int] = None,
        k: int = 1,
        time_budget_s: Optional[float] = None,
        closed_loop: bool = False,
        mix_goal: str = "club",
    ) -> SongRender:
        """
        Generate K candidate full-song renders (varying seed) and return the best-scoring one.

        Scoring uses the lightweight metrics in `composition.evaluation`.
        """
        rerank_on = resolve_config("composition", "whole_song_rerank_enabled", True, bool)
        kk = 1 if not rerank_on else max(1, int(k))
        if kk == 1 and not closed_loop:
            return self.generate_song(
                sections,
                base_tempo_bpm=base_tempo_bpm,
                arrangement_form=arrangement_form,
                seed=seed,
            )

        try:
            from composition.evaluation import score_song  # noqa: F401
        except Exception:
            # If evaluation can't be imported, fall back to deterministic first candidate.
            song = self.generate_song(
                sections,
                base_tempo_bpm=base_tempo_bpm,
                arrangement_form=arrangement_form,
                seed=seed,
            )
            try:
                if song.metadata is None:
                    song.metadata = {}
                song.metadata["picked_by"] = "best_of_k"
                song.metadata["picked_k"] = int(kk)
                song.metadata["picked_k_actual"] = 1
                if time_budget_s is not None:
                    song.metadata["picked_time_budget_s"] = float(time_budget_s)
            except Exception:
                pass
            return song


        best: Optional[SongRender] = None
        best_score: Optional[float] = None
        tried = 0

        start_t = None
        budget = None
        try:
            if time_budget_s is not None:
                budget = float(time_budget_s)
        except Exception:
            budget = None
        if budget is not None:
            budget = max(0.0, float(budget))
            start_t = __import__("time").time()

        for i in range(kk):
            # Optional wall-clock budget (after at least one candidate).
            if budget is not None and start_t is not None and i >= 1:
                try:
                    if (__import__("time").time() - float(start_t)) >= float(budget) - 1e-9:
                        break
                except Exception:
                    pass
            s_i = (int(seed) + int(i) if seed is not None else None)
            cand = self.generate_song(
                sections,
                base_tempo_bpm=base_tempo_bpm,
                arrangement_form=arrangement_form,
                seed=s_i,
            )
            tried += 1
            score, details = self._score_candidate_song(cand, arrangement_form=arrangement_form)

            # Save candidate metrics into metadata for debugging.
            try:
                if cand.metadata is None:
                    cand.metadata = {}
                cand.metadata["candidate_k"] = int(kk)
                cand.metadata["candidate_index"] = int(i)
                cand.metadata["candidate_score"] = float(score)
                cand.metadata["candidate_metrics"] = dict(details)
            except Exception:
                pass

            try:
                emo0 = str((cand.sections[0].emotion_name if cand.sections else "") or "")
                self._log_rerank_candidate_row(
                    emotion=emo0,
                    seed=int(s_i) if s_i is not None else 0,
                    candidate_index=int(i),
                    score=float(score),
                    details=dict(details),
                    metadata=dict(cand.metadata or {}),
                )
            except Exception:
                pass

            if best is None or best_score is None or score > best_score:
                best = cand
                best_score = float(score)

        assert best is not None
        try:
            if best.metadata is None:
                best.metadata = {}
            best.metadata["picked_by"] = "best_of_k"
            best.metadata["picked_k"] = int(kk)
            best.metadata["picked_k_actual"] = int(tried)
            if budget is not None:
                best.metadata["picked_time_budget_s"] = float(budget)
            best.metadata["picked_score"] = float(best_score if best_score is not None else 0.0)
        except Exception:
            pass
        # Optional closed-loop self-evaluation: gently retune composition knobs
        # based on recent generated-song quality metrics.
        try:
            from audiogen_core.config import CONFIG
            from composition.evaluation_auto_tune import maybe_auto_tune_from_render
            tune_info = maybe_auto_tune_from_render(CONFIG, dict(best.metadata or {}))
            if isinstance(tune_info, dict):
                if best.metadata is None:
                    best.metadata = {}
                best.metadata["self_eval_autotune"] = dict(tune_info)
        except Exception as e:
            logger.debug("maybe_auto_tune_from_render failed: %s", e, exc_info=True)

        # Phase 11 closed-loop self-correction loop
        if closed_loop:
            try:
                render_song_to_wav_file = getattr(__import__("audio.render_to_wav", fromlist=["render_song_to_wav_file"]), "render_song_to_wav_file")
                analyze_rendered_wav = getattr(__import__("audio.auto_analyze", fromlist=["analyze_rendered_wav"]), "analyze_rendered_wav")
                from composition.song_rerank_model import append_audio_rerank_row
                from pathlib import Path
                
                temp_dir = Path("tmp").resolve()
                temp_dir.mkdir(parents=True, exist_ok=True)
                
                logger.info("Closed-loop: rendering candidate to WAV for analysis...")
                wav_path = render_song_to_wav_file(best, export_dir=temp_dir, name_prefix="cl_temp")
                
                logger.info("Closed-loop: analyzing rendered WAV...")
                report = analyze_rendered_wav(wav_path, mix_goal=mix_goal)
                
                flags_list = [f.get("label") for f in report.get("flags", []) if f.get("label")]
                logger.info("Closed-loop: analysis found flags: %s", flags_list)
                
                target_flags = {"Heavy sub", "Low dynamics", "Low presence", "Frequency masking"}
                triggered = [f for f in flags_list if f in target_flags]
                
                final_metrics = report.get("metrics") or {}
                
                if triggered:
                    logger.info("Closed-loop: target flags triggered: %s. Regenerating song...", triggered)
                    new_song = self.generate_song(
                        sections,
                        base_tempo_bpm=base_tempo_bpm,
                        arrangement_form=arrangement_form,
                        seed=seed,
                        feedback_constraints={"flags": flags_list},
                    )
                    
                    logger.info("Closed-loop: rendering regenerated song to WAV...")
                    new_wav_path = render_song_to_wav_file(new_song, export_dir=temp_dir, name_prefix="cl_temp_regen")
                    
                    logger.info("Closed-loop: analyzing regenerated WAV...")
                    new_report = analyze_rendered_wav(new_wav_path, mix_goal=mix_goal)
                    new_flags = [f.get("label") for f in new_report.get("flags", []) if f.get("label")]
                    logger.info("Closed-loop: regenerated song flags: %s", new_flags)
                    
                    best = new_song
                    final_metrics = new_report.get("metrics") or {}
                    
                    if best.metadata is None:
                        best.metadata = {}
                    best.metadata["closed_loop_regenerated"] = True
                    best.metadata["closed_loop_flags_before"] = flags_list
                    best.metadata["closed_loop_flags_after"] = new_flags
                    
                    try:
                        new_wav_path.unlink()
                    except Exception:
                        pass
                else:
                    logger.info("Closed-loop: no target flags triggered. Keeping original composition.")
                    if best.metadata is None:
                        best.metadata = {}
                    best.metadata["closed_loop_regenerated"] = False
                    best.metadata["closed_loop_flags_before"] = flags_list
                    best.metadata["closed_loop_flags_after"] = flags_list
                
                logger.info("Closed-loop: appending audio features to rerank dataset...")
                append_audio_rerank_row(best, final_metrics)
                
                try:
                    wav_path.unlink()
                except Exception:
                    pass
            except Exception as e:
                logger.exception("Closed-loop execution failed: %s", e)

        return best
