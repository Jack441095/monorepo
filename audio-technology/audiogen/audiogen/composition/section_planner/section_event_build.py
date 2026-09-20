"""Section event generation (Markov melody/arp, hooks, counters)."""

from __future__ import annotations
from audiogen_core.config import resolve_config
try:
    from data.arp_style_table import arp_style_for_emotion, pick_style_value
except Exception:
    arp_style_for_emotion = None
    pick_style_value = None

import logging
import random
from typing import Any, Dict, List, Optional, Tuple

from audiogen_core.composition_runtime_flags import (
    phrase_length_bars_clamped,
)
from midi.midi_range_limiter import RANGE_LIMITER

from ..harmonic_plan import HarmonicPlan
from ..melody_arp_octave_resolve import (
    resolve_melody_octaves_vs_arp_clashes,
    resolve_melody_unisons_vs_arp_by_interval,
)
from ..section_plan import SectionPlan
from .build_context import comp_proxy_for_voicing
from .chorus_hook_blueprint import (
    _apply_bright_chorus_payoff_to_melody,
    _apply_chorus_hook_blueprint_to_arp_plan,
    _apply_chorus_hook_blueprint_to_melody,
    _masking_focus_strength_for_emotion,
    _select_seeded_chorus_hook_blueprint,
)
from .lead_texture_guards import (
    _arp_bed_suppressed_for_section,
    _perceptual_scale_emotion,
    _stabilize_low_flow_lead_harmony,
    _supportive_arp_follow_lead,
)
from .chorus_hook_memory import (
    apply_chorus_hook_memory as _apply_chorus_hook_memory,
    capture_chorus_hook_memory as _capture_chorus_hook_memory,
)
from .counter_melody_stage import run_counter_melody_stage
from .timeline import _make_timeline_targets, _timeline_shape

logger = logging.getLogger(__name__)

if False:  # TYPE_CHECKING
    pass

