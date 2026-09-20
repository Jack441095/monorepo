# composition/section_planner/planner_harmony_voicing_mixin.py
# ---------------------------------------------------------------------------
# SectionPlanner mixin: chord-progression/harmony prep and voice-leading
# voicing prep (prepare_section_harmony, prepare_section_voicing). Split out
# of planner.py (see planner.py for the assembled class).
# ---------------------------------------------------------------------------
from typing import List, Optional, Tuple

from audiogen_core.config import resolve_config

from ..section_plan import SectionPlan
from .timeline import _make_timeline_targets


class _PlannerHarmonyVoicingMixin:
    """Section harmony + voicing preparation instance methods."""

    def prepare_section_harmony(
        self,
        plan: SectionPlan,
        key_changes: Optional[List[Tuple[int, int]]],
        temperature: float,
        chord_progression: Optional[List[str]],
        section_index: int = 0,
    ) -> SectionPlan:
        owner = self.owner
        curve = owner.arrangement_policy.arrangement_curve(section_index, plan.emotion)
        role = owner.arrangement_policy.section_role(section_index)
        form_n = owner.arrangement_policy.form_section_count()
        requested = plan.bars

        try:
            from composition.section_planner.joint_plan_stage import (
                attach_joint_plan_to_section_plan,
                integrate_joint_plan_at_harmony,
            )

            try:
                role_occ = int(owner.arrangement_policy.role_occurrence(section_index))
            except Exception:
                role_occ = 1
            try:
                sec_prog = float(section_index) / float(max(1, int(form_n) - 1))
            except Exception:
                sec_prog = 0.0
            curve, chord_progression, joint_meta = integrate_joint_plan_at_harmony(
                owner,
                plan,
                dict(curve),
                section_index=int(section_index),
                section_role=str(role),
                chord_progression=chord_progression,
                role_occurrence=int(role_occ),
                section_progress=float(sec_prog),
            )
            attach_joint_plan_to_section_plan(plan, joint_meta)
            plan.arrangement_curve = dict(curve)
        except Exception:
            pass

        # Build timeline targets early so harmony can react to the same section-level
        # density/motion intent that the melody/arp planners use later.
        try:
            plan.timeline_targets = _make_timeline_targets(
                role,
                int(requested),
                dict(curve),
                emotion=getattr(plan, "emotion", None),
            )
        except Exception:
            plan.timeline_targets = None
        payoff_on = resolve_config("composition", "final_chorus_payoff_enabled", True, bool)
        payoff_strength = resolve_config("composition", "final_chorus_payoff_strength", 0.72, float)
        if payoff_on and isinstance(plan.timeline_targets, dict):
            try:
                payoff_state = self._resolve_final_chorus_payoff_state(
                    owner,
                    role=str(role),
                    section_index=int(section_index),
                    form_section_count=int(form_n),
                )
                plan.timeline_targets = self._apply_final_chorus_payoff_targets(
                    dict(plan.timeline_targets),
                    payoff_state=dict(payoff_state),
                    strength=float(payoff_strength),
                )
            except Exception:
                pass

        # If we're generating the first chunk after a queued emotion switch, blend the
        # per-bar targets from the previous emotion into the new one for the first N bars.
        blend_bars = resolve_config("composition", "transition_blend_bars", 0, int)
        blend_bars = max(0, min(int(requested), int(blend_bars)))
        if blend_bars >= 2 and isinstance(plan.timeline_targets, dict):
            try:
                hctx = getattr(owner, "_emotion_transition_handoff_ctx", None) or {}
                prev_name = str(hctx.get("previous_emotion_name", "") or "").strip().lower()
            except Exception:
                prev_name = ""
            if prev_name and prev_name != str(getattr(plan.emotion, "name", "") or "").strip().lower():
                try:
                    from data.music_data import EMOTION_BY_NAME

                    prev_emotion = EMOTION_BY_NAME.get(prev_name)
                except Exception:
                    prev_emotion = None
                if prev_emotion is not None:
                    try:
                        prev_curve = owner.arrangement_policy.arrangement_curve(section_index, prev_emotion)
                        prev_targets = _make_timeline_targets(
                            role,
                            int(requested),
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

        if isinstance(plan.timeline_targets, dict):
            try:
                plan.timeline_targets = self._apply_arrangement_energy_matrix_targets(
                    dict(plan.timeline_targets),
                    section_role=str(role),
                    section_index=int(section_index),
                    form_section_count=int(form_n),
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
                    form_section_count=int(form_n),
                )
            except Exception:
                pass

        chord_rhythm = list((plan.timeline_targets or {}).get("chord_rhythm", []) or [])
        chord_rhythm_avg = (
            sum(float(v) for v in chord_rhythm) / max(1, len(chord_rhythm)) if chord_rhythm else 1.0
        )
        # Use chord_rhythm as a shared "harmonic motion" budget: higher => more motion/variety.
        chord_motion_mult = float(curve.get("chord_motion_mult", 1.0)) * float(chord_rhythm_avg)
        harmony_temperature_mult = float(curve.get("harmony_temperature_mult", 1.0)) * (
            0.92 + 0.16 * float(chord_rhythm_avg)
        )
        # Optional role-aware cadence strength (verse more open, chorus/outro stronger).
        cadence_strength_mult = float(curve.get("cadence_strength_mult", 1.0))
        dest_enabled = resolve_config("composition", "harmonic_destination_planner_enabled", True, bool)
        try:
            dest = (
                owner.chord_planner.section_harmonic_destination(
                    section_role=role,
                    next_role=str(getattr(owner, "_next_section_role_hint", "") or ""),
                    is_last_section=bool(int(section_index) >= max(0, int(form_n) - 1)),
                )
                if dest_enabled
                else None
            )
            setattr(owner, "_section_harmonic_destination", dict(dest or {}))
        except Exception:
            try:
                setattr(owner, "_section_harmonic_destination", {})
            except Exception:
                pass
        # Expose per-bar motif-strength to the harmony planner so it can keep hook bars stable.
        try:
            setattr(owner, "_section_motif_strength_profile", list((plan.timeline_targets or {}).get("motif_strength", []) or []))
            setattr(owner, "_section_tension_profile", list((plan.timeline_targets or {}).get("tension", []) or []))
            setattr(owner, "_section_cadence_strength_profile", list((plan.timeline_targets or {}).get("cadence_window", []) or []))
            setattr(
                owner,
                "_section_harmony_function_target_profile",
                list((plan.timeline_targets or {}).get("harmony_function_target_by_bar", []) or []),
            )
        except Exception:
            pass
        plan.chords, plan.roots = owner.harmony_manager.prepare_chord_progression(
            plan.emotion,
            plan.root_note,
            requested,
            key_changes,
            temperature,
            chord_progression,
            section_role=role,
            section_index=section_index,
            form_section_count=form_n,
            chord_motion_mult=float(chord_motion_mult),
            harmony_temperature_mult=float(harmony_temperature_mult),
            cadence_strength_mult=float(cadence_strength_mult),
        )
        if not plan.chords:
            return plan
        # Keep section length aligned with SongGenerator beat offsets (spec.bars). A shorter
        # chord list would leave the rest of the section silent in the arranged timeline.
        if len(plan.chords) < requested:
            pad_ch, pad_r = plan.chords[-1], plan.roots[-1]
            while len(plan.chords) < requested:
                plan.chords.append(pad_ch)
                plan.roots.append(pad_r)
        elif len(plan.chords) > requested:
            plan.chords = plan.chords[:requested]
            plan.roots = plan.roots[:requested]
        plan.bars = requested
        return plan

    def prepare_section_voicing(self, plan: SectionPlan) -> SectionPlan:
        owner = self.owner
        plan.chosen_bass, plan.chosen_chord, plan.chosen_melody = owner.harmony_manager.use_voice_leading(
            plan.chords, plan.roots, plan.bars, plan.beats_per_bar, plan.emotion
        )
        # If chorus-like harmony still ended up as triads/shells, enrich voicings so
        # extensions are actually audible. (Role-aware post-process; deterministic.)
        try:
            rlc = str(getattr(plan, "section_role", "") or "").strip().lower()
        except Exception:
            rlc = ""
        if rlc in {"b", "chorus", "hook", "tag"}:
            try:
                vv0 = list(getattr(plan, "chosen_chord", []) or [])
                lens0 = [len(list(row or [])) for row in vv0] if vv0 else []
                avg0 = float(sum(lens0) / max(1, len(lens0))) if lens0 else 0.0
            except Exception:
                avg0 = 0.0
            if avg0 < 3.75 and getattr(plan, "chords", None) and getattr(plan, "roots", None):
                try:
                    def _pick_intervals(sym: str):
                        try:
                            ivs = sorted(set(int(i) for i in (owner._chord_symbol_to_intervals(sym) or [])))
                        except Exception:
                            ivs = []
                        third = next((i for i in ivs if i % 12 in {3, 4}), None)
                        seventh = next((i for i in ivs if i % 12 in {10, 11}), None)
                        fifth = next((i for i in ivs if i % 12 == 7), None)
                        ninth = next((i for i in ivs if i % 12 == 2), None)
                        eleventh = next((i for i in ivs if i % 12 == 5), None)
                        thirteenth = next((i for i in ivs if i % 12 == 9), None)
                        out = [0]
                        # Prefer guide tones + upper extensions, then fifth.
                        for x in (third, seventh, ninth, eleventh, thirteenth, fifth):
                            if x is not None and x not in out:
                                out.append(int(x))
                            if len(out) >= 6:
                                break
                        return out

                    def _anchor_notes(notes: list, target_center: float) -> list:
                        out = []
                        for n in notes:
                            try:
                                x = int(n)
                            except Exception:
                                continue
                            # Shift by octaves to sit near target_center.
                            while x < target_center - 7:
                                x += 12
                            while x > target_center + 7:
                                x -= 12
                            out.append(int(x))
                        return sorted(set(out))

                    enriched = []
                    for i, (sym, rt) in enumerate(zip(list(plan.chords), list(plan.roots))):
                        base = list(vv0[i]) if i < len(vv0) else []
                        center = (sum(base) / len(base)) if base else float(int(rt) + 12)
                        ivs = _pick_intervals(str(sym))
                        cand = [int(rt) + int(iv) for iv in ivs]
                        cand = _anchor_notes(cand, float(center))
                        # Fallback: if we somehow still have <4, pull from full chord tones.
                        # (We still cap overall polyphony below.)
                        if len(cand) < 4:
                            try:
                                full = list(owner._chord_symbol_to_notes(str(sym), int(rt)) or [])
                            except Exception:
                                full = []
                            full = _anchor_notes(full, float(center))
                            for n in full:
                                if n not in cand:
                                    cand.append(int(n))
                                if len(cand) >= 6:
                                    break
                        enriched.append(sorted(set(int(n) for n in (cand[:6] if len(cand) > 6 else cand))))
                    if enriched and len(enriched) == len(vv0):
                        plan.chosen_chord = enriched

                except Exception:
                    pass
        return plan

