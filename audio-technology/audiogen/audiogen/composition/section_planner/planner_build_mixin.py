# composition/section_planner/planner_build_mixin.py
# ---------------------------------------------------------------------------
# SectionPlanner mixin: the core per-section build orchestration
# (_build_section_once, build_section). Split out of planner.py (see
# planner.py for the assembled class).
# ---------------------------------------------------------------------------
import logging
import random
from typing import Any, Dict, List, Optional, Tuple

from audiogen_core.config import resolve_config
from audiogen_core.composition_runtime_flags import (
    phrase_length_bars_clamped,
    tension_trajectory_params,
)
from midi.midi_range_limiter import RANGE_LIMITER

from ..section_plan import SectionPlan
from .build_context import snapshot_section_build_from_config
from .scale_setup import apply_derived_global_scale
from .section_sampling import run_best_of_k_section_build
from .timeline import _make_texture_by_bar, _make_timeline_targets

logger = logging.getLogger(__name__)


class _PlannerBuildMixin:
    """Per-section build orchestration (_build_section_once, build_section)."""

    def _build_section_once(
        self,
        *,
        emotion,
        root_note: int,
        bars: int,
        key_changes: Optional[List[Tuple[int, int]]],
        temperature: float,
        target_notes_per_bar: float,
        melody_style: str,
        humanization_scale: float,
        chord_progression: Optional[List[str]],
        melody_styles: Optional[List[Tuple[int, str]]],
        section_index: int = 0,
    ) -> List[Tuple]:
        # Previous build_section body moved here (no best-of-K loop).
        owner = self.owner
        if not emotion:
            return []

        plan = SectionPlan(emotion=emotion, root_note=root_note, bars=bars)

        curve = owner.arrangement_policy.arrangement_curve(section_index, emotion)
        role = owner.arrangement_policy.section_role(section_index)
        # Next-role hint for cadence planning (used by ChordPlanner).
        try:
            seq = owner.arrangement_policy._FORM_SEQUENCES.get(owner.arrangement_policy.form_mode) or owner.arrangement_policy._FORM_SEQUENCES["default"]
            nxt = None
            if isinstance(seq, (list, tuple)) and seq:
                i = int(section_index) + 1
                if 0 <= i < len(seq):
                    nxt = str(seq[i])
            # Realtime form scheduler can override the next role (continuous looping).
            try:
                hctx = getattr(owner, "_emotion_transition_handoff_ctx", None) or {}
                if isinstance(hctx, dict):
                    rn = str(hctx.get("rt_next_section_role", "") or "").strip()
                    if rn:
                        nxt = rn
            except Exception:
                pass
            setattr(owner, "_next_section_role_hint", str(nxt or ""))
        except Exception:
            try:
                setattr(owner, "_next_section_role_hint", "")
            except Exception:
                pass
        try:
            plan.section_index = int(section_index)
        except Exception:
            plan.section_index = 0
        try:
            plan.section_role = str(role or "")
        except Exception:
            plan.section_role = ""
        # Precompute shared per-bar targets (used by multiple layers).
        try:
            plan.timeline_targets = _make_timeline_targets(
                str(role),
                int(bars),
                dict(curve),
                emotion=emotion,
                next_role=str(getattr(owner, "_next_section_role_hint", "") or ""),
            )
        except Exception:
            plan.timeline_targets = None
        bp_apply = resolve_config("composition", "song_blueprint_apply_targets_enabled", True, bool)
        bp_strength = resolve_config("composition", "song_blueprint_target_strength", 0.72, float)
        if bp_apply and isinstance(plan.timeline_targets, dict):
            try:
                bp_sec = getattr(owner, "_current_song_blueprint_section", None)
                plan.timeline_targets, curve = self._apply_song_blueprint_targets(
                    dict(plan.timeline_targets),
                    curve=dict(curve),
                    section_blueprint=bp_sec,
                    strength=float(bp_strength),
                )
                setattr(plan, "song_blueprint_section", bp_sec)
                # Expose compact hints for downstream modules (harmony/motif).
                setattr(owner, "_song_blueprint_cadence_style", str(getattr(bp_sec, "cadence_style", "") or ""))
                setattr(owner, "_song_blueprint_motif_stage", str(getattr(bp_sec, "motif_stage", "") or ""))
                setattr(owner, "_song_blueprint_harmony_hint", str(getattr(bp_sec, "harmony_function_hint", "") or ""))
            except Exception:
                pass
        payoff_on = resolve_config("composition", "final_chorus_payoff_enabled", True, bool)
        payoff_strength = resolve_config("composition", "final_chorus_payoff_strength", 0.72, float)
        if payoff_on and isinstance(plan.timeline_targets, dict):
            try:
                payoff_state = self._resolve_final_chorus_payoff_state(
                    owner,
                    role=str(role),
                    section_index=int(section_index),
                    form_section_count=int(owner.arrangement_policy.form_section_count()),
                )
                plan.timeline_targets = self._apply_final_chorus_payoff_targets(
                    dict(plan.timeline_targets),
                    payoff_state=dict(payoff_state),
                    strength=float(payoff_strength),
                )
            except Exception:
                pass

        # Phrase spans: higher-level phrase windows for motif scheduling + debugging.
        try:
            phrase_len = phrase_length_bars_clamped(1, 16)
        except Exception:
            phrase_len = 4
        phrase_len = max(1, min(16, int(phrase_len)))
        try:
            bpb = float(getattr(plan, "beats_per_bar", 4.0) or 4.0)
        except Exception:
            bpb = 4.0
        bpb = max(1e-6, float(bpb))
        b2 = max(1, int(bars))
        total_phrases = max(1, (b2 + phrase_len - 1) // phrase_len)
        spans: List[Dict[str, Any]] = []
        for pid in range(int(total_phrases)):
            bar_start = int(pid) * int(phrase_len)
            bar_end = int(min(int(b2), (int(pid) + 1) * int(phrase_len)))
            if bar_end <= bar_start:
                continue
            # Keep role logic aligned with ChordUtils.phrase_role.
            if int(total_phrases) <= 1 or int(pid) == 0:
                pr = "opening"
            elif int(pid) == int(total_phrases) - 1:
                pr = "cadence"
            elif int(pid) % 2 == 1:
                pr = "answer"
            else:
                pr = "continuation"
            t0 = float(bar_start) * float(bpb)
            t1 = float(bar_end) * float(bpb)
            spans.append(
                {
                    "phrase_id": int(pid),
                    "start_beats": float(t0),
                    "length_beats": float(max(0.0, t1 - t0)),
                    "bar_start": int(bar_start),
                    "bar_end": int(bar_end),
                    "phrase_role": str(pr),
                }
            )
        plan.phrase_spans = spans

        # Expose per-bar target profiles for downstream planners (best-effort).
        try:
            if isinstance(plan.timeline_targets, dict):
                setattr(owner, "_section_motif_strength_profile", list(plan.timeline_targets.get("motif_strength", []) or []))
                setattr(owner, "_section_tension_profile", list(plan.timeline_targets.get("tension", []) or []))
                setattr(owner, "_section_cadence_strength_profile", list(plan.timeline_targets.get("cadence_window", []) or []))
                setattr(owner, "_section_melody_density_profile", list(plan.timeline_targets.get("melody_density", []) or []))
                setattr(
                    owner,
                    "_section_harmony_function_target_profile",
                    list(plan.timeline_targets.get("harmony_function_target_by_bar", []) or []),
                )
                plan.phrase_intent_by_bar = list(plan.timeline_targets.get("phrase_intent_by_bar", []) or [])
        except Exception:
            pass

        # ------------------------------------------------------------
        # A → A′ development: capture an A fingerprint (density contour),
        # then reuse it when we reach a_prime (single-axis variation comes
        # from role curves/register lift, while density stays familiar).
        # ------------------------------------------------------------
        try:
            seq_fb = owner.arrangement_policy._FORM_SEQUENCES.get(owner.arrangement_policy.form_mode) or owner.arrangement_policy._FORM_SEQUENCES["default"]
            first_a = next(i for i, r in enumerate(seq_fb) if str(r) == "a")
        except Exception:
            first_a = None
        try:
            if first_a is not None and int(section_index) == int(first_a) and str(role) == "a":
                if getattr(owner, "_a_fingerprint", None) is None and isinstance(plan.timeline_targets, dict):
                    owner._a_fingerprint = {
                        "melody_density": list(plan.timeline_targets.get("melody_density", []) or []),
                    }
        except Exception:
            pass
        try:
            if str(role) == "a_prime" and isinstance(plan.timeline_targets, dict):
                fp = getattr(owner, "_a_fingerprint", None)
                if isinstance(fp, dict):
                    md = fp.get("melody_density", None)
                    if isinstance(md, list) and md:
                        plan.timeline_targets["melody_density"] = list(md)
        except Exception:
            pass

        # Emotion handoff smoothing: when the realtime player queues an emotion change,
        # it passes a handoff context containing the previous emotion name. Blend the
        # *per-bar targets* for the first N bars so the composition morphs rather than
        # hard-jumping to a totally new density/tension profile.
        blend_bars = resolve_config("composition", "transition_blend_bars", 0, int)
        blend_bars = max(0, min(int(bars), int(blend_bars)))
        if blend_bars >= 2 and isinstance(plan.timeline_targets, dict):
            try:
                hctx = getattr(owner, "_emotion_transition_handoff_ctx", None) or {}
                prev_name = str(hctx.get("previous_emotion_name", "") or "").strip().lower()
            except Exception:
                prev_name = ""
            if prev_name and prev_name != str(getattr(emotion, "name", "") or "").strip().lower():
                try:
                    from data.music_data import EMOTION_BY_NAME

                    prev_emotion = EMOTION_BY_NAME.get(prev_name)
                except Exception:
                    prev_emotion = None
                if prev_emotion is not None:
                    try:
                        prev_curve = owner.arrangement_policy.arrangement_curve(section_index, prev_emotion)
                        prev_targets = _make_timeline_targets(
                            str(role),
                            int(bars),
                            dict(prev_curve),
                            emotion=prev_emotion,
                        )
                    except Exception:
                        prev_targets = None

                    def _smoothstep01(x: float) -> float:
                        x = 0.0 if x < 0.0 else 1.0 if x > 1.0 else float(x)
                        return float(x * x * (3.0 - 2.0 * x))

                    def _blend_series(prev: list[float], new: list[float], n: int) -> list[float]:
                        out = list(new)
                        m = min(len(prev), len(new), int(n))
                        if m <= 0:
                            return out
                        # Blend weight ramps from 0 -> 1 over the first n bars.
                        # Bar 0 stays very close to previous targets; by bar n-1 it's close to new.
                        denom = float(max(1, int(n) - 1))
                        for i in range(m):
                            w = _smoothstep01(float(i) / denom)
                            out[i] = float((1.0 - w) * float(prev[i]) + w * float(new[i]))
                        return out

                    if isinstance(prev_targets, dict):
                        for k in ("melody_density", "chord_rhythm", "motif_strength", "tension"):
                            try:
                                p = list(prev_targets.get(k, []) or [])
                                n = list(plan.timeline_targets.get(k, []) or [])
                            except Exception:
                                p, n = [], []
                            if p and n:
                                plan.timeline_targets[k] = _blend_series(p, n, blend_bars)

        # ------------------------------------------------------------------
        # Realtime continuity: gently bias tension + motif targets across looped sections.
        # This avoids the "reset every section" feel in realtime mode.
        # ------------------------------------------------------------------
        try:
            hctx = getattr(owner, "_emotion_transition_handoff_ctx", None) or {}
        except Exception:
            hctx = {}
        if isinstance(plan.timeline_targets, dict) and isinstance(hctx, dict):
            # Realtime role scheduler intent: contrast bridges and recap tags.
            try:
                rt_role = str(hctx.get("rt_section_role", "") or "").strip().lower()
            except Exception:
                rt_role = ""
            try:
                rt_special = str(hctx.get("rt_special_event", "") or "").strip().lower()
            except Exception:
                rt_special = ""
            try:
                recap_intent = bool(hctx.get("rt_recap_intent", False))
            except Exception:
                recap_intent = False

            # Cheap role-aware target shaping (keeps CPU flat, but makes form audible).
            # - contrast_bridge: reduce motif pressure, slightly increase motion/tension
            # - recap_intent/tag: increase motif pressure, slightly stabilize harmony
            if recap_intent or rt_special == "tag_recap" or rt_role == "tag":
                try:
                    ms = list(plan.timeline_targets.get("motif_strength", []) or [])
                except Exception:
                    ms = []
                if ms:
                    plan.timeline_targets["motif_strength"] = [
                        float(max(0.0, min(2.0, float(v) * 1.18))) for v in ms
                    ]
                try:
                    cr = list(plan.timeline_targets.get("chord_rhythm", []) or [])
                except Exception:
                    cr = []
                if cr:
                    plan.timeline_targets["chord_rhythm"] = [
                        float(max(0.35, min(2.0, float(v) * 0.92))) for v in cr
                    ]
            elif rt_special == "contrast_bridge" or rt_role == "a_prime":
                try:
                    ms = list(plan.timeline_targets.get("motif_strength", []) or [])
                except Exception:
                    ms = []
                if ms:
                    plan.timeline_targets["motif_strength"] = [
                        float(max(0.0, min(2.0, float(v) * 0.82))) for v in ms
                    ]
                try:
                    cr = list(plan.timeline_targets.get("chord_rhythm", []) or [])
                except Exception:
                    cr = []
                if cr:
                    plan.timeline_targets["chord_rhythm"] = [
                        float(max(0.35, min(2.0, float(v) * 1.08))) for v in cr
                    ]
                try:
                    t = list(plan.timeline_targets.get("tension", []) or [])
                except Exception:
                    t = []
                if t:
                    plan.timeline_targets["tension"] = [
                        float(max(0.0, min(1.35, float(v) * 1.06))) for v in t
                    ]

            try:
                loop_it = int(hctx.get("loop_iteration", 0) or 0)
            except Exception:
                loop_it = 0
            try:
                recent_peak = hctx.get("recent_peak_tension", None)
                recent_peak = float(recent_peak) if recent_peak is not None else None
            except Exception:
                recent_peak = None
            try:
                age = hctx.get("motif_statement_age_sections", None)
                age = int(age) if age is not None else None
            except Exception:
                age = None

            # 4-step loop phase: build -> peak -> release -> settle.
            # Configurable arc length (default 6): triangle-shaped build -> peak -> release.
            arc_len = resolve_config("composition", "realtime_tension_arc_length", 6, int)
            arc_len = max(2, min(32, int(arc_len)))
            phase = int(loop_it) % int(arc_len) if int(loop_it) >= 0 else 0
            denom = float(max(1, int(arc_len) - 1))
            prog = float(phase) / denom  # 0..1
            arc = 1.0 - abs(2.0 * float(prog) - 1.0)  # triangle 0..1..0
            arc = max(0.0, min(1.0, float(arc)))

            # Map arc to multipliers (tension + density + harmonic motion).
            tm = 0.90 + 0.25 * float(arc)          # 0.90..1.15
            mdm = 0.85 + 0.35 * float(arc)         # 0.85..1.20
            crm = 0.85 + 0.30 * float(arc)         # 0.85..1.15

            # If we recently peaked very high, favor release on the next section.
            if recent_peak is not None and recent_peak >= 1.05 and arc >= 0.85:
                tm *= 0.95
                mdm *= 0.97
                crm *= 0.97

            try:
                t = list(plan.timeline_targets.get("tension", []) or [])
            except Exception:
                t = []
            if t and abs(float(tm) - 1.0) > 1e-6:
                plan.timeline_targets["tension"] = [float(max(0.0, min(1.35, float(v) * float(tm)))) for v in t]

            # Drive density + harmonic motion with the same arc (keeps sections feeling like they progress).
            try:
                md = list(plan.timeline_targets.get("melody_density", []) or [])
            except Exception:
                md = []
            if md and abs(float(mdm) - 1.0) > 1e-6:
                plan.timeline_targets["melody_density"] = [float(max(0.15, min(2.25, float(v) * float(mdm)))) for v in md]
            try:
                cr = list(plan.timeline_targets.get("chord_rhythm", []) or [])
            except Exception:
                cr = []
            if cr and abs(float(crm) - 1.0) > 1e-6:
                plan.timeline_targets["chord_rhythm"] = [float(max(0.35, min(2.0, float(v) * float(crm)))) for v in cr]

            # Motif pacing: if we haven't stated the theme in a while, slightly increase motif strength targets.
            if age is not None and int(age) >= 3:
                boost = 1.0 + 0.12 * min(1.0, float(int(age) - 2) / 4.0)
                try:
                    ms = list(plan.timeline_targets.get("motif_strength", []) or [])
                except Exception:
                    ms = []
                if ms:
                    plan.timeline_targets["motif_strength"] = [float(max(0.0, min(2.0, float(v) * float(boost)))) for v in ms]

            # Energy lane: if scheduler exported rt_energy, use it to gently scale
            # global density/motion (keeps long-range arcs audible without extra CPU).
            try:
                e = hctx.get("rt_energy", None)
                e = float(e) if e is not None else None
            except Exception:
                e = None
            if e is not None:
                e = max(0.0, min(1.0, float(e)))
                dens_m = 0.88 + 0.35 * float(e)
                ten_m = 0.92 + 0.28 * float(e)
                try:
                    md = list(plan.timeline_targets.get("melody_density", []) or [])
                except Exception:
                    md = []
                if md:
                    plan.timeline_targets["melody_density"] = [float(max(0.15, min(2.25, float(v) * float(dens_m)))) for v in md]
                try:
                    cr = list(plan.timeline_targets.get("chord_rhythm", []) or [])
                except Exception:
                    cr = []
                if cr:
                    plan.timeline_targets["chord_rhythm"] = [float(max(0.35, min(2.0, float(v) * float(dens_m)))) for v in cr]
                try:
                    t = list(plan.timeline_targets.get("tension", []) or [])
                except Exception:
                    t = []
                if t:
                    plan.timeline_targets["tension"] = [float(max(0.0, min(1.35, float(v) * float(ten_m)))) for v in t]

        if isinstance(plan.timeline_targets, dict):
            try:
                plan.timeline_targets = self._apply_arrangement_energy_matrix_targets(
                    dict(plan.timeline_targets),
                    section_role=str(role),
                    section_index=int(section_index),
                    form_section_count=int(owner.arrangement_policy.form_section_count()),
                )
            except Exception:
                pass
            try:
                plan.timeline_targets, curve = self._apply_whole_song_director(
                    dict(plan.timeline_targets),
                    dict(curve),
                    owner=owner,
                    section_role=str(role),
                    section_index=int(section_index),
                    form_section_count=int(owner.arrangement_policy.form_section_count()),
                )
            except Exception:
                pass

        # Texture script: computed once per section and used during finalization + debugging.
        try:
            setattr(
                plan,
                "texture_by_bar",
                _make_texture_by_bar(
                    section_role=str(role),
                    bars=int(bars),
                    timeline_targets=(plan.timeline_targets if isinstance(plan.timeline_targets, dict) else None),
                    handoff_ctx=(getattr(owner, "_emotion_transition_handoff_ctx", None) or {}),
                    next_role=str(getattr(owner, "_next_section_role_hint", "") or ""),
                ),
            )
        except Exception:
            try:
                setattr(plan, "texture_by_bar", [])
            except Exception:
                pass
        tension = list((plan.timeline_targets or {}).get("tension", []) or [])
        tension_avg = (
            sum(float(v) for v in tension) / max(1, len(tension)) if tension else 1.0
        )
        tension_avg = max(0.0, min(1.25, float(tension_avg)))
        with owner.snapshot_settings(
            "extension_prob",
            "interchange_prob",
            "secondary_dominant_prob",
            "use_modal_interchange",
            "use_secondary_dominants",
        ):
            ext0, int0, sec0 = owner.extension_prob, owner.interchange_prob, owner.secondary_dominant_prob
            if role == "b":
                # Chorus-only modal interchange allowlist. Was volatile/high-arousal
                # negative emotions only (anger/disgust/disapproval/annoyance/fear/
                # nervousness) plus surprise/excitement — added 2026-07-02 (see
                # docs/AUDIOGEN_COMPOSITION_PLAN.md item 10): the "sad" cluster
                # (grief/sadness/remorse/disappointment) was excluded despite borrowed
                # iv/bVI/bIII being one of the most standard devices for melancholic
                # color in real harmony — arguably more idiomatic there than for
                # surprise/excitement, which were already allowed.
                owner.use_modal_interchange = owner.use_modal_interchange and ((getattr(plan.emotion, "name", "") or "").strip().lower() in {"anger", "disgust", "disapproval", "annoyance", "surprise", "excitement", "fear", "nervousness", "grief", "sadness", "remorse", "disappointment"})
                owner.use_secondary_dominants = True
                owner.extension_prob = min(0.92, float(ext0) * 1.10)
                owner.interchange_prob = min(0.52, float(int0) * 0.92)
                owner.secondary_dominant_prob = min(0.48, float(sec0) * 1.08)
            elif role == "a_prime":
                rng = getattr(owner, "rng", random)
                owner.use_modal_interchange = owner.use_modal_interchange or (rng.random() < 0.35)
                owner.use_secondary_dominants = owner.use_secondary_dominants or (rng.random() < 0.25)
                owner.extension_prob = min(0.9, float(ext0) * 1.1)
                owner.interchange_prob = min(0.75, float(int0) * 1.15)
                owner.secondary_dominant_prob = min(0.6, float(sec0) * 1.1)
            elif role == "pre_chorus":
                owner.use_modal_interchange = False
                owner.use_secondary_dominants = True
                owner.extension_prob = min(0.88, float(ext0) * 1.02)
                owner.interchange_prob = 0.0
                owner.secondary_dominant_prob = min(0.55, float(sec0) * 1.18)
            elif role == "tag":
                owner.extension_prob = max(0.0, float(ext0) * 0.82)
                owner.interchange_prob = max(0.0, float(int0) * 0.75)
                owner.secondary_dominant_prob = max(0.0, float(sec0) * 0.65)
            elif role in {"intro", "outro"}:
                owner.extension_prob = max(0.0, float(ext0) * 0.75)
                owner.interchange_prob = max(0.0, float(int0) * 0.7)
                owner.secondary_dominant_prob = max(0.0, float(sec0) * 0.7)

            hc = max(0.55, min(1.45, float(curve.get("harmonic_color_mult", 1.0))))
            # Tension pushes harmonic color (extensions/secondary dom) modestly.
            t_enabled, t_strength = tension_trajectory_params()
            if t_enabled and t_strength > 1e-6:
                # Map avg tension to a bounded color multiplier ~ [0.88..1.18]
                hc *= (0.88 + 0.30 * float(tension_avg)) ** float(t_strength)

            # 16-bar development scheduling: allow a bit more color in the section overall,
            # but tighten toward cadence (keeps endings resolved).
            dev_enabled = resolve_config("composition", "harmony_development_enabled", True, bool)
            dev_strength = resolve_config("composition", "harmony_development_strength", 0.25, float)
            cad_tight = resolve_config("composition", "harmony_cadence_tighten_strength", 0.35, float)
            dev_strength = max(0.0, min(1.0, float(dev_strength)))
            cad_tight = max(0.0, min(1.0, float(cad_tight)))
            if dev_enabled and int(bars) == 16 and (dev_strength > 1e-6 or cad_tight > 1e-6):
                ab = float(curve.get("ab_development_strength", 0.15) or 0.15)
                ab = max(0.0, min(0.5, float(ab)))
                # Development lift is modest and role-shaped via curve.
                hc *= (1.0 + 0.55 * float(dev_strength) * float(ab))
                # Tighten if cadence window is strong at the end.
                try:
                    cw = list((plan.timeline_targets or {}).get("cadence_window", []) or [])
                    cad_level = 0.0
                    if cw and len(cw) >= 2:
                        cad_level = 0.5 * float(cw[-1]) + 0.5 * float(cw[-2])
                    cad_level = max(0.0, min(1.0, float(cad_level)))
                except Exception:
                    cad_level = 0.0
                if cad_level > 1e-6:
                    hc *= (1.0 - 0.35 * float(cad_tight) * float(cad_level))

            hc = max(0.45, min(1.65, float(hc)))
            owner.extension_prob = max(0.0, min(0.98, float(owner.extension_prob) * hc))
            owner.interchange_prob = max(0.0, min(0.95, float(owner.interchange_prob) * hc))
            owner.secondary_dominant_prob = max(0.0, min(0.9, float(owner.secondary_dominant_prob) * hc))

            # Neutral should stay strictly diatonic by default (hybrid target).
            # Avoid modal interchange / secondary dominants which can read "out of key".
            try:
                if (getattr(plan.emotion, "name", "") or "").strip().lower() == "neutral":
                    owner.use_modal_interchange = False
                    owner.use_secondary_dominants = False
                    owner.interchange_prob = 0.0
                    owner.secondary_dominant_prob = 0.0
            except Exception:
                pass

            plan = self.prepare_section_harmony(
                plan, key_changes, temperature, chord_progression, section_index=section_index
            )

        if not plan.chords:
            return []

        plan = self.prepare_section_voicing(plan)
        hctx = getattr(owner, "_emotion_transition_handoff_ctx", None)
        if (
            hctx
            and hctx.get("previous_bass_midi") is not None
            and getattr(plan, "chosen_bass", None)
            and len(plan.chosen_bass) > 0
        ):
            # Transition bridge: hold the outgoing bass anchor for the first N bars
            # after a manual emotion handoff.
            snap = getattr(self, "_active_build_snapshot", None)
            if snap is not None:
                hold_bars = max(1, int(snap.transition_bridge_hold_bars))
            else:
                hold_bars = resolve_config("composition", "transition_bridge_hold_bars", 1, int)
            hold_bars = max(1, min(int(len(plan.chosen_bass)), int(hold_bars)))
            b0 = RANGE_LIMITER.clamp_note(int(hctx["previous_bass_midi"]), 0)
            for i in range(int(hold_bars)):
                plan.chosen_bass[i] = int(b0)

        plan = self.prepare_section_events(
            plan,
            temperature,
            target_notes_per_bar,
            melody_style,
            melody_styles,
            section_index=section_index,
        )
        plan = self.finalize_section_events(plan, humanization_scale)

        rng = getattr(owner, "rng", random)
        if rng.random() < 0.05:
            owner.perf_monitor.report()

        owner._last_section_roots = list(plan.roots)
        owner._last_generation_emotion = plan.emotion
        try:
            setattr(owner, "_last_section_plan", plan)
            setattr(owner, "_last_section_motif_development", dict(getattr(plan, "motif_development", {}) or {}))
            sm = getattr(owner, "song_memory", None)
            if sm is not None and hasattr(sm, "remember_section"):
                sm.remember_section(
                    plan,
                    section_role=str(role),
                    section_index=int(section_index),
                )
        except Exception:
            pass
        # Expose debug trace for the realtime player/CLI (best-effort).
        try:
            setattr(owner, "_last_section_debug_trace_by_bar", list(getattr(plan, "debug_trace_by_bar", []) or []))
        except Exception:
            pass
        owner.register_section_memory(
            plan.chords,
            getattr(owner, "_last_generated_phrase_contours", []),
            plan.melody_events,
        )

        # Optional: write a "log sheet" of every generated note (CSV).
        enabled = resolve_config("composition", "note_log_enabled", True, bool)
        log_path = resolve_config("composition", "note_log_path", "logs/notes", str)
        console_enabled = resolve_config("composition", "note_log_console_enabled", False, bool)
        if enabled:
            try:
                from composition.note_log import NoteLogContext, format_note_dump, get_note_csv_logger

                # Determine scale intervals (global override wins, else emotion scale).
                scale_intervals = []
                try:
                    gs = getattr(owner, "global_scale", None)
                    if gs:
                        scale_intervals = list(gs)
                except Exception:
                    scale_intervals = []
                if not scale_intervals:
                    try:
                        scale_intervals = list(getattr(plan.emotion, "scale_intervals", None) or [])
                    except Exception:
                        scale_intervals = []

                try:
                    root_midi = int(plan.root_note)
                except Exception:
                    # Fallback: section root PC was set earlier; pick a C-based tonic if missing.
                    root_midi = int(getattr(owner, "_section_root_pc", 0) or 0) + 60

                try:
                    raw_seed = getattr(owner, "seed", None)
                    seed = None if raw_seed is None else int(raw_seed)
                except Exception:
                    seed = None

                ctx = NoteLogContext(
                    emotion_name=str(getattr(plan.emotion, "name", "") or ""),
                    section_index=int(section_index),
                    root_midi=int(root_midi),
                    beats_per_bar=float(getattr(plan, "beats_per_bar", 4.0) or 4.0),
                    scale_intervals=tuple(int(x) for x in list(scale_intervals or []) if isinstance(x, int) or str(x).lstrip("-").isdigit()),
                    seed=seed,
                    run_tag="realtime" if str(getattr(owner, "runtime_generation_mode", "normal") or "normal") != "offline" else "offline",
                    section_role=str(getattr(plan, "section_role", "") or ""),
                    arrangement_form=str(getattr(getattr(owner, "arrangement_policy", None), "form_mode", "") or ""),
                )

                n_rows = get_note_csv_logger(log_path).log_events(plan.events, ctx)
                if console_enabled and n_rows:
                    logger.info("Note log: wrote %d notes -> %s", int(n_rows), str(log_path))
                    dump = format_note_dump(plan.events, ctx, max_notes=96)
                    if dump:
                        logger.info("%s", str(dump))
            except Exception:
                # Best-effort only; never fail generation due to logging.
                pass

        return plan.events

    def build_section(
        self,
        emotion,
        root_note: int,
        bars: int,
        key_changes: Optional[List[Tuple[int, int]]],
        temperature: float,
        target_notes_per_bar: float,
        melody_style: str,
        humanization_scale: float,
        chord_progression: Optional[List[str]],
        melody_styles: Optional[List[Tuple[int, str]]],
        section_index: int = 0,
    ) -> List[Tuple]:
        owner = self.owner
        if not emotion:
            return []

        snap = snapshot_section_build_from_config()
        self._active_build_snapshot = snap
        try:
            # Make the section tonic/root pitch-class available to scale quantization.
            try:
                setattr(owner, "_section_root_pc", int(root_note) % 12)
            except Exception:
                pass

            apply_derived_global_scale(owner, emotion, root_note, snap)

            owner.apply_emotion_ranges_for_generation(emotion)
            owner.train_for_emotion(emotion)
            owner.melody_gen.apply_emotion_params(owner.get_emotion_melody_params(emotion))
            # Song-level climax override (docs/AUDIOGEN_COMPOSITION_PLAN.md item 13): the
            # emotion's own `enforce_climax` default (data/emotion_melody_parameters.py) was
            # just applied above and would otherwise win — 15/28 emotions default it off, and
            # even for the 13 that default it on, every section (not just one) would get the
            # phrase-level climax nudge with no single song-wide peak. Force it on specifically
            # for the one section song_generator.py designated as the song's climax (last
            # chorus-family occurrence), regardless of that emotion's own default.
            if bool(getattr(owner, "_force_song_climax_this_section", False)):
                owner.melody_gen.enforce_climax = True

            rt_mode = str(getattr(owner, "runtime_generation_mode", "normal") or "normal").strip().lower()
            effort = str(getattr(owner, "runtime_planner_effort_override", "") or "").strip().lower()
            if effort not in {"minimal", "balanced", "light", "full"}:
                effort = "minimal" if rt_mode in {"preview", "cold_preview"} else snap.realtime_planner_effort

            return run_best_of_k_section_build(
                self,
                owner=owner,
                emotion=emotion,
                root_note=root_note,
                bars=bars,
                key_changes=key_changes,
                temperature=temperature,
                target_notes_per_bar=target_notes_per_bar,
                melody_style=melody_style,
                humanization_scale=humanization_scale,
                chord_progression=chord_progression,
                melody_styles=melody_styles,
                section_index=section_index,
                snapshot=snap,
                rt_mode=rt_mode,
                effort=effort,
            )
        finally:
            try:
                self._active_build_snapshot = None
            except Exception:
                pass