def prepare_section_events(
    planner: Any,
    plan: SectionPlan,
    temperature: float,
    target_notes_per_bar: float,
    melody_style: str,
    melody_styles: Optional[List[Tuple[int, str]]],
    section_index: int = 0,
) -> SectionPlan:
    owner = planner.owner

    curve = owner.arrangement_policy.arrangement_curve(section_index, plan.emotion)
    section_role = owner.arrangement_policy.section_role(section_index)
    if resolve_config("composition", "melody_clear_phrase_memory_each_section", True, bool):
        mg = getattr(owner, "melody_gen", None)
        pm = getattr(mg, "phrase_memory", None) if mg is not None else None
        if isinstance(pm, dict):
            pm.clear()
    payoff_on = resolve_config("composition", "final_chorus_payoff_enabled", True, bool)
    payoff_strength = resolve_config("composition", "final_chorus_payoff_strength", 0.72, float)
    if payoff_on:
        try:
            payoff_state = planner._resolve_final_chorus_payoff_state(
                owner,
                role=str(section_role),
                section_index=int(section_index),
                form_section_count=int(owner.arrangement_policy.form_section_count()),
            )
            curve = planner._apply_final_chorus_payoff_curve(
                dict(curve),
                payoff_state=dict(payoff_state),
                strength=float(payoff_strength),
            )
        except Exception:
            pass
    chorus_ref_arp: Dict[str, float] = planner._chorus_reference_arp_overrides(
        emotion_name=str(getattr(plan.emotion, "name", "") or ""),
        section_role=str(section_role or ""),
    )
    if chorus_ref_arp:
        comp = resolve_config("composition", "", None)
        strength = float(getattr(comp, "chorus_reference_arp_strength", 0.85) or 0.85) if comp is not None else 0.85
        strength = max(0.0, min(1.0, float(strength)))
        target_boost = float(getattr(comp, "chorus_reference_arp_target_boost", 1.25) or 1.25) if comp is not None else 1.25
        target_boost = max(0.7, min(2.0, float(target_boost)))
        # Apply references as a blend so existing hand-tuned per-emotion curves
        # remain the baseline and the chorus refs act as guided pull.
        try:
            if chorus_ref_arp.get("target_notes_per_bar") is not None:
                base_npb = float(curve.get("arp_target_notes_per_bar", 7.0) or 7.0)
                ref_npb = float(chorus_ref_arp.get("target_notes_per_bar", base_npb)) * float(target_boost)
                blend_npb = (1.0 - float(strength)) * float(base_npb) + float(strength) * float(ref_npb)
                curve["arp_target_notes_per_bar"] = float(max(2.0, min(16.0, float(blend_npb))))
        except Exception:
            pass
        try:
            if chorus_ref_arp.get("grid") is not None:
                base_grid = float(curve.get("arp_grid", 0.25) or 0.25)
                ref_grid = float(chorus_ref_arp.get("grid", base_grid))
                blend_grid = (1.0 - float(strength)) * float(base_grid) + float(strength) * float(ref_grid)
                curve["arp_grid"] = float(max(0.125, min(2.0, float(blend_grid))))
        except Exception:
            pass
    chorus_ref_melody: Dict[str, float] = planner._chorus_reference_melody_overrides(
        emotion_name=str(getattr(plan.emotion, "name", "") or ""),
        section_role=str(section_role or ""),
    )
    if chorus_ref_melody:
        comp = resolve_config("composition", "", None)
        m_strength = (
            float(getattr(comp, "chorus_reference_melody_strength", 0.70) or 0.70)
            if comp is not None
            else 0.70
        )
        m_strength = max(0.0, min(1.0, float(m_strength)))
        m_boost = (
            float(getattr(comp, "chorus_reference_melody_target_boost", 1.10) or 1.10)
            if comp is not None
            else 1.10
        )
        m_boost = max(0.7, min(2.0, float(m_boost)))

        def _blend(base: float, target: float, s: float) -> float:
            return float((1.0 - float(s)) * float(base) + float(s) * float(target))

        # Melody density fit: references are chorus-level so apply as a gentle pull.
        try:
            ref_npb = chorus_ref_melody.get("notes_per_bar")
            if ref_npb is not None:
                base_density = float(curve.get("melody_density_mult", 1.0) or 1.0)
                base_target_npb = max(1e-6, float(target_notes_per_bar))
                target_density = float(ref_npb) * float(m_boost) / float(base_target_npb)
                target_density = max(0.60, min(1.65, float(target_density)))
                curve["melody_density_mult"] = float(_blend(base_density, target_density, m_strength))

                base_total = float(curve.get("melody_total_notes_mult", 1.0) or 1.0)
                target_total = max(0.60, min(1.55, float(target_density) * 0.95))
                curve["melody_total_notes_mult"] = float(_blend(base_total, target_total, m_strength))

                base_rest = float(curve.get("markov_rest_prob_mult", 1.0) or 1.0)
                target_rest = max(0.72, min(1.35, 1.0 / max(0.55, float(target_density))))
                curve["markov_rest_prob_mult"] = float(_blend(base_rest, target_rest, m_strength))
        except Exception:
            pass

        # Motif behavior fit: higher motif strength -> stronger repetition pressure.
        try:
            motif_s = chorus_ref_melody.get("motif_strength")
            if motif_s is not None:
                ms = max(0.0, min(1.0, float(motif_s)))
                base_motif = float(curve.get("motif_prob_mult", 1.0) or 1.0)
                tgt_motif = max(0.82, min(1.45, 0.82 + 0.72 * ms))
                curve["motif_prob_mult"] = float(_blend(base_motif, tgt_motif, m_strength))

                base_repeat = float(curve.get("phrase_repeat_mult", 1.0) or 1.0)
                tgt_repeat = max(0.85, min(1.40, 0.88 + 0.62 * ms))
                curve["phrase_repeat_mult"] = float(_blend(base_repeat, tgt_repeat, m_strength))
        except Exception:
            pass
    plan.arrangement_curve = dict(curve)
    # `build_section()` already computes + blends timeline targets early (used by multiple
    # layers). Avoid overwriting here unless missing.
    if getattr(plan, "timeline_targets", None) is None:
        try:
            plan.timeline_targets = _make_timeline_targets(
                section_role,
                int(plan.bars),
                dict(curve),
                emotion=plan.emotion,
            )
        except Exception:
            plan.timeline_targets = None

    # Transition smoothing (manual emotion switches): blend first N bars of per-bar targets
    # from the previous emotion into the new emotion to reduce abrupt musical jumps.
    blend_bars = resolve_config("composition", "transition_blend_bars", 0, int)
    blend_bars = max(0, min(int(getattr(plan, "bars", 0) or 0), int(blend_bars)))
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
                        section_role,
                        int(plan.bars),
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
            plan.timeline_targets = planner._apply_arrangement_energy_matrix_targets(
                dict(plan.timeline_targets),
                section_role=str(section_role),
                section_index=int(section_index),
                form_section_count=int(owner.arrangement_policy.form_section_count()),
            )
        except Exception:
            pass
        try:
            plan.timeline_targets, curve = planner._apply_whole_song_director(
                dict(plan.timeline_targets),
                dict(curve),
                owner=owner,
                section_role=str(section_role),
                section_index=int(section_index),
                form_section_count=int(owner.arrangement_policy.form_section_count()),
            )
        except Exception:
            pass
        try:
            plan.arrangement_curve = dict(curve)
        except Exception:
            pass
    snap = getattr(planner, "_active_build_snapshot", None)
    comp_view = comp_proxy_for_voicing(snap) if snap is not None else None
    plan = planner._apply_timeline_targets_to_voicing(
        plan,
        composition=comp_view,
        chord_utils=getattr(planner.owner, "chord_utils", None),
    )

    # Cross-section chord register anchor:
    # after we shape chords under the melody within this section, shift the whole
    # section's chord voicings by octaves to stay close to a running anchor.
    anchor_enabled = resolve_config("composition", "chord_register_anchor_enabled", True, bool)
    anchor_strength = resolve_config("composition", "chord_register_anchor_strength", 0.85, float)
    chorus_lift = resolve_config("composition", "chord_register_anchor_chorus_lift", 2, int)
    anchor_strength = max(0.0, min(1.0, float(anchor_strength)))
    if anchor_enabled and anchor_strength > 1e-6 and getattr(plan, "chosen_chord", None):
        try:
            # Compute median chord center for this section.
            centers = []
            for notes in list(plan.chosen_chord or []):
                nn = sorted(int(n) for n in (notes or []) if isinstance(n, int))
                if nn:
                    centers.append(int(nn[len(nn) // 2]))
            if centers:
                centers.sort()
                sec_center = int(centers[len(centers) // 2])
            else:
                sec_center = None

            # Running anchor on owner.
            anchor = getattr(owner, "_chord_register_anchor", None)
            if anchor is None and sec_center is not None:
                anchor = int(sec_center)
            if sec_center is not None and anchor is not None:
                target = int(anchor)
                if section_role in {"b", "chorus"}:
                    target += int(chorus_lift)

                # Choose octave shift that best matches target.
                best_shift = 0
                best_dist = abs(int(sec_center) - int(target))
                for sh in (-24, -12, 0, 12, 24):
                    dist = abs(int(sec_center + sh) - int(target))
                    if dist < best_dist:
                        best_dist = dist
                        best_shift = int(sh)

                rng = getattr(owner, "rng", random)
                if rng.random() < anchor_strength and best_shift != 0:
                    shifted = []
                    for bar_notes in list(plan.chosen_chord):
                        shifted.append([int(RANGE_LIMITER.clamp_note(int(n + best_shift), 1)) for n in (bar_notes or [])])
                    plan.chosen_chord = shifted
                    # Update section center after shift.
                    centers2 = []
                    for notes in list(plan.chosen_chord or []):
                        nn = sorted(int(n) for n in (notes or []) if isinstance(n, int))
                        if nn:
                            centers2.append(int(nn[len(nn) // 2]))
                    if centers2:
                        centers2.sort()
                        sec_center = int(centers2[len(centers2) // 2])

                # Smoothly update the anchor (avoid jerky section-to-section jumps).
                if sec_center is not None:
                    old = int(anchor)
                    new = int(round(old * 0.70 + int(sec_center) * 0.30))
                    setattr(owner, "_chord_register_anchor", int(new))
        except Exception:
            pass

    # Harmony snapshot for melody/arp/counter (after register anchor mutates voicing).
    try:
        plan.refresh_harmonic_plan()
    except Exception:
        pass

    # Shared harmonic-rhythm schedule (arp + chord comping) without consuming ``owner.rng``.
    plan.harmonic_rhythm_action_by_bar = []
    _hr_shared = resolve_config("composition", "arp_chord_harmonic_rhythm_shared_enabled", True, bool)
    if _hr_shared:
        try:
            bars_hr = int(plan.bars)
            if bars_hr > 0 and plan.chords and plan.roots:
                chord_rb_hr = list((plan.timeline_targets or {}).get("chord_rhythm", []) or [])
                cr_avg_hr = (
                    (sum(float(v) for v in chord_rb_hr) / max(1, len(chord_rb_hr)))
                    if chord_rb_hr
                    else 1.0
                )
                cm_mult_hr = float(curve.get("chord_motion_mult", 1.0)) * float(cr_avg_hr)
                crm_mult_hr = max(0.5, min(1.55, float(curve.get("chord_rhythm_mult", 1.0))))
                planned = owner.harmony_manager.schedule_section_harmonic_rhythm_actions(
                    chords=list(plan.chords or []),
                    roots=list(plan.roots or []),
                    bars=bars_hr,
                    beats_per_bar=float(plan.beats_per_bar),
                    emotion=plan.emotion,
                    section_role=str(section_role or ""),
                    chord_rhythm_mult=float(crm_mult_hr),
                    chord_motion_mult=float(cm_mult_hr),
                    chord_rhythm_targets=list((plan.timeline_targets or {}).get("chord_rhythm", []) or []),
                    motif_strength_targets=list((plan.timeline_targets or {}).get("motif_strength", []) or []),
                    tension_targets=list((plan.timeline_targets or {}).get("tension", []) or []),
                    section_index=int(section_index),
                )
                if isinstance(planned, list) and len(planned) >= bars_hr:
                    plan.harmonic_rhythm_action_by_bar = list(planned[:bars_hr])
        except Exception:
            plan.harmonic_rhythm_action_by_bar = []

    layers_indep = resolve_config("composition", "arp_melody_layers_fully_independent", True, bool)
    # ------------------------------------------------------------------
    # 1) Arpeggiator first (derived from voiced chords)
    #
    # This matches the intended musical flow: harmony -> arp bed -> lead "answer".
    # (Previously the lead was generated first, then arp was ducked under it.)
    # ------------------------------------------------------------------
    arp_gate = float(curve.get("arp_enabled", 0.0)) >= 0.5
    # Last line of defense: `ambient` shares the default role sequence but keeps
    # form_mode "ambient", so `arrangement_curve` must not be the only gate.
    # Do not apply this to default-form intros: ArrangementPolicy explicitly
    # authors a light intro arp bed there to avoid an empty opening.
    try:
        _fm = str(getattr(getattr(owner, "arrangement_policy", None), "form_mode", "default") or "default")
        _fm = _fm.strip().lower()
    except Exception:
        _fm = "default"
    if _fm in {"ambient"} and str(section_role or "").strip().lower() == "intro":
        arp_gate = False
    # User intent: keep arp + melody separate, avoid "arp disappears" dropouts.
    # In outros, some role curves disable the arp entirely; instead keep a low-density bed.
    # Do not re-enable for emotions that opted out via anchor/override (disgust, annoyance).
    if str(section_role or "").strip().lower() == "outro":
        if not arp_gate and not _arp_bed_suppressed_for_section(plan.emotion, owner):
            arp_gate = True
            try:
                # Ensure a small but non-zero bed (avoid 0.0 from profile tables).
                if float(curve.get("arp_density_mult", 1.0) or 1.0) <= 1e-6:
                    curve["arp_density_mult"] = 0.55
            except Exception:
                curve["arp_density_mult"] = 0.55
    plan.arp_events = []
    if arp_gate:
        arp_target = float(curve.get("arp_target_notes_per_bar", 7.0))
        # Keep arp present even when lead is sparse; still respond to overall density.
        arp_target = max(2.0, arp_target * (0.85 + 0.3 * float(plan.emotion.density)))
        # Lane source: `chosen_melody` is a per-bar melody anchor chosen by the
        # harmony voice-leading pass. In some edge cases it can collapse low and
        # pin the arp to the bottom of its range. Guardrail: if the lane median
        # sits below the arp preferred register, lift it into the preferred band.
        lane = list(plan.chosen_melody or [])
        arp_lane_off = resolve_config("composition", "arp_lane_offset_from_melody", 0, int)
        if arp_lane_off and lane:
            lane = [RANGE_LIMITER.clamp_note(int(n) + int(arp_lane_off), 3) for n in lane]
        try:
            info = RANGE_LIMITER.get_range_info(3) or {}
            pref_min = int(info.get("preferred_min", 60))
            pref_max = int(info.get("preferred_max", 74))
            pref_mid = int(round((pref_min + pref_max) / 2.0))
        except Exception:
            pref_min, pref_max, pref_mid = 60, 74, 67
        if not lane:
            lane = [int(pref_mid) for _ in range(int(plan.bars))]
        else:
            try:
                xs = sorted(int(x) for x in lane if isinstance(x, int))
                med = int(xs[len(xs) // 2]) if xs else int(pref_mid)
            except Exception:
                med = int(pref_mid)
            # If the lane is pinned low, lift by an octave (clamped) so the arp
            # can actually articulate above the bass/chord floor.
            if int(med) < int(pref_min) - 1:
                lane = [RANGE_LIMITER.clamp_note(int(n) + 12, 3) for n in lane]
            # If still low (e.g. clamp collapsed), fall back to preferred mid.
            try:
                xs2 = sorted(int(x) for x in lane if isinstance(x, int))
                med2 = int(xs2[len(xs2) // 2]) if xs2 else int(pref_mid)
            except Exception:
                med2 = int(pref_mid)
            if int(med2) < int(pref_min) - 1:
                lane = [int(pref_mid) for _ in range(int(plan.bars))]
        chorusish_role = str(section_role or "").lower() in {"b", "chorus", "hook", "tag"}
        if chorusish_role and lane:
            # Chorus lift: keep the arp bed clearly above the verse lane so the
            # section reads as a lift even when harmony/melody material is similar.
            lane = [RANGE_LIMITER.clamp_note(int(n) + 12, 3) for n in lane]
        # Section-level arp planning:
        # Stabilize (a) register lane and (b) arp mode across the section, with a
        # small, scheduled variation so it feels composed rather than per-bar random.
        arp_plan = None
        chorus_hook_blueprint = None
        phrase_intents = None
        # Optional: lock per-emotion arp macro style (mode/register/feel).
        style_enabled = resolve_config("composition", "arp_style_table_enabled", True, bool)
        style_strength = resolve_config("composition", "arp_style_table_strength", 0.95, float)
        intent_bus = resolve_config("composition", "phrase_intent_bus_enabled", False, bool)
        style_strength = max(0.0, min(1.0, float(style_strength)))
        style = {}
        if style_enabled and style_strength > 1e-6 and arp_style_for_emotion is not None:
            try:
                style = arp_style_for_emotion(str(getattr(plan.emotion, "name", "") or "neutral"))
            except Exception:
                style = {}
        quiet_ostinato_lock = planner._quiet_verse_ostinato_lock(
            emotion_name=str(getattr(plan.emotion, "name", "") or ""),
            section_role=str(section_role or ""),
        )
        # Ensure `base_mode` always exists even if the section-level arp planning
        # block fails (fallback is still musically coherent).
        base_mode = str(curve.get("arp_mode", "up") or "up")
        base_mode = base_mode.strip() if base_mode else "up"
        try:
            from data.arp_curve_defaults import normalize_arp_mode

            base_mode = normalize_arp_mode(base_mode)
        except Exception:
            pass
        if layers_indep:
            if base_mode in {"converge", "diverge"}:
                base_mode = "updown"
            elif base_mode not in {"up", "down", "updown", "downup", "updown_excl"}:
                base_mode = "updown"
        # Song-level cohesion: optionally lock a per-song arp mode (often per-role) so
        # the arrangement reads as one song, not stitched per-section fragments.
        song_locked = False
        try:
            by_role = getattr(owner, "_song_arp_mode_by_role", None)
        except Exception:
            by_role = None
        if isinstance(by_role, dict):
            try:
                pick = by_role.get(str(section_role or "").strip().lower())
            except Exception:
                pick = None
            if pick:
                base_mode = str(pick)
                song_locked = True
                try:
                    from data.arp_curve_defaults import normalize_arp_mode

                    base_mode = normalize_arp_mode(base_mode)
                except Exception:
                    pass
        try:
            arp_mode_hard_lock = bool(curve.get("arp_mode_lock", False))
        except Exception:
            arp_mode_hard_lock = False
        if arp_mode_hard_lock:
            song_locked = True
        # Pre-resolve role-level arp overrides so they still apply even if the
        # richer per-bar arp plan fails to build for some reason.
        role_arp_density_mult = None
        role_arp_grid = None
        try:
            role_arp_density_mult = float(curve.get("arp_density_mult", 1.0) or 1.0)
            role_arp_density_mult = max(0.25, min(2.0, float(role_arp_density_mult)))
        except Exception:
            role_arp_density_mult = None
        try:
            grid_override = curve.get("arp_grid", None)
            if grid_override is not None:
                g = float(grid_override)
                # 0.5 = 8ths, 0.25 = 16ths; keep within a sane range.
                role_arp_grid = float(max(0.125, min(2.0, float(g))))
        except Exception:
            role_arp_grid = None
        try:
            bars_n = int(plan.bars)
            if bars_n > 0:
                if chorusish_role:
                    preset = getattr(plan, "joint_hook_blueprint", None)
                    if isinstance(preset, dict) and preset:
                        chorus_hook_blueprint = dict(preset)
                    else:
                        try:
                            chorus_hook_blueprint = _select_seeded_chorus_hook_blueprint(
                                owner,
                                plan,
                                section_role=str(section_role or ""),
                                section_index=int(section_index),
                            )
                        except Exception:
                            chorus_hook_blueprint = None
                    if isinstance(chorus_hook_blueprint, dict):
                        mode0 = str(chorus_hook_blueprint.get("chorus_interaction_mode", "") or "").strip().lower()
                        if mode0 in {"coexist", "unison", "dialogue", "fill"}:
                            curve["chorus_interaction_mode"] = str(mode0)
                shape = _timeline_shape(section_role, bars_n)
                # Register plan: follow section energy (slight lift on peaks), but keep
                # within arp channel preferred range.
                lane_center_by_bar: List[int] = []
                for i in range(bars_n):
                    base = int(lane[i]) if lane and i < len(lane) else 72
                    lift = 0
                    v = float(shape[i]) if i < len(shape) else 1.0
                    if chorusish_role and v >= 0.70:
                        lift = 4 if v >= 0.92 else 3
                    elif section_role in {"b", "pre_chorus", "tag"} and v >= 0.85:
                        lift = 2
                    elif section_role == "outro":
                        lift = -2
                    lane_center_by_bar.append(RANGE_LIMITER.clamp_note(int(base + lift), 3))

                if style and pick_style_value is not None:
                    try:
                        base_mode = str(pick_style_value(style, "mode", base_mode) or base_mode)
                        try:
                            from data.arp_curve_defaults import normalize_arp_mode

                            base_mode = normalize_arp_mode(base_mode)
                        except Exception:
                            pass
                    except Exception:
                        pass
                mode_by_bar: List[str] = []
                allow_var = True
                style_mode_choices = None
                if style and pick_style_value is not None:
                    try:
                        allow_var = bool(pick_style_value(style, "allow_mode_variation", True))
                    except Exception:
                        allow_var = True
                    try:
                        smc = style.get("mode_choices")
                        if isinstance(smc, list):
                            style_mode_choices = [str(x) for x in smc if str(x).strip()]
                    except Exception:
                        style_mode_choices = None
                # If the style table is only weakly applied (low strength), don't hard-lock
                # mode variation off; allow limited section-level variation to keep the system
                # feeling self-generative across runs.
                if not allow_var and float(style_strength) < 0.5:
                    allow_var = True
                # If the song chose a locked arp mode palette, do not add per-section
                # random mode thrash; keep only the deterministic scheduled variations.
                if song_locked:
                    allow_var = False

                # Style table can also lock timing/density (Ableton-like rate + straight timing).
                # Apply as section-level arp_plan overrides so the realtime engine sees it.
                style_grid = None
                style_tnpb = None
                if style and pick_style_value is not None:
                    try:
                        style_grid = pick_style_value(style, "grid", None)
                        style_tnpb = pick_style_value(style, "target_notes_per_bar", None)
                    except Exception:
                        style_grid = None
                        style_tnpb = None

                # Conversation-preset variations: small palette of arp rates/modes per emotion.
                # This is intentionally applied *after* the style table so a preset can add
                # variety (e.g. for "neutral") without having to rewrite the global emotion table.
                pv_on = resolve_config("composition", "arp_preset_variations_enabled", False, bool)
                pv_prob = resolve_config("composition", "arp_preset_variations_prob", 0.0, float)
                pv_map = resolve_config("composition", "arp_preset_variations_by_emotion", None)
                pv_prob = max(0.0, min(1.0, float(pv_prob)))
                if pv_on and pv_prob > 1e-6 and isinstance(pv_map, dict):
                    try:
                        em_key = str(getattr(plan.emotion, "name", "") or "neutral").strip().lower()
                    except Exception:
                        em_key = "neutral"
                    spec = pv_map.get(em_key) or pv_map.get("default")
                    if isinstance(spec, dict) and rng.random() < pv_prob:
                        # Pick one deterministic-ish variant per section (not per bar).
                        pick = {}
                        try:
                            variants = list(spec.get("variants") or [])
                        except Exception:
                            variants = []
                        if variants:
                            weighted = []
                            for v in variants:
                                if not isinstance(v, dict):
                                    continue
                                try:
                                    w = float(v.get("weight", 1.0) or 1.0)
                                except Exception:
                                    w = 1.0
                                if w <= 0:
                                    continue
                                weighted.append((w, v))
                            if weighted:
                                total = sum(w for w, _ in weighted)
                                r = rng.random() * total if total > 0 else 0.0
                                acc = 0.0
                                for w, v in weighted:
                                    acc += float(w)
                                    if r <= acc:
                                        pick = dict(v)
                                        break
                        else:
                            # Simple choice lists.
                            try:
                                grids = list(spec.get("grid_choices") or [])
                            except Exception:
                                grids = []
                            try:
                                tnpbs = list(spec.get("target_notes_per_bar_choices") or [])
                            except Exception:
                                tnpbs = []
                            try:
                                modes = list(spec.get("mode_choices") or [])
                            except Exception:
                                modes = []
                            if grids:
                                try:
                                    pick["grid"] = float(rng.choice(grids))
                                except Exception:
                                    pass
                            if tnpbs:
                                try:
                                    pick["target_notes_per_bar"] = float(rng.choice(tnpbs))
                                except Exception:
                                    pass
                            if modes:
                                try:
                                    pick["mode"] = str(rng.choice(modes))
                                except Exception:
                                    pass

                        # Apply picked overrides (guardrails happen downstream).
                        try:
                            g2 = pick.get("grid")
                            if g2 is not None:
                                style_grid = float(g2)
                        except Exception:
                            pass
                        try:
                            t2 = pick.get("target_notes_per_bar")
                            if t2 is not None:
                                style_tnpb = float(t2)
                        except Exception:
                            pass
                        try:
                            m2 = pick.get("mode")
                            if m2:
                                from data.arp_curve_defaults import normalize_arp_mode

                                base_mode = normalize_arp_mode(str(m2))
                        except Exception:
                            pass
                if quiet_ostinato_lock:
                    base_mode = str(quiet_ostinato_lock.get("mode", "up") or "up")
                    allow_var = False
                    song_locked = True
                    style_mode_choices = [str(base_mode)]
                    try:
                        style_grid = float(quiet_ostinato_lock.get("grid", style_grid if style_grid is not None else 1.0) or 1.0)
                    except Exception:
                        style_grid = 1.0
                    try:
                        style_tnpb = min(
                            float(style_tnpb if style_tnpb is not None else 8.0),
                            float(quiet_ostinato_lock.get("target_notes_per_bar_max", 2.2) or 2.2),
                        )
                    except Exception:
                        style_tnpb = float(quiet_ostinato_lock.get("target_notes_per_bar_max", 2.2) or 2.2)
                    try:
                        role_arp_density_mult = min(
                            float(role_arp_density_mult if role_arp_density_mult is not None else 1.0),
                            float(quiet_ostinato_lock.get("density_mult_max", 0.30) or 0.30),
                        )
                    except Exception:
                        role_arp_density_mult = float(quiet_ostinato_lock.get("density_mult_max", 0.30) or 0.30)
                    try:
                        curve["arp_velocity_scale"] = min(
                            float(curve.get("arp_velocity_scale", 1.0) or 1.0),
                            float(quiet_ostinato_lock.get("velocity_scale_max", 0.72) or 0.72),
                        )
                    except Exception:
                        curve["arp_velocity_scale"] = float(quiet_ostinato_lock.get("velocity_scale_max", 0.72) or 0.72)
                for i in range(bars_n):
                    m = base_mode
                    if layers_indep:
                        mode_by_bar.append(str(base_mode))
                        continue
                    if arp_mode_hard_lock:
                        mode_by_bar.append(str(base_mode))
                        continue
                    try:
                        arp_mode_var_prob = float(curve.get("arp_mode_variation_prob", 0.18) or 0.18)
                    except Exception:
                        arp_mode_var_prob = 0.18
                    arp_mode_var_prob = max(0.0, min(0.5, float(arp_mode_var_prob)))
                    # Small scheduled variation: every 4 bars, switch to a related mode
                    # for one bar (keeps identity but adds motion).
                    if chorusish_role:
                        # Chorus/tag should read as a lift, but do NOT hard-force the same
                        # mode cycle across all emotions. Keep the identity anchored to
                        # the emotion's base_mode/style table, with a gentle bias away from
                        # one-directional modes (which can sound like "verse arp" in a chorus).
                        if base_mode in {"up", "down"}:
                            m = "downup"
                        elif base_mode in {"converge", "diverge"}:
                            m = "updown_excl"
                        else:
                            m = base_mode

                        # Allow emotion-driven variation in choruses (kept bounded).
                        if allow_var:
                            try:
                                p = max(float(arp_mode_var_prob), 0.22)
                                if rng.random() < p:
                                    alts = list(style_mode_choices or ["updown", "downup", "updown_excl", "converge", "diverge"])
                                    alts = [x for x in alts if x and x != m]
                                    if alts:
                                        m = str(rng.choice(alts))
                            except Exception:
                                pass
                    elif allow_var and section_role in {"b", "a_prime", "tag"} and (i % 4) == 3:
                        m = "updown" if base_mode in {"up", "down"} else "up"
                    # Ableton-like "Style" variation while keeping straight timing:
                    # occasionally switch the arp ordering mode for a bar.
                    elif allow_var and section_role in {"a", "pre_chorus", "a_prime", "b", "tag"}:
                        try:
                            if rng.random() < arp_mode_var_prob:
                                alts = list(style_mode_choices or ["up", "down", "updown", "downup", "converge", "diverge"])
                                alts = [x for x in alts if x and x != base_mode]
                                if alts:
                                    m = str(rng.choice(alts))
                        except Exception:
                            pass
                    if section_role == "intro" and i < 2:
                        m = "converge"
                    if section_role == "outro" and i >= max(0, bars_n - 2):
                        m = "down"
                    try:
                        from data.arp_curve_defaults import normalize_arp_mode

                        m = normalize_arp_mode(m)
                    except Exception:
                        pass
                    mode_by_bar.append(m)

                lane_hw = 7
                if style and pick_style_value is not None:
                    try:
                        lane_hw = int(pick_style_value(style, "lane_half_width", lane_hw) or lane_hw)
                    except Exception:
                        lane_hw = 7
                arp_plan = {
                    "lane_center_by_bar": lane_center_by_bar,
                    "lane_half_width": int(max(5 if chorusish_role else 4, min(12, int(lane_hw)))),
                    "mode_by_bar": mode_by_bar,
                    "rotate_to_prev": True,
                    # For chorus arp bed (ch=3), prefer cycling all chord pitch-classes so
                    # the arp doesn't collapse to just 1–2 tones when the voiced chord is sparse.
                    "tones_source": "voiced_exact",
                    "tension_by_bar": list((plan.timeline_targets or {}).get("tension", []) or []),
                    "chord_rhythm_by_bar": list((plan.timeline_targets or {}).get("chord_rhythm", []) or []),
                    "motif_strength_by_bar": list((plan.timeline_targets or {}).get("motif_strength", []) or []),
                    "phrase_role_by_bar": list((plan.timeline_targets or {}).get("phrase_role_by_bar", []) or []),
                    "cadence_window": list((plan.timeline_targets or {}).get("cadence_window", []) or []),
                    "cadence_strength_by_bar": list((plan.timeline_targets or {}).get("cadence_window", []) or []),
                    "harmony_function_target_by_bar": list(
                        (plan.timeline_targets or {}).get("harmony_function_target_by_bar", []) or []
                    ),
                }
                try:
                    if style_grid is not None:
                        arp_plan["grid"] = float(style_grid)
                except Exception:
                    pass
                try:
                    if style_tnpb is not None:
                        arp_plan["target_notes_per_bar"] = float(style_tnpb)
                except Exception:
                    pass
                hr_sched = list(getattr(plan, "harmonic_rhythm_action_by_bar", []) or [])
                if hr_sched and len(hr_sched) >= int(bars_n):
                    arp_plan["harmonic_rhythm_action_by_bar"] = list(hr_sched[: int(bars_n)])
                # Chorus-only reference micro-shaping from labeled WAVs.
                if chorus_ref_arp:
                    for k in ("accent_strength", "octave_reach_prob", "syncopation_prob"):
                        if chorus_ref_arp.get(k) is not None:
                            try:
                                arp_plan[k] = float(chorus_ref_arp.get(k))
                            except Exception:
                                pass
                # Stage-2 Arp rhythm cells: choose a deterministic per-bar onset pattern
                # so the arp has a recognizable rhythmic identity.
                cells_on = resolve_config("composition", "arp_rhythm_cells_enabled", False, bool)
                cells_strength = resolve_config("composition", "arp_rhythm_cells_strength", 0.75, float)
                cells_strength = max(0.0, min(1.0, float(cells_strength)))
                if cells_on and cells_strength > 1e-6:
                    try:
                        from data.arp_rhythm_cells import (
                            ARP_RHYTHM_CELLS,
                            arp_rhythm_weights_for_emotion,
                            arp_rhythm_weights_for_role,
                        )

                        em_name = str(getattr(plan.emotion, "name", "neutral") or "neutral")
                        weights = arp_rhythm_weights_for_emotion(em_name)
                        rlc = str(section_role or "").lower()
                        role_weights = arp_rhythm_weights_for_role(rlc)
                        if role_weights:
                            merged = dict(weights)
                            for nm, mul in role_weights.items():
                                try:
                                    merged[str(nm)] = float(merged.get(str(nm), 1.0)) * float(mul)
                                except Exception:
                                    merged[str(nm)] = float(mul)
                            weights = merged
                        chorus_co = 1
                        try:
                            chorus_co = max(
                                1,
                                int(owner.arrangement_policy.chorus_occurrence_number(int(section_index))),
                            )
                        except Exception:
                            chorus_co = 1
                        if rlc in {"b", "chorus", "hook"}:
                            weights = dict(weights)
                            if chorus_co >= 2:
                                tier_c = min(float(chorus_co - 1), 4.0)
                                phase = int(chorus_co - 2) % 3
                                if phase == 0:
                                    weights["sixteenths_sparse"] = float(
                                        weights.get("sixteenths_sparse", 1.0)
                                    ) * (1.14 + 0.03 * tier_c)
                                    weights["eighths"] = float(weights.get("eighths", 1.0)) * (
                                        1.04 + 0.02 * tier_c
                                    )
                                elif phase == 1:
                                    weights["sixteenths"] = float(weights.get("sixteenths", 1.0)) * (
                                        1.10 + 0.04 * tier_c
                                    )
                                    weights["eighths"] = float(weights.get("eighths", 1.0)) * (
                                        0.98 + 0.02 * tier_c
                                    )
                                else:
                                    weights["eighths"] = float(weights.get("eighths", 1.0)) * (
                                        1.12 + 0.03 * tier_c
                                    )
                                    weights["sixteenths"] = float(weights.get("sixteenths", 1.0)) * (
                                        1.06 + 0.03 * tier_c
                                    )
                                    weights["sixteenths_sparse"] = float(
                                        weights.get("sixteenths_sparse", 1.0)
                                    ) * (1.06 + 0.02 * tier_c)
                        elif rlc in {"pre_chorus"}:
                            weights = dict(weights)
                            # Build sections should tighten and accelerate, but still feel planned.
                            weights["sixteenths_sparse"] = float(weights.get("sixteenths_sparse", 1.0)) * 1.10
                            weights["anticipate_2_4"] = float(weights.get("anticipate_2_4", 1.0)) * 1.06
                            weights["offbeat_push"] = float(weights.get("offbeat_push", 1.0)) * 0.90

                        names = sorted([n for n in ARP_RHYTHM_CELLS.keys()])
                        w = [float(weights.get(n, 1.0)) for n in names]
                        # Arp-lane memory: keep rhythm-cell anti-repeat separate from chord memory.
                        lane_mem_on = resolve_config("composition", "arp_lane_rhythm_memory_enabled", True, bool)
                        lane_mem_win = resolve_config("composition", "arp_lane_rhythm_recent_window", 4, int)
                        lane_mem_pen = resolve_config("composition", "arp_lane_rhythm_repeat_penalty", 0.55, float)
                        lane_mem_win = max(1, min(12, int(lane_mem_win)))
                        lane_mem_pen = max(0.0, min(1.0, float(lane_mem_pen)))
                        lane_key = (str(em_name or "").strip().lower(), str(rlc or "").strip().lower())
                        if lane_mem_on and names:
                            try:
                                hist_map = getattr(owner, "_arp_lane_recent_cell_names", None)
                                if not isinstance(hist_map, dict):
                                    hist_map = {}
                                    setattr(owner, "_arp_lane_recent_cell_names", hist_map)
                                recent_cells = list(hist_map.get(lane_key, []) or [])
                            except Exception:
                                recent_cells = []
                            if recent_cells:
                                counts = {}
                                for nm in recent_cells[-lane_mem_win:]:
                                    k = str(nm or "")
                                    counts[k] = int(counts.get(k, 0)) + 1
                                w_adj = []
                                for idx, nm in enumerate(names):
                                    c = int(counts.get(str(nm), 0))
                                    # Exponential attenuation by repeat count in the recent window.
                                    scale = (1.0 - lane_mem_pen) ** c if c > 0 else 1.0
                                    w_adj.append(max(1e-9, float(w[idx]) * float(scale)))
                                w = w_adj
                        # Deterministic pick per section, then evolve every 4 bars.
                        try:
                            drng = getattr(owner, "deterministic_rng", None)
                            rr = (
                                drng("arp_rhythm_cell", str(em_name), str(rlc), str(int(chorus_co)))
                                if callable(drng)
                                else rng
                            )
                            pick_name = rr.choices(names, weights=w, k=1)[0]
                        except Exception:
                            pick_name = names[0] if names else ""
                        if lane_mem_on and pick_name:
                            try:
                                hist_map = getattr(owner, "_arp_lane_recent_cell_names", None)
                                if not isinstance(hist_map, dict):
                                    hist_map = {}
                                    setattr(owner, "_arp_lane_recent_cell_names", hist_map)
                                recent_cells = list(hist_map.get(lane_key, []) or [])
                                recent_cells.append(str(pick_name))
                                hist_map[lane_key] = recent_cells[-lane_mem_win:]
                            except Exception:
                                pass

                        onset_steps_by_bar = []
                        hold_longer = str(em_name).strip().lower() in {
                            "love",
                            "sadness",
                            "remorse",
                            "gratitude",
                            "caring",
                            "grief",
                            "relief",
                            "calm",
                            "peaceful",
                            "serenity",
                        }
                        stable_bed_role = rlc in {"a", "verse", "b", "chorus", "hook", "tag", "pre_chorus"}
                        span_bars = 6 if stable_bed_role else 2
                        if hold_longer:
                            span_bars = max(int(span_bars), 8)
                        if str(em_name).strip().lower() in {"joy", "surprise", "optimism", "pride", "nervousness", "fear"}:
                            span_bars = max(int(span_bars), 8)
                        current_name = str(pick_name)
                        for bi in range(int(bars_n)):
                            if bi > 0 and (bi % int(span_bars)) == 0:
                                evolve_prob = (0.035 if stable_bed_role else 0.12) * cells_strength
                                if hold_longer:
                                    evolve_prob *= 0.55
                                if str(em_name).strip().lower() in {"joy", "surprise", "optimism", "pride", "nervousness", "fear"}:
                                    evolve_prob *= 0.45
                                if rng.random() < float(evolve_prob):
                                    alt = "eighths"
                                    if current_name in {"eighths", "quarters", "snowfall_anchor"}:
                                        alt = "sixteenths_sparse"
                                    elif current_name in {"sixteenths", "sixteenths_sparse"}:
                                        alt = "eighths"
                                    elif current_name == "anticipate_2_4":
                                        alt = "eighths"
                                    elif current_name == "offbeat_push":
                                        alt = "sixteenths_sparse"
                                    if alt in ARP_RHYTHM_CELLS:
                                        current_name = str(alt)
                            cell = ARP_RHYTHM_CELLS.get(str(current_name)) or {}
                            steps = list(cell.get("onset_steps", []) or [])
                            onset_steps_by_bar.append([int(s) for s in steps if isinstance(s, int)])
                        if onset_steps_by_bar and rng.random() < cells_strength:
                            arp_plan["onset_steps_by_bar"] = onset_steps_by_bar
                            arp_plan["rhythm_cell_span_bars"] = int(span_bars)
                            # Let the cell suggest a grid if it’s musically coherent.
                            try:
                                grid0 = float((ARP_RHYTHM_CELLS.get(str(pick_name)) or {}).get("grid", 0.25))
                                if grid0 > 1e-9 and ("grid" not in arp_plan):
                                    arp_plan["grid"] = float(grid0)
                            except Exception:
                                pass
                    except Exception:
                        pass
                # Stage-1 PhraseIntent bus: build advisory phrase intents so
                # downstream layers can coordinate (no behavior change unless enabled).
                if intent_bus and not layers_indep:
                    try:
                        from composition.phrase_intent import PhraseIntent

                        # Plan phrase contours + onset grids using the same melody parameterization.
                        effective_temp = float(temperature) * float(curve.get("temperature_mult", 1.0))
                        timeline_melody = list((plan.timeline_targets or {}).get("melody_density", []) or [])
                        if timeline_melody:
                            effective_target_npb = float(target_notes_per_bar) * (
                                sum(float(v) for v in timeline_melody) / max(1, len(timeline_melody))
                            )
                        else:
                            effective_target_npb = float(target_notes_per_bar) * float(curve.get("melody_density_mult", 1.0))
                        melody_total_notes_mult = float(curve.get("melody_total_notes_mult", 1.0))
                        raw_cap = curve.get("melody_max_notes_per_phrase")
                        melody_max_notes_per_phrase = int(raw_cap) if raw_cap is not None else None
                        mel_em = owner.melody_manager.get_melody_emotion(plan.emotion)
                        phrase_contours, notes_per_phrase, _tm, _dm = owner.melody_runtime.prepare_melody_parameters(
                            mel_em,
                            int(plan.bars),
                            float(effective_temp),
                            float(effective_target_npb),
                            first_phrase_note_scale=1.0,
                            melody_total_notes_mult=float(melody_total_notes_mult),
                            melody_max_notes_per_phrase=melody_max_notes_per_phrase,
                            section_role=section_role,
                            timeline_density_by_bar=list((plan.timeline_targets or {}).get("melody_density", []) or []),
                        )
                        onsets_by_bar = owner.melody_runtime.plan_phrase_rhythm_onset_steps_by_bar(
                            emotion=mel_em,
                            phrase_contours=list(phrase_contours),
                            notes_per_phrase=list(notes_per_phrase),
                            bars=int(plan.bars),
                            beats_per_bar=float(plan.beats_per_bar),
                            grid=0.25,
                            rng=getattr(owner, "rng", rng),
                        )
                        # Phrase roles: opening/cadence ends; alternate inner phrases as answer/continuation.
                        def _role_for_phrase(i: int, total: int) -> str:
                            if total <= 1 or i == 0:
                                return "opening"
                            if i == total - 1:
                                return "cadence"
                            return "answer" if (i % 2 == 1) else "continuation"

                        nphr = max(1, len(list(notes_per_phrase)))
                        # Register hint from melody lane median.
                        try:
                            xs = sorted(int(x) for x in (plan.chosen_melody or []) if isinstance(x, int))
                            reg_center = int(xs[len(xs) // 2]) if xs else None
                        except Exception:
                            reg_center = None

                        phrase_intents = []
                        for pid in range(nphr):
                            # Interaction-driven groove policy (chorus-like roles only).
                            _base_pol = resolve_config("composition", "arp_groove_link_mode", "complement", str)
                            pol = _base_pol
                            try:
                                interaction_mode0 = str(curve.get("chorus_interaction_mode", "") or "").strip().lower()
                                if chorusish_role and interaction_mode0 in {"unison"}:
                                    pol = "mirror"
                                elif chorusish_role and interaction_mode0 in {"dialogue", "fill"}:
                                    pol = "complement"
                                elif chorusish_role and interaction_mode0 in {"coexist"}:
                                    pol = "hybrid"
                            except Exception:
                                pol = _base_pol
                            phrase_intents.append(
                                PhraseIntent(
                                    phrase_idx=int(pid),
                                    phrase_role=str(_role_for_phrase(pid, nphr)),
                                    contour=str(phrase_contours[pid] if pid < len(phrase_contours) else ""),
                                    register_center_midi=reg_center,
                                    register_half_width_midi=resolve_config("composition", "melody_lane_half_width", 10, int),
                                    melody_onset_steps_by_bar=list(onsets_by_bar) if onsets_by_bar else None,
                                    arp_onset_policy=str(pol),
                                )
                            )
                    except Exception:
                        phrase_intents = None
                # Groove link: plan a melody rhythm-template onset grid so the arp can
                # either align (groove lock) or fill gaps (call/response).
                gl = resolve_config("composition", "arp_melody_groove_link_strength", 0.0, float)
                gl = max(0.0, min(1.0, float(gl)))
                if gl > 1e-6 and not layers_indep:
                    try:
                        # Use the same parameterization as the later melody generation
                        # so the onset plan matches the actual phrase rhythm templates.
                        effective_temp = float(temperature) * float(curve.get("temperature_mult", 1.0))
                        timeline_melody = list((plan.timeline_targets or {}).get("melody_density", []) or [])
                        if timeline_melody:
                            effective_target_npb = float(target_notes_per_bar) * (
                                sum(float(v) for v in timeline_melody) / max(1, len(timeline_melody))
                            )
                        else:
                            effective_target_npb = float(target_notes_per_bar) * float(curve.get("melody_density_mult", 1.0))
                        melody_total_notes_mult = float(curve.get("melody_total_notes_mult", 1.0))
                        raw_cap = curve.get("melody_max_notes_per_phrase")
                        melody_max_notes_per_phrase = int(raw_cap) if raw_cap is not None else None

                        mel_em = owner.melody_manager.get_melody_emotion(plan.emotion)
                        phrase_contours, notes_per_phrase, _tm, _dm = owner.melody_runtime.prepare_melody_parameters(
                            mel_em,
                            int(plan.bars),
                            float(effective_temp),
                            float(effective_target_npb),
                            first_phrase_note_scale=1.0,
                            melody_total_notes_mult=float(melody_total_notes_mult),
                            melody_max_notes_per_phrase=melody_max_notes_per_phrase,
                            section_role=section_role,
                            timeline_density_by_bar=list((plan.timeline_targets or {}).get("melody_density", []) or []),
                        )
                        onsets_by_bar = owner.melody_runtime.plan_phrase_rhythm_onset_steps_by_bar(
                            emotion=mel_em,
                            phrase_contours=list(phrase_contours),
                            notes_per_phrase=list(notes_per_phrase),
                            bars=int(plan.bars),
                            beats_per_bar=float(plan.beats_per_bar),
                            grid=0.25,
                            rng=getattr(owner, "rng", rng),
                        )
                        if onsets_by_bar:
                            arp_plan["melody_onsets_by_bar"] = onsets_by_bar
                    except Exception:
                        pass
                # Role curve density multiplier (applied inside Arpeggiator so it stacks
                # with emotion profiles rather than being overridden by them).
                try:
                    dm = float(curve.get("arp_density_mult", 1.0) or 1.0)
                    if chorusish_role:
                        dm = max(float(dm), 1.35 if str(section_role or "").lower() in {"b", "chorus", "hook"} else 1.22)
                    dm = max(0.25, min(2.0, float(dm)))
                    arp_plan["density_mult"] = float(dm)
                except Exception:
                    pass
                # Optional role-level rhythmic grid override (hybrid feel).
                # If set, this takes precedence over emotion defaults inside Arpeggiator.
                try:
                    if role_arp_grid is not None:
                        arp_plan["grid"] = float(role_arp_grid)
                except Exception:
                    pass
                if chorusish_role and isinstance(chorus_hook_blueprint, dict):
                    try:
                        arp_plan = _apply_chorus_hook_blueprint_to_arp_plan(
                            dict(arp_plan or {}),
                            chorus_hook_blueprint,
                            bars=int(bars_n),
                        )
                    except Exception:
                        pass
        except Exception:
            arp_plan = None
        # If arp_plan failed to build, keep the role-level grid/density overrides.
        if arp_plan is None:
            try:
                arp_plan = {}
                if role_arp_density_mult is not None:
                    arp_plan["density_mult"] = float(role_arp_density_mult)
                if role_arp_grid is not None:
                    arp_plan["grid"] = float(role_arp_grid)
                if chorus_ref_arp:
                    for k in ("accent_strength", "octave_reach_prob", "syncopation_prob"):
                        if chorus_ref_arp.get(k) is not None:
                            arp_plan[k] = float(chorus_ref_arp.get(k))
                hr_fb = list(getattr(plan, "harmonic_rhythm_action_by_bar", []) or [])
                bars_fb = int(plan.bars)
                if hr_fb and bars_fb > 0 and len(hr_fb) >= bars_fb:
                    arp_plan["harmonic_rhythm_action_by_bar"] = list(hr_fb[:bars_fb])
                if chorusish_role and isinstance(chorus_hook_blueprint, dict):
                    arp_plan = _apply_chorus_hook_blueprint_to_arp_plan(
                        dict(arp_plan or {}),
                        chorus_hook_blueprint,
                        bars=int(bars_fb),
                    )
            except Exception:
                arp_plan = None
        try:
            # Shared motif memory: seed a theme from the motif library and let the arp
            # inherit its rhythm accents (subtle glue between layers).
            motif_hook = None
            bus_enabled = True
            bus_strength = 0.72
            bus_enabled = resolve_config("composition", "cross_lane_motif_bus_enabled", True, bool)
            bus_strength = resolve_config("composition", "cross_lane_motif_bus_strength", 0.72, float)
            bus_strength = max(0.0, min(1.0, float(bus_strength)))
            try:
                if hasattr(owner, "motif_plan") and owner.motif_plan is not None:
                    owner.motif_plan.seed_from_library_if_needed()
                    motif_hook = owner.motif_plan.theme()
            except Exception:
                motif_hook = None
            if motif_hook is None and bus_enabled and bus_strength > 1e-6:
                try:
                    bus = getattr(owner, "_cross_lane_motif_bus", None)
                    motif_hook = planner._motif_hook_from_cross_lane_bus(bus)
                except Exception:
                    motif_hook = None
            # IMPORTANT: wire arp tone pool to the exact same voiced chord notes
            # that will be used for chord rendering (channel 1). The chord layer
            # uses `harmonic_plan_comping` (refreshed immediately before comping),
            # so prefer that snapshot for the arp too.
            try:
                plan.refresh_harmonic_plan_comping()
            except Exception:
                pass
            _hp_arp = getattr(plan, "harmonic_plan_comping", None) or getattr(plan, "harmonic_plan", None) or HarmonicPlan.from_section_plan(plan)
            voiced_arp = None
            try:
                voiced_arp = _hp_arp.voiced_chords_as_lists()
            except Exception:
                voiced_arp = None
            try:
                if layers_indep and isinstance(arp_plan, dict):
                    arp_plan.pop("melody_onsets_by_bar", None)
            except Exception:
                pass
            plan.arp_events = owner.melody_manager.arpeggiator.generate_from_harmonic_plan(
                owner.melody_manager.get_melody_emotion(plan.emotion),
                _hp_arp,
                arp_target,
                None,
                phrase_intents=(None if layers_indep else phrase_intents),
                channel=3,
                velocity_scale=float(
                    (
                        pick_style_value(style, "velocity_scale", curve.get("arp_velocity_scale", 0.92))
                        if style and pick_style_value is not None and rng.random() < style_strength
                        else curve.get("arp_velocity_scale", 0.92)
                    )
                ),
                chosen_lane=lane,
                voiced_chords=voiced_arp,
                # Arp is the bed; don't duck against the lead (lead is generated after).
                lead_events=None,
                swing=float(
                    (
                        pick_style_value(style, "swing", curve.get("arp_swing", 0.0) or 0.0)
                        if style and pick_style_value is not None and rng.random() < style_strength
                        else (curve.get("arp_swing", 0.0) or 0.0)
                    )
                ),
                lead_ducking=float(curve.get("arp_lead_ducking", 0.65) or 0.65),
                arp_mode=str(base_mode),
                section_role=section_role,
                arp_plan=arp_plan,
                motif_hook=(None if layers_indep else motif_hook),
            )
            try:
                setattr(owner, "_last_section_arp_plan", dict(arp_plan or {}))
            except Exception:
                pass

            # Chorus continuity repair: if the realized arp bed has sparse bars (<=3 events),
            # regenerate those bars with a forced full-grid onset policy (no melody-follow thinning).
            # This is intentionally conservative: it only replaces bars that are clearly "dropping out".
            try:
                rlc = str(section_role or "").strip().lower()
            except Exception:
                rlc = ""
            try:
                bars_i = int(plan.bars)
                bpb = float(plan.beats_per_bar)
            except Exception:
                bars_i, bpb = 0, 4.0
            if rlc in {"b", "chorus", "hook", "tag"} and bars_i > 0 and bpb > 1e-9 and plan.arp_events:
                try:
                    # Count arp events per bar.
                    counts = [0 for _ in range(int(bars_i))]
                    for ev in list(plan.arp_events or []):
                        if not (isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == 3):
                            continue
                        bi = int(float(ev[3]) // float(bpb))
                        if 0 <= bi < int(bars_i):
                            counts[int(bi)] += 1
                    sparse_bars = [int(i) for i, c in enumerate(counts) if int(c) <= 3]
                except Exception:
                    sparse_bars = []

                if sparse_bars:
                    fixed = []
                    # Build a cleaned arp_plan for regeneration (avoid any per-bar onset/groove masks).
                    try:
                        ap_clean = dict(arp_plan or {})
                        ap_clean.pop("onset_steps_by_bar", None)
                        ap_clean.pop("melody_onsets_by_bar", None)
                        ap_clean.pop("lane_center_by_bar", None)
                    except Exception:
                        ap_clean = None
                    try:
                        ch_syms = list(getattr(_hp_arp, "chords", []) or [])
                        roots_syms = list(getattr(_hp_arp, "roots", []) or [])
                    except Exception:
                        ch_syms, roots_syms = [], []
                    arper = owner.melody_manager.arpeggiator
                    new_events = []
                    for bi in sparse_bars:
                        if not (0 <= int(bi) < int(bars_i)):
                            continue
                        try:
                            chord_sym = str(ch_syms[int(bi)]) if int(bi) < len(ch_syms) else None
                            root_m = int(roots_syms[int(bi)]) if int(bi) < len(roots_syms) else 60
                        except Exception:
                            chord_sym, root_m = None, 60
                        if not chord_sym:
                            continue
                        try:
                            voiced_one = (
                                voiced_arp[int(bi)]
                                if isinstance(voiced_arp, list) and int(bi) < len(voiced_arp)
                                else None
                            )
                        except Exception:
                            voiced_one = None
                        try:
                            regen = arper.generate_from_chords(
                                owner.melody_manager.get_melody_emotion(plan.emotion),
                                [str(chord_sym)],
                                [int(root_m)],
                                1,
                                float(bpb),
                                float(arp_target),
                                None,
                                channel=3,
                                velocity_scale=1.0,
                                chosen_lane=None,
                                voiced_chords=([list(voiced_one)] if isinstance(voiced_one, list) else None),
                                lead_events=None,
                                swing=0.0,
                                lead_ducking=0.0,
                                arp_mode=str(base_mode),
                                section_role=str(rlc),
                                arp_plan=ap_clean,
                                motif_hook=(None if layers_indep else motif_hook),
                            )
                        except Exception:
                            regen = []
                        if regen:
                            # Offset regenerated bar events into section timeline.
                            off = float(bi) * float(bpb)
                            for ev in list(regen or []):
                                if not (isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == 3):
                                    continue
                                ch, midi, vel, st, dur, notes = ev
                                new_events.append((3, int(midi), int(vel), float(st) + off, float(dur), list(notes)))
                            fixed.append(int(bi))

                    if fixed and new_events:
                        # Drop old arp events in those bars; keep other channels intact.
                        kept = []
                        for ev in list(plan.arp_events or []):
                            if not (isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == 3):
                                kept.append(ev)
                                continue
                            bi = int(float(ev[3]) // float(bpb))
                            if int(bi) in set(fixed):
                                continue
                            kept.append(ev)
                        plan.arp_events = sorted(list(kept) + list(new_events), key=lambda e: float(e[3]))
            # End chorus continuity repair.

            # Optional: feed motifs extracted from the arp bed back into the
            # melody motif library (so the lead can quote the bed later).
            fb_enabled = resolve_config("composition", "arp_to_melody_motif_feedback_enabled", False, bool)
            fb_prob = resolve_config("composition", "arp_to_melody_motif_feedback_prob", 0.35, float)
            fb_prob = max(0.0, min(1.0, float(fb_prob)))
            if fb_enabled and fb_prob > 1e-6 and plan.arp_events:
                try:
                    rng2 = getattr(owner, "rng", rng)
                    if rng2.random() < fb_prob:
                        bpb2 = float(plan.beats_per_bar)
                        bars_i2 = int(plan.bars)
                        scale = list(getattr(plan.emotion, "scale_intervals", []) or [])
                        if scale and bpb2 > 1e-9 and bars_i2 > 0:
                            scale_pcs = [int(iv) % 12 for iv in scale]

                            def _deg_from_midi(m: int, root: int) -> Optional[int]:
                                rel = (int(m) - int(root)) % 12
                                if rel in scale_pcs:
                                    try:
                                        return int(scale_pcs.index(int(rel)))
                                    except Exception:
                                        return None
                                return None

                            # Convert arp events → (degree, duration) tokens.
                            seq: List[Tuple[int, float]] = []
                            chord_seq: List[str] = []
                            allowed_d = (0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0)

                            def _snap_d(d: float) -> float:
                                return float(min(allowed_d, key=lambda a: abs(float(a) - float(d))))

                            for ev in sorted(
                                list(plan.arp_events or []),
                                key=lambda e: float(e[3]) if len(e) == 6 else 0.0,
                            ):
                                if not (isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == 3):
                                    continue
                                st = float(ev[3])
                                bar = int(st // bpb2)
                                if bar < 0 or bar >= bars_i2 or bar >= len(plan.roots) or bar >= len(plan.chords):
                                    continue
                                root = int(plan.roots[bar])
                                midi0 = None
                                try:
                                    midi0 = int(ev[5][0]) if isinstance(ev[5], list) and ev[5] else int(ev[1])
                                except Exception:
                                    midi0 = None
                                if midi0 is None:
                                    continue
                                deg = _deg_from_midi(int(midi0), int(root))
                                if deg is None:
                                    continue
                                dur = _snap_d(max(0.25, float(ev[4])))
                                seq.append((int(deg), float(dur)))
                                chord_seq.append(str(plan.chords[bar] or ""))

                            # Need >= motif_len + 1 tokens for motif extraction.
                            if len(seq) >= 4:
                                mg = getattr(owner, "melody_gen", None)
                                mm = getattr(mg, "motif", None) if mg is not None else None
                                if mm is not None and hasattr(mm, "extract_from_melody"):
                                    try:
                                        mm.extract_from_melody(
                                            list(seq),
                                            source_emotion=str(getattr(plan.emotion, "name", "neutral") or "neutral").lower(),
                                            chord_sequence=list(chord_seq) if chord_seq else None,
                                        )
                                    except Exception:
                                        pass
                except Exception:
                    pass
        except Exception:
            logger.exception("Failed to generate arp events")

    # ------------------------------------------------------------------
    # 2) Melody as an "answer" after the harmonic/arp bed
    # ------------------------------------------------------------------
    effective_temp = float(temperature) * float(curve.get("temperature_mult", 1.0))
    timeline_melody = list((plan.timeline_targets or {}).get("melody_density", []) or [])
    if timeline_melody:
        effective_target_npb = float(target_notes_per_bar) * (
            sum(float(v) for v in timeline_melody) / max(1, len(timeline_melody))
        )
    else:
        effective_target_npb = float(target_notes_per_bar) * float(curve.get("melody_density_mult", 1.0))
    melody_total_notes_mult = float(curve.get("melody_total_notes_mult", 1.0))
    raw_cap = curve.get("melody_max_notes_per_phrase")
    melody_max_notes_per_phrase = int(raw_cap) if raw_cap is not None else None

    # Intro/outro: prefer more space. If user explicitly provided a style,
    # respect it, otherwise allow the policy to steer.
    effective_style = melody_style
    if melody_style == "auto" and section_role in {"intro", "outro"}:
        effective_style = "markov"

    hctx0 = getattr(owner, "_emotion_transition_handoff_ctx", None)
    fp_mult = float(curve.get("boundary_first_phrase_note_mult", 1.0)) if hctx0 else 1.0

    # ------------------------------------------------------------
    # Chorus interaction mode (melody ↔ arp)
    #
    # Simplified arrangement behavior:
    # Sections should build by *layering* around the chord plan (bed + additions),
    # not by "dialogue" (call/response) gestures that delay the lead entrance.
    # ------------------------------------------------------------
    chorusish_role_lc = str(section_role or "").strip().lower()
    chorusish = chorusish_role_lc in {"b", "chorus", "hook", "tag"}
    interaction_mode = ""
    interaction_shift_prob = 0.0
    interaction_arp_follow = 0.0
    if chorusish and arp_gate:
        requested_mode = str(curve.get("chorus_interaction_mode", "") or "").strip().lower()
        if requested_mode not in {"coexist", "unison", "dialogue", "fill"}:
            requested_mode = "coexist"
        interaction_mode = requested_mode
        if interaction_mode == "dialogue":
            interaction_shift_prob = 0.0
            interaction_arp_follow = 0.18
        elif interaction_mode == "fill":
            interaction_shift_prob = 0.0
            interaction_arp_follow = 0.22
        elif interaction_mode == "unison":
            interaction_shift_prob = 0.0
            interaction_arp_follow = 0.0
        else:
            interaction_shift_prob = 0.0
            interaction_arp_follow = 0.0
        # One-line section signature log (emotion-distinct chord/arp/melody macro choices).
        try:
            if interaction_mode and chorusish_role_lc:
                chord_dbg = getattr(owner, "_last_chord_template_pick_debug", {}) or {}
                # Prefer the general per-section chord family (works for intro/verse too).
                fam_dbg = getattr(owner, "_last_section_chord_family", {}) or {}
                chord_family = str(fam_dbg.get("family", "") or chord_dbg.get("chorus_family", "") or "")
                arp_dbg = getattr(owner, "_last_section_arp_mode", {}) or {}
                arp_mode_dbg = str(arp_dbg.get("mode", "") or "")
                logger.info(
                    "SECTION signature: emotion=%s role=%s chord_family=%s arp_mode=%s interaction=%s",
                    str(getattr(plan.emotion, "name", "") or ""),
                    str(section_role or ""),
                    chord_family if chord_family else "-",
                    arp_mode_dbg if arp_mode_dbg else "-",
                    str(interaction_mode),
                )
        except Exception:
            pass
    try:
        fam_dbg = getattr(owner, "_last_section_chord_family", {}) or {}
        chord_dbg = getattr(owner, "_last_chord_template_pick_debug", {}) or {}
        chord_family = str(fam_dbg.get("family", "") or chord_dbg.get("chorus_family", "") or "")
        arp_dbg = getattr(owner, "_last_section_arp_mode", {}) or {}
        arp_mode_dbg = str(arp_dbg.get("mode", "") or "")
        setattr(
            owner,
            "_last_section_signature",
            {
                "role": str(section_role or ""),
                "emotion": str(getattr(plan.emotion, "name", "") or ""),
                "chord_family": str(chord_family),
                "arp_mode": str(arp_mode_dbg),
                "interaction": str(interaction_mode or ""),
                "arp_enabled": bool(arp_gate),
                "motif_stage": str(getattr(owner, "_song_blueprint_motif_stage", "") or ""),
                "verse_sentence_pattern": str((getattr(plan, "arrangement_curve", {}) or {}).get("verse_sentence_pattern", "") or ""),
                "verse_development_mode": str((getattr(plan, "arrangement_curve", {}) or {}).get("verse_development_mode", "") or ""),
            },
        )
    except Exception:
        pass

    # Optional: when arp is present, bias toward "call/response" by delaying the lead entrance.
    # Default is off so the melody can coexist with the arp bed instead of waiting for space.
    def _melody_answer_delay_beats() -> float:
        # Simplified layered build: never delay the lead entrance for call/response.
        return 0.0

    delay_beats = _melody_answer_delay_beats()

    # 1-bar bridge policy for live emotion switches:
    # keep bar 0 as a pivot pickup (sparser + slightly later entrance), bar 1 resumes normal opening.
    if hctx0:
        fp_mult *= 0.72
        delay_beats = max(float(delay_beats), float(plan.beats_per_bar) * 0.5)

    # When arp is present, keep the lead simpler so it reads as a top line
    # over the arpeggiated bed instead of a second fast line.
    arp_led_role = str(section_role or "").lower() in {
        "intro", "a", "verse", "pre_chorus", "b", "chorus", "hook", "a_prime", "tag"
    }
    if arp_gate and arp_led_role:
        chorus_duck = resolve_config("composition", "chorus_melody_duck_with_arp", 0.97, float)
        chorus_duck = max(0.50, min(1.05, float(chorus_duck)))
        role_duck = {
            "intro": 0.98,
            "a": 1.00,
            "verse": 1.00,
            "pre_chorus": 1.00,
            "b": float(chorus_duck),
            "chorus": float(chorus_duck),
            "hook": float(chorus_duck),
            "a_prime": 1.00,
            "tag": max(0.50, min(1.05, float(chorus_duck) + 0.02)),
        }.get(str(section_role or "").lower(), 0.86)
        melody_total_notes_mult *= float(role_duck)
        effective_target_npb *= float(max(0.82, min(1.02, role_duck + 0.06)))
        role_phrase_cap = {
            "intro": 14,
            "a": 16,
            "verse": 16,
            "pre_chorus": 18,
            "b": 18,
            "chorus": 18,
            "hook": 18,
            "a_prime": 18,
            "tag": 18,
        }.get(str(section_role or "").lower())
        if role_phrase_cap is not None:
            if melody_max_notes_per_phrase is None:
                melody_max_notes_per_phrase = int(role_phrase_cap)
            else:
                melody_max_notes_per_phrase = int(min(int(melody_max_notes_per_phrase), int(role_phrase_cap)))

        # A fixed per-phrase cap must scale with section length. Otherwise
        # longer chorus/pre sections can never reach the configured role
        # notes-per-bar floor, no matter how high the target is.
    seq_fb = owner.arrangement_policy._FORM_SEQUENCES.get(owner.arrangement_policy.form_mode) or owner.arrangement_policy._FORM_SEQUENCES["default"]
    try:
        first_ai = next(i for i, r in enumerate(seq_fb) if r == "a")
    except StopIteration:
        first_ai = None
    hook_boost = (
        1.28
        if (
            first_ai is not None
            and getattr(owner, "_song_motif_hook_seeded", False)
            and section_role in ("a", "a_prime", "b", "tag")
            and section_index > first_ai
        )
        else 1.0
    )

    # Temporarily adjust motif and phrase repetition likelihood based on the
    # section role (A' tends to recall earlier material).
    original_motif_prob = owner.melody_gen.motif.motif_prob
    original_phrase_repeat = owner.melody_gen.phrase_repetition_prob
    original_rest_prob = owner.melody_gen.rest_prob
    handoff_motif_mult = 1.22 if hctx0 else 1.0
    owner.melody_gen.motif.motif_prob = max(
        0.0,
        min(
            0.98,
            float(original_motif_prob)
            * float(curve.get("motif_prob_mult", 1.0))
            * handoff_motif_mult
            * hook_boost,
        ),
    )
    reduce_hook_floors = resolve_config("composition", "melody_reduce_hook_motif_floors", True, bool)
    allow_pr_floor = resolve_config("composition", "melody_allow_min_phrase_repeat_prob_floor", False, bool)
    if getattr(owner, "_song_motif_hook_seeded", False) and section_role in {"b", "a_prime", "tag"}:
        if not reduce_hook_floors:
            owner.melody_gen.motif.motif_prob = max(owner.melody_gen.motif.motif_prob, 0.52)
    owner.melody_gen.phrase_repetition_prob = max(
        0.0,
        min(0.95, float(original_phrase_repeat) * float(curve.get("phrase_repeat_mult", 1.0))),
    )
    if (
        allow_pr_floor
        and getattr(owner, "_song_motif_hook_seeded", False)
        and section_role in {"b", "chorus", "hook", "a_prime", "tag"}
    ):
        # Cohesive songs: chorus/returns should confidently restate material.
        # Keep the floor modest so we still get variation between songs.
        floor = 0.30
        if section_role in {"b", "chorus", "hook"}:
            floor = 0.34
        elif section_role in {"tag"}:
            floor = 0.38
        owner.melody_gen.phrase_repetition_prob = max(owner.melody_gen.phrase_repetition_prob, float(floor))
    r_mult = max(0.5, min(1.5, float(curve.get("markov_rest_prob_mult", 1.0))))
    # Global knob: increase rest probability for all emotions (overall fewer lead notes).
    global_rest = resolve_config("composition", "melody_rest_prob_mult", 1.0, float)
    global_rest = max(0.5, min(2.0, float(global_rest)))
    arp_rest_mult = 1.0
    if arp_gate and arp_led_role:
        arp_rest_mult = 1.0 if section_role in {"pre_chorus", "b", "chorus", "hook", "tag", "a_prime"} else 1.04
    owner.melody_gen.rest_prob = max(
        0.02, min(0.5, float(original_rest_prob) * r_mult * global_rest * float(arp_rest_mult))
    )
    chord_rhythm_mult = max(0.5, min(1.55, float(curve.get("chord_rhythm_mult", 1.0))))
    chord_motion_layer = float(curve.get("chord_motion_mult", 1.0))
    chord_rhythm_targets = list((plan.timeline_targets or {}).get("chord_rhythm", []) or [])
    # Call/response: compute per-bar melody activity so chords can comp around the lead.
    melody_activity_by_bar: List[float] = []
    try:
        bpb = float(plan.beats_per_bar)
        bars_i = int(plan.bars)
        if bpb > 1e-9 and bars_i > 0:
            mel_dur = [0.0 for _ in range(bars_i)]
            for ev in list(plan.melody_events or []):
                if not (isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == 2):
                    continue
                st = float(ev[3])
                dur = float(ev[4])
                if dur <= 1e-9:
                    continue
                en = st + dur
                b0 = int(st // bpb)
                b1 = int((en - 1e-9) // bpb)
                for bi in range(max(0, b0), min(bars_i, b1 + 1)):
                    seg_s = max(st, float(bi) * bpb)
                    seg_e = min(en, float(bi + 1) * bpb)
                    if seg_e > seg_s + 1e-9:
                        mel_dur[bi] += float(seg_e - seg_s)
            melody_activity_by_bar = [float(max(0.0, min(1.0, d / bpb))) for d in mel_dur]
    except Exception:
        melody_activity_by_bar = []
    try:
        occ = None
        occ_weight_scale = 0.0
        if arp_gate and plan.arp_events and arp_led_role:
            occ_on = resolve_config("composition", "melody_arp_occupied_masking_enabled", True, bool)
            occ_weight_scale = resolve_config("composition", "melody_arp_occupied_weight_global_scale", 0.58, float)
            occ_weight_scale = max(0.0, min(1.0, float(occ_weight_scale)))
            if occ_on and occ_weight_scale > 1e-6:
                try:
                    occ = []
                    bpb_occ = float(plan.beats_per_bar)
                    for ev in list(plan.arp_events or []):
                        if not (isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == 3):
                            continue
                        _ch, midi, _vel, st, dur, notes = ev
                        s0 = float(st)
                        e0 = float(st) + float(dur)
                        beat_in_bar = float(s0 % bpb_occ) if bpb_occ > 1e-9 else 0.0
                        strong = abs(beat_in_bar - 0.0) <= 1e-6 or abs(beat_in_bar - 2.0) <= 1e-6
                        w0 = 0.58 if strong else 0.34
                        if float(dur) >= 0.95:
                            w0 *= 0.82
                        pcs0 = None
                        try:
                            if isinstance(notes, list) and notes:
                                pcs0 = sorted({int(n) % 12 for n in notes if isinstance(n, int)})
                            else:
                                pcs0 = [int(midi) % 12]
                        except Exception:
                            pcs0 = [int(midi) % 12]
                        occ.append((float(s0), float(e0), float(w0), pcs0))
                except Exception:
                    occ = None
        harmonic = getattr(plan, "harmonic_plan", None) or HarmonicPlan.from_section_plan(plan)
        try:
            from composition.joint_section_plan import hook_degrees_from_plan_dict

            hook_cell = hook_degrees_from_plan_dict(getattr(plan, "joint_section_plan", None))
            setattr(owner, "_joint_hook_degrees", hook_cell if hook_cell else None)
        except Exception:
            try:
                setattr(owner, "_joint_hook_degrees", None)
            except Exception:
                pass
        plan.melody_events = owner.melody_manager.generate_melody_events_from_harmonic_plan(
            plan.emotion,
            harmonic,
            effective_temp,
            effective_target_npb,
            effective_style,
            melody_styles,
            occupied_intervals=occ,
            first_phrase_note_scale=fp_mult,
            melody_total_notes_mult=melody_total_notes_mult,
            melody_max_notes_per_phrase=melody_max_notes_per_phrase,
            section_role=section_role,
            timeline_density_by_bar=list((plan.timeline_targets or {}).get("melody_density", []) or []),
            breath_window_by_bar=list((plan.timeline_targets or {}).get("breath_window", []) or []),
        )

        # Guardrail: if lead gets over-suppressed by compatibility masks,
        # regenerate once with lighter occupancy so sections keep melodic intent.
        try:
            role_lc = str(section_role or "").strip().lower()

            def _lead_count(evs):
                return sum(
                    1
                    for ev in list(evs or [])
                    if isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == 2
                )

            role_min_npb = {
                "intro": 0.95,
                "a": 1.10,
                "verse": 1.10,
                "pre_chorus": 1.35,
                "b": 1.45,
                "chorus": 1.45,
                "hook": 1.45,
                "tag": 1.35,
                "a_prime": 1.20,
                "outro": 0.85,
            }
            min_notes = int(max(1, round(float(plan.bars) * float(role_min_npb.get(role_lc, 0.95)))))
            current_notes = _lead_count(plan.melody_events)
            if current_notes < min_notes:
                relaxed_occ = []
                for item in list(occ or []):
                    try:
                        s0, e0 = float(item[0]), float(item[1])
                        w0 = float(item[2]) if len(item) >= 3 and item[2] is not None else 1.0
                        w0 = float(w0) * float(occ_weight_scale)
                        pcs0 = item[3] if len(item) >= 4 else None
                        relaxed_occ.append((s0, e0, max(0.18, min(0.80, w0 * 0.45)), pcs0))
                    except Exception:
                        continue
                retry = owner.melody_manager.generate_melody_events_from_harmonic_plan(
                    plan.emotion,
                    harmonic,
                    effective_temp,
                    effective_target_npb,
                    effective_style,
                    melody_styles,
                    occupied_intervals=relaxed_occ,
                    first_phrase_note_scale=fp_mult,
                    melody_total_notes_mult=float(melody_total_notes_mult) * 1.16,
                    melody_max_notes_per_phrase=melody_max_notes_per_phrase,
                    section_role=section_role,
                    timeline_density_by_bar=list((plan.timeline_targets or {}).get("melody_density", []) or []),
                    breath_window_by_bar=list((plan.timeline_targets or {}).get("breath_window", []) or []),
                )
                if _lead_count(retry) > current_notes:
                    plan.melody_events = list(retry or [])
        except Exception:
            pass

        skip_melody_blueprint = resolve_config("composition", "joint_plan_markov_conditioning_enabled", False, bool)
        try:
            if not skip_melody_blueprint:
                _apply_chorus_hook_blueprint_to_melody(
                    plan,
                    chorus_hook_blueprint,
                    section_role=str(section_role or ""),
                )
            _apply_bright_chorus_payoff_to_melody(
                plan,
                chorus_hook_blueprint,
                section_role=str(section_role or ""),
            )
        except Exception:
            pass
        try:
            setattr(owner, "_joint_hook_degrees", None)
        except Exception:
            pass

        # If the lead median sits in the same register as the arp, lift the whole line
        # by an octave (when range headroom allows). This reads as "melody above the bed"
        # instead of rhythmically ducking around it.
        if arp_gate and plan.arp_events and plan.melody_events:
            lift_on = resolve_config("composition", "melody_octave_lift_vs_arp_when_median_at_or_below_arp", True, bool)
            max_gap = resolve_config("composition", "melody_octave_lift_vs_arp_max_median_gap_semitones", 2, int)
            headroom = resolve_config("composition", "melody_octave_lift_vs_arp_min_headroom_semitones", 2, int)
            max_gap = max(0, min(24, int(max_gap)))
            headroom = max(0, min(24, int(headroom)))
            _RLM = RANGE_LIMITER
            if lift_on and _RLM is not None:
                try:

                    def _median_int(vals: List[int]) -> Optional[int]:
                        xs = sorted(int(x) for x in vals)
                        if not xs:
                            return None
                        mid = len(xs) // 2
                        if len(xs) % 2 == 1:
                            return int(xs[mid])
                        return int(round(0.5 * (float(xs[mid - 1]) + float(xs[mid]))))

                    mel_ps: List[int] = []
                    for ev in list(plan.melody_events or []):
                        if not (isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == 2):
                            continue
                        try:
                            mel_ps.append(int(ev[5][0]) if isinstance(ev[5], list) and ev[5] else int(ev[1]))
                        except Exception:
                            continue
                    arp_ps: List[int] = []
                    for ev in list(plan.arp_events or []):
                        if not (isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == 3):
                            continue
                        try:
                            arp_ps.append(int(ev[5][0]) if isinstance(ev[5], list) and ev[5] else int(ev[1]))
                        except Exception:
                            continue
                    if mel_ps and arp_ps:
                        med_m = int(_median_int(mel_ps) or 0)
                        med_a = int(_median_int(arp_ps) or 0)
                        if int(med_m) - int(med_a) <= int(max_gap):
                            try:
                                max_n = int(_RLM.configs[2].max_note)  # type: ignore[attr-defined]
                            except Exception:
                                max_n = 88
                            cand: List[int] = []
                            ok = True
                            for p in mel_ps:
                                c = int(_RLM.clamp_note(int(p) + 12, 2))
                                cand.append(int(c))
                                if int(c) <= int(p) + 10:
                                    ok = False
                                    break
                            if ok and cand and int(max(cand)) <= int(max_n) - int(headroom):
                                lifted_m: List[Tuple] = []
                                for ev in list(plan.melody_events or []):
                                    if not (isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == 2):
                                        lifted_m.append(ev)
                                        continue
                                    ch, midi, vel, st, dur, notes = ev
                                    m2 = int(_RLM.clamp_note(int(midi) + 12, 2))
                                    n2 = list(notes) if isinstance(notes, list) else notes
                                    if isinstance(n2, list) and n2:
                                        try:
                                            n2[0] = int(m2)
                                        except Exception:
                                            pass
                                    lifted_m.append((int(ch), int(m2), int(vel), float(st), float(dur), n2))
                                plan.melody_events = lifted_m
                except Exception:
                    pass

        if delay_beats > 1e-6 and plan.melody_events:
            # Leave space at the front: drop any lead notes that start before delay.
            original_melody = list(plan.melody_events)
            delayed = [
                ev for ev in plan.melody_events
                if (len(ev) == 6 and float(ev[3]) + 1e-9 >= float(delay_beats))
            ]
            # Safety: never allow the delay gate to wipe the section topline.
            plan.melody_events = delayed if delayed else original_melody

        shift_on = False
        shift_on = resolve_config("composition", "melody_chorus_strong_beat_shift_vs_arp_enabled", False, bool)
        # New chorus interaction system: enable strong-beat shift probabilistically in dialogue mode.
        if (interaction_mode == "dialogue") and plan.melody_events:
            try:
                drng = getattr(owner, "deterministic_rng", None)
                r = drng("chorus_strongbeat_shift", str(getattr(plan.emotion, "name", "") or ""), int(section_index)) if callable(drng) else rng
                u = float(getattr(r, "random", rng.random)())
            except Exception:
                u = float(rng.random())
            shift_on = bool(u < float(interaction_shift_prob))

        if shift_on and arp_gate and plan.melody_events and str(section_role or "").lower() in {"b", "chorus", "hook", "tag"}:
            # Further enforce call/response: avoid landing lead notes exactly on
            # strong beats (0,1,2,3) where the arp is most perceptually dense.
            bpb = float(plan.beats_per_bar)
            shifted = []
            for ev in plan.melody_events:
                if len(ev) != 6:
                    shifted.append(ev)
                    continue
                ch, midi, vel, start, dur, notes = ev
                st = float(start)
                bar_pos = st % max(1e-6, bpb)
                # If near an integer beat inside the bar, nudge to the "and".
                if abs(bar_pos - round(bar_pos)) <= 1e-6:
                    st2 = st + 0.5
                    # Keep inside section bounds.
                    if st2 < float(plan.bars) * bpb - 1e-6:
                        st = st2
                shifted.append((ch, midi, vel, st, dur, notes))
            plan.melody_events = shifted

        # Bidirectional density negotiation: when the realized melody is very busy
        # in a bar, soften or thin arp hits in that bar so call/response reads.
        if arp_gate and plan.arp_events and plan.melody_events and not layers_indep:
            follow = resolve_config("composition", "arp_density_follow_melody", 0.0, float)
            # Chorus interaction modes override follow strength:
            # - dialogue/fill: follow busy melody to preserve "answer" clarity
            # - coexist/unison: keep the arp bed stable
            if interaction_mode in {"dialogue", "fill"}:
                follow = max(float(follow), float(interaction_arp_follow))
            elif interaction_mode in {"coexist", "unison"}:
                # Keep a small amount of post-melody thinning even in
                # coexist/unison modes so dense arp beds do not mask the
                # topline on high-activity bars.
                follow = max(min(float(follow), 0.10), 0.06 if float(follow) > 1e-6 else 0.0)
            follow = max(0.0, min(1.0, float(follow)))
            if follow > 1e-6:
                try:
                    bpb = float(plan.beats_per_bar)
                    bars_i = int(plan.bars)
                    if bpb > 1e-9 and bars_i > 0:
                        arp_before = [0 for _ in range(int(bars_i))]
                        try:
                            for ev in list(plan.arp_events or []):
                                if not (isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == 3):
                                    continue
                                bi0 = int(float(ev[3]) // float(bpb))
                                if 0 <= int(bi0) < int(bars_i):
                                    arp_before[int(bi0)] += 1
                        except Exception:
                            pass
                        # endregion agent log
                        mel_dur = [0.0 for _ in range(bars_i)]
                        lead_ints_follow = []
                        for ev in list(plan.melody_events or []):
                            if not (isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == 2):
                                continue
                            st = float(ev[3])
                            dur = float(ev[4])
                            if dur <= 1e-9:
                                continue
                            en = st + dur
                            lead_ints_follow.append((float(st), float(en)))
                            b0 = int(st // bpb)
                            b1 = int((en - 1e-9) // bpb)
                            for bi in range(max(0, b0), min(bars_i, b1 + 1)):
                                seg_s = max(st, float(bi) * bpb)
                                seg_e = min(en, float(bi + 1) * bpb)
                                if seg_e > seg_s + 1e-9:
                                    mel_dur[bi] += float(seg_e - seg_s)
                        activity = [float(max(0.0, min(1.0, d / bpb))) for d in mel_dur]

                        # Normalize activity to 0..1 across this section (avoid emotion-specific tuning).
                        if activity:
                            mx = float(max(activity)) if max(activity) > 1e-9 else 1.0
                            if mx > 1e-9:
                                activity = [float(max(0.0, min(1.0, a / mx))) for a in activity]

                        try:
                            drng = getattr(owner, "deterministic_rng", None)
                        except Exception:
                            drng = None

                        plan.arp_events = _supportive_arp_follow_lead(
                            list(plan.arp_events or []),
                            list(plan.melody_events or []),
                            beats_per_bar=float(bpb),
                            bars=int(bars_i),
                            follow=float(follow),
                            rng=rng,
                            deterministic_rng=drng,
                            mask_strength=_masking_focus_strength_for_emotion(
                                str(getattr(plan.emotion, "name", "") or ""),
                                section_role=str(section_role or ""),
                            ),
                        )
                except Exception:
                    pass

        # Post-pass: refine arp pitches against the realized lead.
        # Keep arp rhythm constant; only swap pitches when the lead is active
        # and we would otherwise collide (unison pitch class or too-close register).
        if arp_gate and plan.arp_events and plan.melody_events:
            refine_enabled = resolve_config("composition", "arp_refine_against_lead_enabled", True, bool)
            sep_margin = resolve_config("composition", "arp_melody_register_separation_semitones", 5, int)
            harm_policy_on = resolve_config("composition", "dialogue_harmony_policy_enabled", False, bool)
            harm_policy_strength = resolve_config("composition", "dialogue_harmony_policy_strength", 0.75, float)
            reg_choreo_on = resolve_config("composition", "register_choreography_enabled", False, bool)
            reg_choreo_strength = resolve_config("composition", "register_choreography_strength", 0.75, float)
            sep_margin = max(0, min(24, int(sep_margin)))
            harm_policy_strength = max(0.0, min(1.0, float(harm_policy_strength)))
            reg_choreo_strength = max(0.0, min(1.0, float(reg_choreo_strength)))
            if refine_enabled:
                try:
                    from midi.midi_range_limiter import RANGE_LIMITER as _RL
                except Exception:
                    _RL = None

                try:
                    bpb = float(plan.beats_per_bar)
                    # Lead activity intervals (st,en,pitch).
                    lead_ints = []
                    for ev in list(plan.melody_events or []):
                        if not (isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == 2):
                            continue
                        st = float(ev[3])
                        en = st + float(ev[4])
                        if en <= st + 1e-9:
                            continue
                        try:
                            p = int(ev[5][0]) if isinstance(ev[5], list) and ev[5] else int(ev[1])
                        except Exception:
                            continue
                        lead_ints.append((st, en, int(p)))

                    def _lead_pitch_at(t: float) -> Optional[int]:
                        for s, e, p in lead_ints:
                            if float(s) - 1e-9 <= float(t) <= float(e) - 1e-9:
                                return int(p)
                        return None

                    # Register choreography target separation per bar.
                    sep_by_bar = [int(sep_margin) for _ in range(int(plan.bars))]
                    if reg_choreo_on and reg_choreo_strength > 1e-6:
                        try:
                            dens = list((plan.timeline_targets or {}).get("melody_density", []) or [])
                        except Exception:
                            dens = []
                        rlc = str(section_role or "").strip().lower()
                        for bi in range(int(plan.bars)):
                            d = float(dens[bi]) if 0 <= bi < len(dens) else float(getattr(plan.emotion, "density", 0.5) or 0.5)
                            delta = int(round((d - 0.55) * 6.0 * reg_choreo_strength))
                            if rlc in {"a_prime"} and (bi % 4) in {1, 2}:
                                delta -= int(round(2.0 * reg_choreo_strength))
                            if rlc in {"b", "chorus", "hook"}:
                                delta += int(round(1.0 * reg_choreo_strength))
                            sep_by_bar[bi] = int(max(3, min(12, int(sep_margin) + int(delta))))

                    def _pick_alt_chord_tone(
                        *,
                        bar: int,
                        cur: int,
                        lead_pitch: int,
                        sep_target: int,
                    ) -> int:
                        # Use voiced chord tones if present; otherwise fall back to original note.
                        chord_notes = []
                        try:
                            chord_notes = list((plan.chosen_chord or [])[bar] or [])
                        except Exception:
                            chord_notes = []
                        pcs = sorted({int(n) % 12 for n in chord_notes if isinstance(n, int)})
                        if not pcs:
                            return int(cur)
                        lead_pc = int(lead_pitch) % 12
                        base_oct = (int(cur) // 12) * 12
                        cands = []
                        for pc in pcs:
                            if int(pc) == int(lead_pc):
                                continue
                            for k in (-24, -12, 0, 12, 24):
                                cand = int(base_oct) + int(pc) + int(k)
                                if _RL is not None:
                                    try:
                                        cand = int(_RL.clamp_note(int(cand), 3))
                                    except Exception:
                                        cand = int(cand)
                                cands.append(int(cand))
                        # Prefer staying under the lead by margin if possible.
                        under = [c for c in cands if int(c) <= int(lead_pitch) - int(sep_target)]
                        pool = under if under else cands
                        if not pool:
                            return int(cur)
                        # Harmony-aware dialogue: optionally prefer consonant support intervals (3rds/6ths)
                        # relative to the lead, otherwise just choose nearest safe chord tone.
                        if harm_policy_on and harm_policy_strength > 1e-6:
                            try:
                                rlc = str(section_role or "").strip().lower()
                            except Exception:
                                rlc = ""
                            # Default policy by role (cheap and musically robust).
                            # chorus/tag: support; a_prime: answer; else: avoid.
                            if rlc in {"b", "chorus", "hook", "tag"}:
                                policy = "support"
                            elif rlc in {"a_prime"}:
                                policy = "answer"
                            else:
                                policy = "avoid"
                            # Consonant semitone distances for support intervals.
                            consonant = {3, 4, 8, 9}
                            def _score(n: int) -> tuple:
                                # Primary: keep under lead; Secondary: avoid unison PC; Tertiary: consonance.
                                d_cur = abs(int(n) - int(cur))
                                d_lead = abs(int(n) - int(lead_pitch))
                                pc_dist = (int(n) - int(lead_pitch)) % 12
                                is_con = int(pc_dist) in consonant
                                # Blend: at low strength, mostly nearest; at high strength, prefer consonance.
                                con_term = 0 if is_con else 1
                                if policy == "support":
                                    return (con_term, d_cur, d_lead)
                                if policy == "answer":
                                    # Answer: prefer more separation and avoid consonant “doubling”.
                                    return (0 if not is_con else 1, -d_lead, d_cur)
                                # Avoid: just keep far and non-unison.
                                return (0, d_lead, d_cur)
                            try:
                                best = min(pool, key=_score)
                                return int(best)
                            except Exception:
                                pass
                        return int(min(pool, key=lambda n: (abs(int(n) - int(cur)), abs(int(n) - int(lead_pitch)))))

                    refined = []
                    for ev in list(plan.arp_events or []):
                        if not (isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == 3):
                            refined.append(ev)
                            continue
                        ch, midi, vel, st, dur, notes = ev
                        t0 = float(st)
                        lp = _lead_pitch_at(t0)
                        if lp is None:
                            refined.append(ev)
                            continue
                        try:
                            an = int(notes[0]) if isinstance(notes, list) and notes else int(midi)
                        except Exception:
                            refined.append(ev)
                            continue
                        # Trigger only on clear collisions.
                        same_pc = (int(an) % 12) == (int(lp) % 12)
                        bar = int(float(t0) // float(bpb)) if bpb > 1e-9 else 0
                        sep_target = int(sep_by_bar[bar]) if 0 <= bar < len(sep_by_bar) else int(sep_margin)
                        too_high = int(an) > int(lp) - int(sep_target)
                        if not (same_pc or too_high):
                            refined.append(ev)
                            continue
                        alt = _pick_alt_chord_tone(bar=bar, cur=int(an), lead_pitch=int(lp), sep_target=int(sep_target))
                        # Final fallback: if still too close after swap, drop an octave.
                        try:
                            if int(alt) > int(lp) - int(sep_target):
                                alt = int(alt) - 12
                                if _RL is not None:
                                    alt = int(_RL.clamp_note(int(alt), 3))
                        except Exception:
                            pass
                        refined.append((int(ch), int(alt), int(vel), float(st), float(dur), [int(alt)]))

                    plan.arp_events = refined
                except Exception:
                    pass

        # Final chorus-register guard: refinement prefers supporting tones under the lead,
        # but choruses still need an audible register lift over verse arps.
        if arp_gate and plan.arp_events and str(section_role or "").lower() in {"b", "chorus", "hook", "tag"}:
            try:
                notes0 = [
                    int(ev[1])
                    for ev in list(plan.arp_events or [])
                    if isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == 3 and isinstance(ev[1], int)
                ]
                high_count = sum(1 for n in notes0 if int(n) >= 72)
                if notes0 and high_count < max(1, int(round(0.12 * len(notes0)))):
                    lifted = []
                    for ev in list(plan.arp_events or []):
                        if not (isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == 3):
                            lifted.append(ev)
                            continue
                        ch, midi, vel, st, dur, notes = ev
                        m2 = int(RANGE_LIMITER.clamp_note(int(midi) + 12, 3))
                        lifted.append((int(ch), int(m2), int(vel), float(st), float(dur), [int(m2)]))
                    plan.arp_events = lifted
            except Exception:
                pass

        # Never allow consecutive arp hits on the same MIDI pitch (refine/lift can reintroduce repeats).
        if arp_gate and plan.arp_events:
            try:
                from composition.arpeggiator_engine import (
                    repair_arp_consecutive_same_midi,
                    repair_arp_duplicate_start_times,
                )

                cc = getattr(plan, "chosen_chord", None)
                plan.arp_events = repair_arp_consecutive_same_midi(
                    list(plan.arp_events or []),
                    chord_notes_by_bar=list(cc) if isinstance(cc, list) else None,
                    beats_per_bar=float(plan.beats_per_bar),
                )
                plan.arp_events = repair_arp_duplicate_start_times(list(plan.arp_events or []))
            except Exception:
                pass

        # Debug: summarize arp continuity in chorus-like roles.
        try:
            rlc = str(section_role or "").strip().lower()
        except Exception:
            rlc = ""
        # Per-note octave nudge: if the lead overlaps the arp on a clashing pitch, move the
        # melody by ±12 (within range) instead of thinning either layer.
        clash_on = resolve_config("composition", "melody_octave_resolve_arp_clash_enabled", True, bool)
        clash_semis = resolve_config("composition", "melody_arp_clash_max_semitones", 0, int)
        clash_up = resolve_config("composition", "melody_arp_clash_octave_resolve_prefer_up", True, bool)
        unison_on = resolve_config("composition", "melody_unison_shift_vs_arp_enabled", True, bool)
        unison_interval = resolve_config("composition", "melody_unison_shift_interval_semitones", 7, int)
        # Always resolve exact unison overlaps by shifting the melody up a fifth.
        # This applies even when layers are "independent" — it is a pure register fix,
        # not a density/groove coupling behavior.
        if arp_gate and unison_on and plan.melody_events and plan.arp_events:
            try:
                if resolve_melody_unisons_vs_arp_by_interval is not None:
                    plan.melody_events = resolve_melody_unisons_vs_arp_by_interval(
                        list(plan.melody_events or []),
                        list(plan.arp_events or []),
                        enabled=True,
                        interval_semitones=int(unison_interval),
                    )
            except Exception:
                pass
        if arp_gate and clash_on and plan.melody_events and plan.arp_events:
            try:
                before = list(plan.melody_events or [])
                plan.melody_events = resolve_melody_octaves_vs_arp_clashes(
                    list(plan.melody_events or []),
                    list(plan.arp_events or []),
                    enabled=True,
                    clash_max_semitones=int(clash_semis),
                    prefer_up=bool(clash_up),
                )
                # Final strict-scale snap for the lead. Both the unison-shift
                # (perfect-fifth) and the octave-clash resolver above can land
                # the lead on a non-modal pitch class even though the generator
                # emits in-scale MIDI; this single choke-point restores the
                # authored modal identity of the section's lead voice.
                if resolve_config("composition", "melody_strict_scale_enabled", True, bool):
                    from composition.melody_arp_octave_resolve import snap_lead_events_to_strict_scale
                    section_root_pc = int(getattr(owner, "_section_root_pc", 0)) % 12
                    plan.melody_events = snap_lead_events_to_strict_scale(
                        list(plan.melody_events or []),
                        emotion=_perceptual_scale_emotion(owner, plan.emotion),
                        section_root_pc=int(section_root_pc),
                        melody_channel=2,
                    )
                # Debug: count octave shifts applied.
                try:
                    def _p(ev):
                        try:
                            return int(ev[5][0]) if isinstance(ev, tuple) and len(ev) == 6 and isinstance(ev[5], list) and ev[5] else int(ev[1])
                        except Exception:
                            return None
                    shifts = 0
                    total = 0
                    for a, b in zip(before, list(plan.melody_events or [])):
                        if not (isinstance(a, tuple) and len(a) == 6 and int(a[0]) == 2):
                            continue
                        pa = _p(a)
                        pb = _p(b)
                        if pa is None or pb is None:
                            continue
                        total += 1
                        if int(pb) != int(pa):
                            shifts += 1
                    rlc2 = str(section_role or "").strip().lower()
                    if rlc2 in {"b", "chorus", "hook", "tag"}:
                        pass
                except Exception:
                    pass
            except Exception:
                pass

        # ------------------------------------------------------------------
        # Explicit A-material reuse: capture a 1-bar rhythm cell from the first
        # verse (`a`) so later choruses can restate it via motif injection.
        # ------------------------------------------------------------------
        try:
            if getattr(owner, "_song_rhythm_cell", None) is None:
                seq_fb = owner.arrangement_policy._FORM_SEQUENCES.get(owner.arrangement_policy.form_mode) or owner.arrangement_policy._FORM_SEQUENCES["default"]
                try:
                    first_a = next(i for i, r in enumerate(seq_fb) if r == "a")
                except StopIteration:
                    first_a = None
                if first_a is not None and int(section_index) == int(first_a) and str(section_role) == "a":
                    bpb = float(plan.beats_per_bar)
                    cell: List[float] = []
                    t_sum = 0.0
                    # Use the first bar worth of lead durations (post call/response shifts).
                    for ev in list(plan.melody_events or []):
                        if not (isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == 2):
                            continue
                        st = float(ev[3])
                        if st < -1e-6:
                            continue
                        if st >= float(bpb) - 1e-6:
                            break
                        dur = max(0.0, float(ev[4]))
                        if dur <= 1e-6:
                            continue
                        # Clip to bar.
                        dur = min(dur, float(bpb) - st)
                        # Stop once we have a full bar of rhythm.
                        if t_sum + dur > float(bpb) + 1e-6:
                            dur = max(0.0, float(bpb) - float(t_sum))
                        if dur > 1e-6:
                            cell.append(float(dur))
                            t_sum += float(dur)
                        if t_sum >= float(bpb) - 1e-6:
                            break
                    # Keep only meaningful cells (2+ onsets).
                    if len(cell) >= 2 and sum(cell) >= float(bpb) * 0.65:
                        setattr(owner, "_song_rhythm_cell", list(cell))
        except Exception:
            pass

        owner.try_seed_first_verse_motif_hook(plan, section_index)
        try:
            if hasattr(owner, "motif_plan") and owner.motif_plan is not None:
                enabled = resolve_config("composition", "hook_restatement_enabled", True, bool)
                if enabled:
                    owner.motif_plan.apply_to_section_plan(plan, role=section_role, section_index=section_index)
        except Exception:
            logger.debug("MotifPlan application failed", exc_info=True)

        # Bidirectional motif glue: if a hook motif exists, softly align some lead onsets
        # toward the motif rhythm grid (keeps layers feeling like one composed idea).
        motif_glue = resolve_config("composition", "motif_melody_alignment_enabled", True, bool)
        motif_strength = resolve_config("composition", "motif_melody_alignment_strength", 0.25, float)
        motif_strength = max(0.0, min(1.0, float(motif_strength)))
        if motif_glue and motif_strength > 1e-6 and plan.melody_events:
            try:
                hook = None
                if hasattr(owner, "motif_plan") and owner.motif_plan is not None:
                    hook = owner.motif_plan.theme()
                if hook is not None and getattr(hook, "rhythms", None):
                    bpb = float(plan.beats_per_bar)
                    # Motif onsets (in beats) within one bar.
                    onsets = []
                    t = 0.0
                    for r in list(getattr(hook, "rhythms", []) or []):
                        onsets.append(float(t))
                        t += float(r)
                    onsets = [o for o in onsets if -1e-6 <= o < float(bpb) - 1e-6]
                    if onsets:
                        # Snap window scales with strength; keep small to avoid audible "teleport".
                        snap_eps = 0.04 + 0.14 * float(motif_strength)
                        snapped = []
                        total_beats = float(plan.bars) * float(bpb)
                        for ev in list(plan.melody_events or []):
                            if not (isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == 2):
                                snapped.append(ev)
                                continue
                            ch, midi, vel, st, dur, notes = ev
                            st = float(st)
                            bar_pos = float(st % bpb) if bpb > 1e-9 else float(st)
                            nearest = min(onsets, key=lambda o: abs(float(o) - float(bar_pos)))
                            if abs(float(nearest) - float(bar_pos)) <= float(snap_eps):
                                st2 = float(st - bar_pos + float(nearest))
                                if 0.0 <= st2 <= total_beats - 1e-6:
                                    st = st2
                            snapped.append((int(ch), midi, int(vel), float(st), float(dur), notes))
                        plan.melody_events = snapped
            except Exception:
                pass

        # Cross-lane motif bus: derive a lightweight motif cell from the realized
        # lead and expose it as shared memory for arp/counter in subsequent sections.
        bus_on = resolve_config("composition", "cross_lane_motif_bus_enabled", True, bool)
        if bus_on and plan.melody_events:
            try:
                bus = planner._cross_lane_motif_bus_from_melody(
                    list(plan.melody_events or []),
                    bars=int(plan.bars),
                    beats_per_bar=float(plan.beats_per_bar),
                    section_role=section_role,
                )
                if isinstance(bus, dict):
                    setattr(owner, "_cross_lane_motif_bus", dict(bus))
            except Exception:
                pass

        # ------------------------------------------------------------------
        # Phrase cadence landing constraints (cheap post-pass).
        # Adjust the last lead note near phrase boundaries to land more intentionally:
        #   - pre-chorus: keep open (avoid tonic when possible)
        #   - chorus/outro/tag: prefer tonic landings (when available)
        #   - verse: light chord-tone alignment only
        # ------------------------------------------------------------------
        enabled = resolve_config("composition", "melody_phrase_cadence_landing_enabled", True, bool)
        prob = resolve_config("composition", "melody_phrase_cadence_landing_prob", 0.92, float)
        eps_beats = resolve_config("composition", "melody_phrase_cadence_landing_eps_beats", 0.65, float)
        prob = max(0.0, min(1.0, float(prob)))
        eps_beats = max(0.15, min(1.25, float(eps_beats)))
        if enabled and prob > 1e-6 and plan.melody_events and getattr(owner, "rng", None) is not None:
            try:
                rng = owner.rng
                bpb = float(plan.beats_per_bar)
                phrase_len = phrase_length_bars_clamped(2, 8)
                role_lc = str(section_role or "").lower()

                # Per-bar chord pitch-class sets (prefer voiced chords).
                pcs_by_bar: List[set] = []
                for bi in range(int(plan.bars)):
                    pcs = set()
                    try:
                        if getattr(plan, "chosen_chord", None) and bi < len(plan.chosen_chord):
                            pcs = {int(n) % 12 for n in (plan.chosen_chord[bi] or []) if isinstance(n, int) and int(n) > 0}
                    except Exception:
                        pcs = set()
                    pcs_by_bar.append(set(pcs))

                def _nearest_with_pc(m: int, pc: int) -> int:
                    # Choose nearest MIDI note with pitch class pc.
                    base = int(m)
                    cands = [base + k for k in (-24, -12, 0, 12, 24)]
                    best = None
                    best_d = 999
                    for x in cands:
                        x2 = int(x + ((pc - (x % 12)) % 12))
                        d = abs(int(x2) - int(base))
                        if d < best_d:
                            best_d = d
                            best = x2
                    return int(best if best is not None else base)

                for bar in range(int(plan.bars)):
                    # Phrase boundary bars or explicit cadence window bars.
                    cad_win = list((plan.timeline_targets or {}).get("cadence_window", []) or [])
                    is_phrase_end = ((bar + 1) % phrase_len) == 0
                    is_cad_bar = bool(bar < len(cad_win) and bool(cad_win[bar]))
                    if not (is_phrase_end or is_cad_bar):
                        continue
                    if rng.random() > prob:
                        continue

                    pcs = pcs_by_bar[bar] if bar < len(pcs_by_bar) else set()
                    if not pcs:
                        continue
                    bar_end = float((bar + 1) * bpb)
                    # Candidate: last lead note that reaches into the final eps_beats.
                    cand_idx = None
                    cand_st = -1.0
                    for i, ev in enumerate(list(plan.melody_events or [])):
                        if not (isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == 2):
                            continue
                        st = float(ev[3])
                        dur = float(ev[4])
                        if st < float(bar * bpb) - 1e-6 or st >= float((bar + 1) * bpb) + 1e-6:
                            continue
                        if st + dur < float(bar_end) - float(eps_beats):
                            continue
                        if st >= cand_st:
                            cand_st = st
                            cand_idx = i
                    if cand_idx is None:
                        continue

                    ev = list(plan.melody_events[cand_idx])
                    midi0 = int(ev[1])
                    tonic_pc = int(plan.roots[bar]) % 12 if getattr(plan, "roots", None) and bar < len(plan.roots) else int(midi0) % 12

                    target_pc = None
                    if role_lc in {"pre_chorus"}:
                        # Keep it open: avoid tonic if there is any alternative.
                        non_t = [pc for pc in pcs if int(pc) != int(tonic_pc)]
                        if non_t:
                            target_pc = min(non_t, key=lambda pc: abs(((int(midi0) % 12) - int(pc)) % 12))
                    elif role_lc in {"b", "chorus", "outro", "tag"}:
                        if int(tonic_pc) in pcs:
                            target_pc = int(tonic_pc)
                    # Fallback: nearest chord tone to current pitch class.
                    if target_pc is None:
                        target_pc = min(list(pcs), key=lambda pc: min(abs(int(pc) - (int(midi0) % 12)), 12 - abs(int(pc) - (int(midi0) % 12))))

                    midi1 = _nearest_with_pc(int(midi0), int(target_pc))
                    # Keep within lead range.
                    midi1 = int(RANGE_LIMITER.clamp_note(int(midi1), 2))
                    ev[1] = int(midi1)
                    plan.melody_events[cand_idx] = tuple(ev)
            except Exception:
                pass

        try:
            _stabilize_low_flow_lead_harmony(
                plan,
                emotion_name=str(getattr(plan.emotion, "name", "") or ""),
                tempo_multiplier=float(getattr(plan.emotion, "tempo_multiplier", 1.0) or 1.0),
            )
        except Exception:
            pass

        # Chorus hook memory: first chorus captures its opening phrase; later
        # chorus/tag sections restate it before any counterline is written.
        try:
            _apply_chorus_hook_memory(
                owner,
                plan,
                section_role=str(section_role),
                section_index=int(section_index),
            )
            _capture_chorus_hook_memory(
                owner,
                plan,
                section_role=str(section_role),
                section_index=int(section_index),
            )
        except Exception:
            pass

        run_counter_melody_stage(
            owner,
            plan,
            curve=curve,
            section_role=str(section_role),
            section_index=int(section_index),
        )
    finally:
        owner.melody_gen.motif.motif_prob = original_motif_prob
        owner.melody_gen.phrase_repetition_prob = original_phrase_repeat
        owner.melody_gen.rest_prob = original_rest_prob

    bass_gate = float(curve.get("bass_enabled", 1.0)) >= 0.5
    _hp_bass = getattr(plan, "harmonic_plan", None)
    if _hp_bass is not None:
        try:
            _hp_bass.validate()
            _b_ch = list(_hp_bass.chords)
            _b_rt = list(_hp_bass.roots)
            _b_bars = int(_hp_bass.bars)
            _b_bpb = float(_hp_bass.beats_per_bar)
            _b_lane = list(_hp_bass.chosen_bass)
        except Exception:
            _b_ch, _b_rt, _b_bars, _b_bpb, _b_lane = (
                plan.chords,
                plan.roots,
                int(plan.bars),
                float(plan.beats_per_bar),
                plan.chosen_bass,
            )
    else:
        _b_ch, _b_rt, _b_bars, _b_bpb, _b_lane = (
            plan.chords,
            plan.roots,
            int(plan.bars),
            float(plan.beats_per_bar),
            plan.chosen_bass,
        )
    plan.bass_events = (
        owner.harmony_manager.generate_bass_events(
            _b_ch,
            _b_rt,
            _b_bars,
            _b_bpb,
            _b_lane,
            plan.emotion,
            section_role=section_role,
            timeline_targets=(plan.timeline_targets if isinstance(plan.timeline_targets, dict) else None),
        )
        if bass_gate
        else []
    )

    # ------------------------------------------------------------------
    # Density budgeting (cinematic): if other layers are busy, simplify chords.
    # This keeps the arrangement from spiking unpredictably.
    # ------------------------------------------------------------------
    try:
        mel_density = list((plan.timeline_targets or {}).get("melody_density", []) or [])
    except Exception:
        mel_density = []
    try:
        arp_active = bool(arp_gate and plan.arp_events)
    except Exception:
        arp_active = False
    # If melody lane is dense on average, reduce chord motion/rhythm a bit.
    try:
        if mel_density:
            avg_md = float(sum(float(x) for x in mel_density) / max(1, len(mel_density)))
        else:
            avg_md = 1.0
    except Exception:
        avg_md = 1.0
    try:
        _rlc_busy = str(section_role or "").strip().lower()
    except Exception:
        _rlc_busy = ""
    chorus_like = _rlc_busy in {"b", "chorus", "hook", "tag"}
    busy = (avg_md >= 1.08) or arp_active
    if busy:
        chord_motion_layer *= 0.88 if avg_md >= 1.08 else 0.92
        chord_rhythm_mult *= 0.90
        try:
            if chord_rhythm_targets:
                chord_rhythm_targets = [float(x) * (0.88 if arp_active else 0.93) for x in chord_rhythm_targets]
        except Exception:
            pass
        # Thin voicings slightly (drop extensions) by trimming chosen chord tones.
        # NOTE: do not collapse chorus-like sections; that defeats the “lift” and
        # makes extended harmony inaudible when other layers are active.
        if not chorus_like:
            try:
                trimmed = []
                for bi, notes in enumerate(list(plan.chosen_chord or [])):
                    nn = sorted({int(n) for n in (notes or []) if isinstance(n, int)})
                    if len(nn) <= 3:
                        row = nn
                    else:
                        # Keep low, mid, high (shell-ish); never fewer than three tones.
                        row = [nn[0], nn[len(nn) // 2], nn[-1]]
                    try:
                        sym = plan.chords[bi] if bi < len(plan.chords) else ""
                        rt = int(plan.roots[bi]) if bi < len(plan.roots) else 60
                        row = list(owner._ensure_min_chord_polyphony(str(sym), rt, row, minimum=3))
                    except Exception:
                        pass
                    trimmed.append(row)
                if trimmed and len(trimmed) == len(plan.chosen_chord):
                    plan.chosen_chord = trimmed
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Cadence + breath windows (timeline): make harmony rhythm “breathe” at
    # structural bars without any retries or heavy computation.
    # ------------------------------------------------------------------
    try:
        targets2 = getattr(plan, "timeline_targets", None) or {}
        breath_w = list(targets2.get("breath_window", []) or [])
        cad_w = list(targets2.get("cadence_window", []) or [])
        motif_w = list(targets2.get("motif_strength", []) or [])
    except Exception:
        breath_w = []
        cad_w = []
        motif_w = []
    if chord_rhythm_targets and (breath_w or cad_w):
        shaped_targets = []
        for i, x in enumerate(list(chord_rhythm_targets)):
            bw = float(breath_w[i]) if 0 <= i < len(breath_w) else 0.0
            cw = float(cad_w[i]) if 0 <= i < len(cad_w) else 0.0
            mw = float(motif_w[i]) if 0 <= i < len(motif_w) else 0.0
            # Breath bars: slightly calmer harmonic activity (space for handoffs).
            # Cadence bars: calmer activity to avoid washing out resolution.
            # Motif bars: slightly calmer too (hook clarity), but less than cadence.
            scale = (
                1.0
                - (0.22 * max(0.0, min(1.0, bw)))
                - (0.32 * max(0.0, min(1.0, cw)))
                - (0.18 * max(0.0, min(1.0, mw)))
            )
            shaped_targets.append(float(max(0.35, min(2.0, float(x) * float(scale)))))
        chord_rhythm_targets = shaped_targets
        # Also reduce global motion a touch when the cadence window is strong at the end.
        try:
            tail = 0.0
            if cad_w:
                tail = max(float(cad_w[-1]), float(cad_w[-2]) if len(cad_w) >= 2 else 0.0)
            tail = max(0.0, min(1.0, float(tail)))
            if tail > 1e-6:
                chord_motion_layer *= (1.0 - 0.10 * float(tail))
        except Exception:
            pass

    # Orchestration automation: role-based chord comping intensity.
    try:
        comp_mult = float(curve.get("chord_comping_strength_mult", 1.0) or 1.0)
    except Exception:
        comp_mult = 1.0
    comp_mult = max(0.0, min(1.35, float(comp_mult)))
    base_comp_strength = resolve_config("composition", "chord_comping_strength", 0.8, float)
    comp_strength_override = float(base_comp_strength) * float(comp_mult)
    try:
        plan.refresh_harmonic_plan_comping()
    except Exception:
        pass
    _hp_cmp = getattr(plan, "harmonic_plan_comping", None)
    if _hp_cmp is not None:
        try:
            _hp_cmp.validate()
            _ch_cmp = list(_hp_cmp.chords)
            _rt_cmp = list(_hp_cmp.roots)
            _bars_cmp = int(_hp_cmp.bars)
            _bpb_cmp = float(_hp_cmp.beats_per_bar)
            _voiced_cmp = [list(row) for row in _hp_cmp.chosen_chord] if _hp_cmp.chosen_chord else plan.chosen_chord
        except Exception:
            _ch_cmp, _rt_cmp, _bars_cmp, _bpb_cmp, _voiced_cmp = (
                plan.chords,
                plan.roots,
                int(plan.bars),
                float(plan.beats_per_bar),
                plan.chosen_chord,
            )
    else:
        _ch_cmp, _rt_cmp, _bars_cmp, _bpb_cmp, _voiced_cmp = (
            plan.chords,
            plan.roots,
            int(plan.bars),
            float(plan.beats_per_bar),
            plan.chosen_chord,
        )

    hr_action_override = None
    if resolve_config("composition", "arp_chord_harmonic_rhythm_shared_enabled", True, bool):
        hrx = list(getattr(plan, "harmonic_rhythm_action_by_bar", []) or [])
        if hrx and len(hrx) >= int(_bars_cmp):
            hr_action_override = list(hrx[: int(_bars_cmp)])
    plan.chord_events = owner.harmony_manager.generate_chord_events(
        _ch_cmp,
        _rt_cmp,
        _bars_cmp,
        _bpb_cmp,
        _voiced_cmp,
        plan.emotion,
        section_role=section_role,
        chord_rhythm_mult=chord_rhythm_mult,
        chord_motion_mult=chord_motion_layer,
        chord_rhythm_targets=chord_rhythm_targets,
        motif_strength_targets=list((plan.timeline_targets or {}).get("motif_strength", []) or []),
        tension_targets=list((plan.timeline_targets or {}).get("tension", []) or []),
        melody_activity_targets=list(melody_activity_by_bar or []),
        melody_onset_steps_by_bar=melody_onset_steps_by_bar_for_section(planner, plan, section_role=section_role),
        chord_comping_strength_override=comp_strength_override,
        hr_action_override=hr_action_override,
    )

    # ------------------------------------------------------------------
    # Harmonic motif memory: capture a chorus/tag cadence signature (last 2 chords)
    # so later choruses can restate it (progression hook).
    # ------------------------------------------------------------------
    try:
        rlc = str(section_role or "").strip().lower()
    except Exception:
        rlc = ""
    try:
        already = getattr(owner, "_harmonic_hook_signature", None)
    except Exception:
        already = None
    try:
        if already is None and rlc in {"b", "tag"} and isinstance(plan.chords, list) and len(plan.chords) >= 2:
            sig = {
                "pair": [str(plan.chords[-2]), str(plan.chords[-1])],
            }
            # Also store the harmonic rhythm actions if present (best-effort).
            try:
                actions = list(getattr(owner.harmony_manager, "_debug_hr_action_by_bar", []) or [])
                if actions:
                    sig["hr_actions_tail"] = [str(actions[-2]), str(actions[-1])] if len(actions) >= 2 else [str(actions[-1])]
            except Exception:
                pass
            setattr(owner, "_harmonic_hook_signature", sig)
    except Exception:
        pass
    drone_gate = float(curve.get("drone_enabled", 1.0)) >= 0.5
    if resolve_config("composition", "drone_always_on", False, bool):
        drone_gate = True
    plan.drone_event = owner._get_drone_event(plan.root_note, plan.emotion, plan.beats_per_bar) if drone_gate else None
    plan.arrangement_curve = dict(curve)
    # Interim strict-scale snap for the lead and counter-melody. Other
    # channels (bass / chords / arp) get their final snap inside
    # ``finalize_section_events``, which runs after the last arp repair
    # passes. We snap the lead twice (here + finalize) because some
    # downstream consumers read ``plan.melody_events`` directly via
    # ``register_section_memory`` before finalize merges the channels.
    if resolve_config("composition", "melody_strict_scale_enabled", True, bool):
        from composition.melody_arp_octave_resolve import snap_lead_events_to_strict_scale
        section_root_pc = int(getattr(owner, "_section_root_pc", 0)) % 12
        if plan.melody_events:
            plan.melody_events = snap_lead_events_to_strict_scale(
                list(plan.melody_events or []),
                emotion=_perceptual_scale_emotion(owner, plan.emotion),
                section_root_pc=int(section_root_pc),
                melody_channel=2,
            )
        if getattr(plan, "counter_events", None):
            plan.counter_events = snap_lead_events_to_strict_scale(
                list(plan.counter_events or []),
                emotion=_perceptual_scale_emotion(owner, plan.emotion),
                section_root_pc=int(section_root_pc),
                melody_channel=5,
            )
    return plan


def melody_onset_steps_by_bar_for_section(
    planner: Any,
    plan: SectionPlan,
    *,
    section_role: Optional[str] = None,
) -> Optional[List[List[int]]]:
    """
    Compute a deterministic per-bar melody onset plan (0.25-grid steps) derived from
    the same phrase rhythm templates used by Markov melody generation.

    This is used for chord/arp call-response (avoid masking the lead on its onsets).
    """
    owner = planner.owner
    try:
        bars = int(plan.bars)
        bpb = float(plan.beats_per_bar)
    except Exception:
        return None
    if bars <= 0 or bpb <= 1e-9:
        return None
    try:
        mel_em = owner.melody_manager.get_melody_emotion(plan.emotion)
    except Exception:
        mel_em = plan.emotion
    try:
        effective_temp = float(getattr(plan, "temperature", 0.7) or 0.7)
    except Exception:
        effective_temp = 0.7
    try:
        target_npb = float(getattr(plan, "target_notes_per_bar", 5.0) or 5.0)
    except Exception:
        target_npb = 5.0
    try:
        timeline_md = list((plan.timeline_targets or {}).get("melody_density", []) or [])
    except Exception:
        timeline_md = []
    if timeline_md:
        try:
            target_npb = float(target_npb) * (sum(float(v) for v in timeline_md) / max(1, len(timeline_md)))
        except Exception:
            pass
    try:
        phrase_contours, notes_per_phrase, _tm, _dm = owner.melody_runtime.prepare_melody_parameters(
            mel_em,
            int(bars),
            float(effective_temp),
            float(target_npb),
            first_phrase_note_scale=1.0,
            melody_total_notes_mult=1.0,
            melody_max_notes_per_phrase=None,
            section_role=section_role,
            timeline_density_by_bar=list((plan.timeline_targets or {}).get("melody_density", []) or []),
        )
    except Exception:
        return None
    try:
        onsets = owner.melody_runtime.plan_phrase_rhythm_onset_steps_by_bar(
            emotion=mel_em,
            phrase_contours=list(phrase_contours),
            notes_per_phrase=list(notes_per_phrase),
            bars=int(bars),
            beats_per_bar=float(bpb),
            grid=0.25,
            rng=getattr(owner, "rng", random),
        )
    except Exception:
        onsets = None
    if not onsets:
        return None
    # Ensure length matches bars.
    out = [list(row or []) for row in list(onsets)]
    while len(out) < int(bars):
        out.append([])
    if len(out) > int(bars):
        out = out[: int(bars)]
    return out
