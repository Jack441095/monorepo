"""Finalize section events: QA passes, humanization, assembly."""

from __future__ import annotations
from audiogen_core.config import resolve_config

import logging
from typing import Any, Dict, List

from audiogen_core.composition_runtime_flags import markov_style_strength, phrase_length_bars_clamped
from audiogen_core.mixer_config import CHANNEL_NAMES
from midi.midi_range_limiter import RANGE_LIMITER

from ..event import Event
from ..section_plan import SectionPlan
from .lead_texture_guards import _perceptual_scale_emotion
from .melody_event_guards import (
    _break_repeated_lead_notes_events,
    _cap_large_leaps_events,
    _repair_phrase_end_chord_tone_events,
    _smooth_target_emotion_leaps_events,
)
from .section_event_qa import (
    _apply_arrangement_collision_manager_typed,
    _apply_arrangement_velocity_typed,
    _apply_hook_strength_qa_typed,
    _apply_melody_action_qa_typed,
    _apply_phrase_vocal_grammar_typed,
    _apply_post_generation_qa_typed,
    _apply_section_contrast_qa_typed,
    _apply_section_transition_gestures_typed,
    _apply_slow_emotion_melody_interest_typed,
    _apply_stability_contract_typed,
    _apply_velocity_curves_typed,
)

logger = logging.getLogger(__name__)


def _apply_melody_phrase_boundary_breath_typed(events: List[Event], plan: SectionPlan) -> List[Event]:
    """Shorten lead notes that crowd phrase boundaries, preserving a small playable breath."""
    if not events:
        return events
    enabled = resolve_config("composition", "melody_phrase_breath_enabled", True, bool)
    breath = resolve_config("composition", "melody_phrase_breath_beats", 0.16, float)
    min_note = resolve_config("composition", "melody_phrase_breath_min_note_beats", 0.2, float)
    if not enabled:
        return events

    try:
        bpb = float(getattr(plan, "beats_per_bar", 4.0) or 4.0)
        bars = int(getattr(plan, "bars", 0) or 0)
    except Exception:
        bpb = 4.0
        bars = 0
    if bpb <= 0.0 or bars <= 1:
        return events

    breath = max(0.03, min(0.50, float(breath)))
    min_note = max(0.05, min(1.0, float(min_note)))

    try:
        phrase_len = phrase_length_bars_clamped(1, 16)
    except Exception:
        phrase_len = 4
    phrase_len = max(1, int(phrase_len))

    try:
        targets = dict(getattr(plan, "timeline_targets", None) or {})
        roles = list(targets.get("phrase_role_by_bar", []) or [])
        breaths = list(targets.get("breath_window", []) or [])
    except Exception:
        roles = []
        breaths = []

    boundary_beats: List[float] = []
    for bar in range(1, int(bars)):
        boundary = False
        if phrase_len > 0 and int(bar) % int(phrase_len) == 0:
            boundary = True
        try:
            if str(roles[bar]).strip().lower() == "opening":
                boundary = True
        except Exception:
            pass
        try:
            prev_bw = float(breaths[bar - 1]) if bar - 1 < len(breaths) else 0.0
            cur_bw = float(breaths[bar]) if bar < len(breaths) else 0.0
            if max(prev_bw, cur_bw) >= 0.55:
                boundary = True
        except Exception:
            pass
        if boundary:
            boundary_beats.append(float(bar) * float(bpb))

    if not boundary_beats:
        return events

    shaped: List[Event] = []
    for ev in events:
        try:
            if int(ev.channel) != 2:
                shaped.append(ev)
                continue
            st = float(ev.start_beats)
            dur = float(ev.duration_beats)
            end = st + dur
            new_dur = dur
            for boundary in boundary_beats:
                # Only phrase-end notes need trimming; pickups after the breath zone are left alone.
                if st < boundary and end > (boundary - breath):
                    cand = float(boundary - breath - st)
                    if cand >= min_note and cand < new_dur:
                        new_dur = cand
            if abs(new_dur - dur) <= 1e-6:
                shaped.append(ev)
                continue
            shaped.append(
                Event(
                    channel=ev.channel,
                    midi=ev.midi,
                    velocity=ev.velocity,
                    start_beats=ev.start_beats,
                    duration_beats=float(max(0.05, new_dur)),
                    notes=list(ev.notes),
                )
            )
        except Exception:
            shaped.append(ev)
    return shaped


def finalize_section_events(
    planner: Any,
    plan: SectionPlan,
    humanization_scale: float,
) -> SectionPlan:
    owner = planner.owner
    try:
        curve = dict(getattr(plan, "arrangement_curve", None) or {})
        cm_mult = float(curve.get("counter_melody_enabled_mult", 0.0) or 0.0)
        role_lc = str(getattr(plan, "section_role", "") or "").strip().lower()
        if (
            cm_mult >= 0.08
            and not list(getattr(plan, "counter_events", []) or [])
            and role_lc in {"a", "verse", "a_prime", "b", "chorus", "hook", "tag"}
        ):
            from data.emotion_scales import melody_scale_intervals_for_emotion

            scale = list(melody_scale_intervals_for_emotion(plan.emotion) or [0, 2, 4, 5, 7, 9, 11])
            bpb = float(getattr(plan, "beats_per_bar", 4.0) or 4.0)
            bars = max(1, int(getattr(plan, "bars", 1) or 1))
            bar = min(bars - 1, max(1, bars // 2))
            root = int(plan.roots[bar]) if 0 <= bar < len(plan.roots or []) else int(getattr(plan, "root_note", 60) or 60)
            degree = 2 if len(scale) > 2 else 0
            midi = int(root) + int(scale[degree]) - 12
            lead_pitch = None
            t = float(bar) * float(bpb) + (1.5 if bpb >= 4.0 else 0.5)
            for ev in list(getattr(plan, "melody_events", []) or []):
                if not (isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == 2):
                    continue
                st = float(ev[3])
                if st <= t < st + float(ev[4]):
                    lead_pitch = int(ev[1]) if isinstance(ev[1], int) else (int(ev[5][0]) if ev[5] else None)
                    break
            if lead_pitch is not None and midi >= int(lead_pitch) - 7:
                midi -= 12
            midi = int(RANGE_LIMITER.clamp_note(int(midi), 5))
            vel = int(max(1, min(127, round(52 * float(getattr(plan.emotion, "velocity_multiplier", 1.0) or 1.0)))))
            plan.counter_events = [(5, int(midi), int(vel), float(t), 0.5, [int(midi)])]
    except Exception:
        pass
    tuple_events = (
        plan.melody_events
        + plan.arp_events
        + (plan.counter_events or [])
        + plan.bass_events
        + plan.chord_events
    )
    if plan.drone_event is not None:
        tuple_events = tuple_events + [plan.drone_event]

    # Convert once into typed events for safer processing.
    typed_events: List[Event] = []
    for ev in tuple_events:
        try:
            typed_events.append(Event.from_tuple(ev))
        except Exception:
            # Legacy behavior: malformed events get dropped by validation.
            continue

    if plan.arrangement_curve:
        hctx = getattr(owner, "_emotion_transition_handoff_ctx", None)
        bar0_soft = None
        if hctx:
            raw_b0 = plan.arrangement_curve.get("boundary_bar0_vel_mult")
            if raw_b0 is not None:
                bar0_soft = float(raw_b0)
            else:
                bar0_soft = 0.88
        typed_events = _apply_arrangement_velocity_typed(
            typed_events,
            plan.arrangement_curve,
            handoff_bar0_velocity_mult=bar0_soft,
            beats_per_bar=float(plan.beats_per_bar),
        )

    # Instrument-aware velocity curves (performed-feel dynamics).
    vc_enabled = resolve_config("composition", "velocity_curves_enabled", True, bool)
    vc_strength = resolve_config("composition", "velocity_curves_strength", 0.85, float)
    vc_strength = max(0.0, min(1.0, float(vc_strength)))
    if vc_enabled and vc_strength > 1e-6:
        typed_events = _apply_velocity_curves_typed(
            typed_events,
            plan=plan,
            strength=float(vc_strength),
        )

    # Optional: tiny per-note velocity jitter (human feel).
    # Applied after curves but before humanization/validation so it stays bounded.
    mel_j = resolve_config("composition", "melody_velocity_jitter", 0, int)
    arp_j = resolve_config("composition", "arp_velocity_jitter", 0, int)
    mel_j = max(0, min(20, int(mel_j)))
    arp_j = max(0, min(20, int(arp_j)))
    if (mel_j > 0 or arp_j > 0) and typed_events:
        rng = getattr(owner, "rng", None)
        if rng is None:
            import random as _random

            rng = _random
        jittered: List[Event] = []
        for ev in typed_events:
            try:
                ch = int(ev.channel)
                j = mel_j if ch == 2 else (arp_j if ch == 3 else 0)
                if j <= 0:
                    jittered.append(ev)
                    continue
                dv = int(rng.randint(-j, j))
                nv = int(max(1, min(127, int(ev.velocity) + dv)))
                if nv == int(ev.velocity):
                    jittered.append(ev)
                    continue
                jittered.append(
                    Event(
                        channel=ev.channel,
                        midi=ev.midi,
                        velocity=nv,
                        start_beats=ev.start_beats,
                        duration_beats=ev.duration_beats,
                        notes=list(ev.notes),
                    )
                )
            except Exception:
                jittered.append(ev)
        typed_events = jittered

    # Audible role-to-role handoffs: pickup notes, anticipation hits, and release thinning.
    tg_enabled = resolve_config("composition", "transition_arrangement_gestures_enabled", True, bool)
    tg_strength = resolve_config("composition", "transition_arrangement_gestures_strength", 0.72, float)
    if tg_enabled and typed_events:
        try:
            typed_events = _apply_section_transition_gestures_typed(
                typed_events,
                plan,
                next_role=str(getattr(owner, "_next_section_role_hint", "") or ""),
                strength=float(tg_strength),
            )
        except Exception:
            pass

    vg_enabled = resolve_config("composition", "phrase_vocal_grammar_enabled", True, bool)
    vg_strength = resolve_config("composition", "phrase_vocal_grammar_strength", 0.68, float)
    if vg_enabled and typed_events:
        try:
            typed_events = _apply_phrase_vocal_grammar_typed(
                typed_events,
                plan,
                strength=float(vg_strength),
            )
        except Exception:
            pass

    qa_enabled = resolve_config("composition", "post_generation_qa_enabled", True, bool)
    qa_strength = resolve_config("composition", "post_generation_qa_strength", 0.58, float)
    if qa_enabled and typed_events:
        try:
            typed_events = _apply_post_generation_qa_typed(
                typed_events,
                plan,
                strength=float(qa_strength),
            )
        except Exception:
            pass

    slow_interest_enabled = resolve_config("composition", "slow_emotion_melody_interest_enabled", True, bool)
    slow_interest_strength = resolve_config("composition", "slow_emotion_melody_interest_strength", 0.72, float)
    if slow_interest_enabled and typed_events:
        try:
            typed_events = _apply_slow_emotion_melody_interest_typed(
                typed_events,
                plan,
                strength=float(slow_interest_strength),
            )
        except Exception:
            pass

    action_enabled = resolve_config("composition", "melody_action_qa_enabled", True, bool)
    action_strength = resolve_config("composition", "melody_action_qa_strength", 0.78, float)
    if action_enabled and typed_events:
        try:
            typed_events = _apply_melody_action_qa_typed(
                typed_events,
                plan,
                strength=float(action_strength),
            )
        except Exception:
            pass

    hook_enabled = resolve_config("composition", "hook_strength_qa_enabled", True, bool)
    hook_strength = resolve_config("composition", "hook_strength_qa_strength", 0.62, float)
    if hook_enabled and typed_events:
        try:
            typed_events = _apply_hook_strength_qa_typed(
                typed_events,
                plan,
                strength=float(hook_strength),
            )
        except Exception:
            pass

    contrast_enabled = resolve_config("composition", "section_contrast_qa_enabled", True, bool)
    contrast_strength = resolve_config("composition", "section_contrast_qa_strength", 0.55, float)
    if contrast_enabled and typed_events:
        try:
            typed_events = _apply_section_contrast_qa_typed(
                typed_events,
                plan,
                strength=float(contrast_strength),
            )
        except Exception:
            pass

    collision_enabled = resolve_config("composition", "arrangement_collision_manager_enabled", True, bool)
    collision_strength = resolve_config("composition", "arrangement_collision_manager_strength", 0.62, float)
    if collision_enabled and typed_events:
        try:
            typed_events = _apply_arrangement_collision_manager_typed(
                typed_events,
                plan,
                strength=float(collision_strength),
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 16-bar structural handoff shaping (A -> B) and cadence breathing.
    # Deterministic + RT-cheap: only simple per-event adjustments.
    # ------------------------------------------------------------------
    try:
        bpb = float(getattr(plan, "beats_per_bar", 4.0) or 4.0)
        bars = int(getattr(plan, "bars", 0) or 0)
        targets = getattr(plan, "timeline_targets", None) or {}
        breath = list(targets.get("breath_window", []) or [])
        cad_win = list(targets.get("cadence_window", []) or [])
    except Exception:
        bpb = 4.0
        bars = 0
        breath = []
        cad_win = []

    if typed_events and bars == 16 and bpb > 0:
        def _bar_idx(start_beats: float) -> int:
            return int(float(start_beats) // float(bpb))

        # 0) Realtime special events: bridge/tag boundary gestures.
        # Keep it deterministic + cheap (single pass filter/scale).
        try:
            hctx = getattr(owner, "_emotion_transition_handoff_ctx", None) or {}
        except Exception:
            hctx = {}
        try:
            rt_special = str(hctx.get("rt_special_event", "") or "").strip().lower()
        except Exception:
            rt_special = ""
        try:
            recap_intent = bool(hctx.get("rt_recap_intent", False))
        except Exception:
            recap_intent = False
        if rt_special in {"contrast_bridge", "tag_recap"} or recap_intent:
            shaped0: List[Event] = []
            for ev in typed_events:
                try:
                    ch = int(ev.channel)
                    st = float(ev.start_beats)
                    dur = float(ev.duration_beats)
                    bi = _bar_idx(st)
                    bar_start = float(bi) * float(bpb)
                    pos = float(st - bar_start)
                    is_bar_end_anchor = ch == 3 and pos >= max(0.0, float(bpb) - 1.0)

                    # Bridge contrast: create a small "air gap" on bar 0 by removing
                    # busy chord/arp/counter stabs that clutter the downbeat.
                    if rt_special == "contrast_bridge" and bi == 0 and ch in {1, 3, 5}:
                        keep = is_bar_end_anchor or (abs(pos - 0.0) < 0.03) or (abs(pos - 2.0) < 0.03) or (dur >= 0.95)
                        if not keep:
                            continue
                        # Also soften the first bar slightly so the following section can lift.
                        if abs(pos - 0.0) < 0.06:
                            nv = int(max(1, min(127, round(float(ev.velocity) * 0.90))))
                            ev = Event(
                                channel=ev.channel,
                                midi=ev.midi,
                                velocity=nv,
                                start_beats=ev.start_beats,
                                duration_beats=ev.duration_beats,
                                notes=list(ev.notes),
                            )

                    # Tag/recap: simplify the final bar comping so the hook reads cleanly.
                    if (rt_special == "tag_recap" or recap_intent) and bi == (bars - 1) and ch in {1, 3, 5}:
                        keep = is_bar_end_anchor or (abs(pos - 0.0) < 0.03) or (abs(pos - 2.0) < 0.03) or (dur >= float(bpb) * 0.8)
                        if not keep:
                            continue
                        # Slight accent on the downbeat.
                        if abs(pos - 0.0) < 0.06:
                            nv = int(max(1, min(127, round(float(ev.velocity) * 1.06))))
                            ev = Event(
                                channel=ev.channel,
                                midi=ev.midi,
                                velocity=nv,
                                start_beats=ev.start_beats,
                                duration_beats=ev.duration_beats,
                                notes=list(ev.notes),
                            )

                    shaped0.append(ev)
                except Exception:
                    shaped0.append(ev)
            typed_events = shaped0

        # 0b) Texture script actions (drops/register spotlight/builds).
        # Computed earlier in build_section and attached to the plan.
        try:
            tex = getattr(plan, "texture_by_bar", None)
            tex = list(tex) if isinstance(tex, list) else []
        except Exception:
            tex = []
        if tex:
            def _is_strong(pos: float) -> bool:
                return abs(float(pos) - 0.0) < 0.03 or abs(float(pos) - 2.0) < 0.03

            # Pass 1: apply drops + lead spotlight + register lift.
            shaped_tex: List[Event] = []
            for ev in typed_events:
                try:
                    ch = int(ev.channel)
                    st = float(ev.start_beats)
                    dur = float(ev.duration_beats)
                    bi = _bar_idx(st)
                    if bi < 0 or bi >= bars:
                        shaped_tex.append(ev)
                        continue
                    info = tex[bi] if bi < len(tex) and isinstance(tex[bi], dict) else {}
                    drop = float(info.get("drop_level", 0.0) or 0.0)
                    focus = float(info.get("lead_focus", 0.0) or 0.0)
                    lift = int(info.get("register_lift_semitones", 0) or 0)
                    layer_presence = info.get("layer_presence", {}) if isinstance(info.get("layer_presence", {}), dict) else {}
                    space = float(info.get("fx_space_boost", 0.0) or 0.0)
                    width = float(info.get("fx_width_boost", 0.0) or 0.0)
                    grit = float(info.get("fx_grit_boost", 0.0) or 0.0)
                    has_gesture = (drop > 1e-6) or (lift != 0) or (space > 1e-6) or (width > 1e-6) or (grit > 1e-6)
                    bar_start = float(bi) * float(bpb)
                    pos = float(st - bar_start)
                    is_bar_end_anchor = ch == 3 and pos >= max(0.0, float(bpb) - 1.0)

                    # Drops: remove clutter first (arp/counter), then chord stabs.
                    if drop > 1e-6 and ch in {3, 5}:
                        if (not _is_strong(pos)) and (not is_bar_end_anchor) and (dur < 0.95):
                            # Drop probability scales with drop level.
                            keep = float(drop) < 0.55
                            if not keep:
                                continue
                    if drop > 1e-6 and ch == 1:
                        if (not _is_strong(pos)) and (dur < float(bpb) * 0.8):
                            keep = float(drop) < 0.65
                            if not keep:
                                continue

                    # Slot orchestration: per-role layer presence profile.
                    # Deterministic thinning (no randomness) to make section roles legible.
                    try:
                        layer_key = {
                            0: "bass",
                            1: "chords",
                            2: "melody",
                            3: "arp",
                            5: "counter",
                        }.get(int(ch), "")
                        lp = float(layer_presence.get(layer_key, 1.0) or 1.0) if layer_key else 1.0
                    except Exception:
                        layer_key, lp = "", 1.0
                    lp = float(max(0.0, min(1.0, lp)))
                    if layer_key and lp < 0.999:
                        q16 = int(round(float(pos) * 4.0))
                        q8 = int(round(float(pos) * 2.0))
                        strong = _is_strong(pos)
                        keep_lp = True
                        if lp <= 0.05:
                            keep_lp = False
                        elif lp < 0.35:
                            keep_lp = bool(strong or dur >= 0.95)
                        elif lp < 0.60:
                            keep_lp = bool(strong or dur >= 0.75 or (q16 % 2 == 0))
                        elif lp < 0.80:
                            keep_lp = bool(strong or dur >= 0.45 or (q8 % 2 == 0))
                        if not keep_lp:
                            continue
                        # Slightly soften low-presence companion layers to reduce masking.
                        if layer_key in {"chords", "arp", "counter"} and lp < 0.95:
                            nv = int(max(1, min(127, round(float(ev.velocity) * (0.72 + 0.28 * lp)))))
                            ev = Event(
                                channel=ev.channel,
                                midi=ev.midi,
                                velocity=nv,
                                start_beats=ev.start_beats,
                                duration_beats=ev.duration_beats,
                                notes=list(ev.notes),
                            )

                    # Lead spotlight: on high focus bars, thin competing layers and boost lead.
                    if has_gesture and focus >= 0.85:
                        if ch in {1, 3, 5} and (not _is_strong(pos)) and dur < 0.95:
                            continue
                        if ch == 2 and _is_strong(pos):
                            nv = int(max(1, min(127, round(float(ev.velocity) * 1.06))))
                            ev = Event(
                                channel=ev.channel,
                                midi=ev.midi,
                                velocity=nv,
                                start_beats=ev.start_beats,
                                duration_beats=ev.duration_beats,
                                notes=list(ev.notes),
                            )

                    # Register lift: chorus/tag lift for melody/chords/arp (not bass).
                    if lift and ch in {1, 2, 3, 5}:
                        try:
                            midi2 = RANGE_LIMITER.clamp_note(int(ev.midi) + int(lift), int(ch))
                        except Exception:
                            midi2 = int(ev.midi)
                        notes2 = list(ev.notes)
                        if notes2:
                            nn = []
                            for n in notes2:
                                try:
                                    nn.append(int(RANGE_LIMITER.clamp_note(int(n) + int(lift), int(ch))))
                                except Exception:
                                    nn.append(int(n))
                            notes2 = nn
                        ev = Event(
                            channel=ev.channel,
                            midi=int(midi2),
                            velocity=ev.velocity,
                            start_beats=ev.start_beats,
                            duration_beats=ev.duration_beats,
                            notes=notes2,
                        )

                    shaped_tex.append(ev)
                except Exception:
                    shaped_tex.append(ev)
            typed_events = shaped_tex

            # Pass 2: small builds (guarded): duplicate some chord hits on beat 2
            # in high-tension, low-drop bars (pre-chorus/chorus lift).
            try:
                added: List[Event] = []
                # Index existing chord onsets per (bar,pos rounded).
                chord_pos = {}
                for ev in typed_events:
                    if int(ev.channel) != 1:
                        continue
                    bi = _bar_idx(float(ev.start_beats))
                    if bi < 0 or bi >= bars:
                        continue
                    bar_start = float(bi) * float(bpb)
                    pos = float(ev.start_beats - bar_start)
                    key = (int(bi), int(round(pos * 100)))
                    chord_pos[key] = True
                for bi in range(bars):
                    info = tex[bi] if bi < len(tex) and isinstance(tex[bi], dict) else {}
                    drop = float(info.get("drop_level", 0.0) or 0.0)
                    space = float(info.get("fx_space_boost", 0.0) or 0.0)
                    if drop >= 0.35:
                        continue
                    # Treat high-space (cadence/tension) as a proxy for "build".
                    if space < 0.45:
                        continue
                    # Only if there's a chord at beat 0 but not at beat 2.
                    k0 = (int(bi), int(round(0.0 * 100)))
                    k2 = (int(bi), int(round(2.0 * 100)))
                    if not chord_pos.get(k0):
                        continue
                    if chord_pos.get(k2):
                        continue
                    # Duplicate: reuse the first chord-at-0 event we find.
                    src = next((e for e in typed_events if int(e.channel) == 1 and _bar_idx(float(e.start_beats)) == bi and abs(float(e.start_beats) - float(bi) * float(bpb)) < 0.03), None)
                    if src is None:
                        continue
                    added.append(
                        Event(
                            channel=src.channel,
                            midi=src.midi,
                            velocity=int(max(1, min(127, round(float(src.velocity) * 0.92)))),
                            start_beats=float(bi) * float(bpb) + 2.0,
                            duration_beats=min(float(src.duration_beats), 1.25),
                            notes=list(src.notes),
                        )
                    )
                if added:
                    typed_events = list(typed_events) + added
            except Exception:
                pass

        # 1) "Breath" at the A->B boundary (bar index 8): reduce arp density and
        # prevent long sustains from bleeding across the boundary.
        boundary_bar = 8
        if boundary_bar < len(breath) and float(breath[boundary_bar]) >= 0.5:
            boundary = float(boundary_bar) * float(bpb)
            prev_end = boundary - 0.05  # small gap in beats
            thinned: List[Event] = []
            for ev in typed_events:
                try:
                    ch = int(ev.channel)
                    st = float(ev.start_beats)
                    dur = float(ev.duration_beats)
                    bi = _bar_idx(st)

                    # Clamp events in the previous bar so they end before the boundary.
                    if bi == boundary_bar - 1 and (st + dur) > boundary and dur > 0.11:
                        new_dur = max(0.10, float(prev_end - st))
                        if new_dur < dur - 1e-6:
                            ev = Event(
                                channel=ev.channel,
                                midi=ev.midi,
                                velocity=ev.velocity,
                                start_beats=ev.start_beats,
                                duration_beats=float(new_dur),
                                notes=list(ev.notes),
                            )

                    # Thin arp events right on the boundary bar to create a handoff.
                    if ch == 3 and bi == boundary_bar:
                        pos = float(st - float(boundary))
                        # Keep only strong beats (0 and 2) plus any long notes.
                        keep = (abs(pos - 0.0) < 0.03) or (abs(pos - 2.0) < 0.03) or (dur >= 0.9)
                        if not keep:
                            continue

                    # Also thin chord comping on the boundary bar so the melody downbeat reads clearly.
                    if ch == 1 and bi == boundary_bar:
                        pos = float(st - float(boundary))
                        # Keep only a strong-beat shell (0, 2) or long pads.
                        keep = (abs(pos - 0.0) < 0.03) or (abs(pos - 2.0) < 0.03) or (dur >= float(bpb) * 0.8)
                        if not keep:
                            continue

                    thinned.append(ev)
                except Exception:
                    thinned.append(ev)
            typed_events = thinned

            # Encourage a clear downbeat re-entry for the melody in bar 9 (index 8):
            # if the first melody onset is close to the downbeat, snap it to beat 1.
            bar_start = boundary
            first_i = None
            first_st = None
            for i, ev in enumerate(typed_events):
                try:
                    if int(ev.channel) != 2:
                        continue
                    st = float(ev.start_beats)
                    if _bar_idx(st) != boundary_bar:
                        continue
                    if first_st is None or st < first_st:
                        first_st = st
                        first_i = i
                except Exception:
                    continue
            if first_i is not None and first_st is not None:
                if (first_st - bar_start) >= 0.20 and (first_st - bar_start) <= 0.75:
                    ev = typed_events[first_i]
                    typed_events[first_i] = Event(
                        channel=ev.channel,
                        midi=ev.midi,
                        velocity=int(min(127, round(float(ev.velocity) * 1.06))),
                        start_beats=float(bar_start),
                        duration_beats=ev.duration_beats,
                        notes=list(ev.notes),
                    )

        # 2) Final cadence breathing: thin arp a bit on strong cadence bars.
        if cad_win:
            thinned2: List[Event] = []
            for ev in typed_events:
                try:
                    ch = int(ev.channel)
                    st = float(ev.start_beats)
                    bi = _bar_idx(st)
                    w = float(cad_win[bi]) if 0 <= bi < len(cad_win) else 0.0
                    if ch == 3 and w >= 0.95:
                        # On final cadence bars, keep only downbeats to open space.
                        bar_start = float(bi) * float(bpb)
                        pos = float(st - bar_start)
                        if not (abs(pos - 0.0) < 0.03 or abs(pos - 2.0) < 0.03):
                            continue
                    if ch == 1 and w >= 0.95:
                        # On cadence bars, simplify chord comping (avoid busy mid-beat stabs).
                        bar_start = float(bi) * float(bpb)
                        pos = float(st - bar_start)
                        if not (abs(pos - 0.0) < 0.03 or abs(pos - 2.0) < 0.03 or float(ev.duration_beats) >= float(bpb) * 0.8):
                            continue
                    thinned2.append(ev)
                except Exception:
                    thinned2.append(ev)
            typed_events = thinned2

    # ------------------------------------------------------------------
    # Texture / rhythmic interplay (DAW-like clarity)
    # If arp (ch=3) is very dense in a bar, keep melody from stacking on downbeats.
    # If melody is very dense, thin arp/counter in that bar.
    # Deterministic: uses only timing + per-bar counts.
    # ------------------------------------------------------------------
    try:
        bpb = float(getattr(plan, "beats_per_bar", 4.0) or 4.0)
        bars = int(getattr(plan, "bars", 0) or 0)
        targets = getattr(plan, "timeline_targets", None) or {}
        mel_t = list(targets.get("melody_density", []) or [])
    except Exception:
        bpb = 4.0
        bars = 0
        mel_t = []

    if typed_events and bars > 0 and bpb > 0:
        dense_arp_nudge = False
        dense_arp_nudge = resolve_config("composition", "melody_dense_arp_downbeat_nudge_enabled", False, bool)
        # Count onsets per bar for melodic layers.
        arp_counts = [0 for _ in range(bars)]
        mel_counts = [0 for _ in range(bars)]
        ctr_counts = [0 for _ in range(bars)]
        for ev in typed_events:
            try:
                ch = int(ev.channel)
                bar = int(float(ev.start_beats) // float(bpb))
                if bar < 0 or bar >= bars:
                    continue
                if ch == 3:
                    arp_counts[bar] += 1
                elif ch == 2:
                    mel_counts[bar] += 1
                elif ch == 5:
                    ctr_counts[bar] += 1
            except Exception:
                continue

        def _is_downbeat(t: float) -> bool:
            pos = float(t) % float(bpb)
            return abs(pos - 0.0) < 1e-6 or abs(pos - 2.0) < 1e-6

        shaped: List[Event] = []
        for ev in typed_events:
            try:
                ch = int(ev.channel)
                st = float(ev.start_beats)
                bar = int(st // float(bpb))
                if bar < 0 or bar >= bars:
                    shaped.append(ev)
                    continue
                mel_target = float(mel_t[bar]) if bar < len(mel_t) else 1.0
                arp_dense = arp_counts[bar] >= 10
                mel_dense = mel_counts[bar] >= int(7 * max(0.7, min(1.3, mel_target)))

                # If arp is dense, avoid stacking melody on downbeats: nudge to the "and".
                if dense_arp_nudge and ch == 2 and arp_dense and _is_downbeat(st):
                    st2 = st + 0.5
                    if st2 < float(bars) * float(bpb) - 1e-6:
                        shaped.append(
                            Event(
                                channel=ev.channel,
                                midi=ev.midi,
                                velocity=ev.velocity,
                                start_beats=float(st2),
                                duration_beats=ev.duration_beats,
                                notes=list(ev.notes),
                            )
                        )
                        continue

                # If melody is dense, thin arp/counter slightly in that bar.
                if mel_dense and ch in {3, 5}:
                    # Keep only strong beats in dense bars.
                    pos = float(st) % float(bpb)
                    keep = abs(pos - 0.0) < 0.03 or abs(pos - 2.0) < 0.03
                    if not keep:
                        continue

                shaped.append(ev)
            except Exception:
                shaped.append(ev)
        typed_events = shaped

    # Lead articulation shaping by phrase role (gate + velocity).
    g_open = resolve_config("composition", "melody_gate_mult_opening", 0.95, float)
    g_ans = resolve_config("composition", "melody_gate_mult_answer", 1.0, float)
    g_cad = resolve_config("composition", "melody_gate_mult_cadence", 1.08, float)
    v_open = resolve_config("composition", "melody_vel_mult_opening", 0.96, float)
    v_ans = resolve_config("composition", "melody_vel_mult_answer", 1.0, float)
    v_cad = resolve_config("composition", "melody_vel_mult_cadence", 1.06, float)
    if typed_events:
        try:
            bpb2 = float(getattr(plan, "beats_per_bar", 4.0) or 4.0)
            bars2 = int(getattr(plan, "bars", 0) or 0)
        except Exception:
            bpb2 = 4.0
            bars2 = 0

        def _phrase_role_for_bar(bar_idx: int) -> str:
            phrase_len = phrase_length_bars_clamped(1, 16)
            try:
                return owner.chord_utils.phrase_role(int(bar_idx), int(bars2), phrase_length=int(phrase_len))
            except Exception:
                return ""

        shaped: List[Event] = []
        for ev in typed_events:
            try:
                if int(ev.channel) != 2:
                    shaped.append(ev)
                    continue
                bar = int(float(ev.start_beats) // float(bpb2)) if bpb2 > 0 else 0
                pr = str(_phrase_role_for_bar(bar) or "")
                g = g_ans
                v = v_ans
                if pr == "opening":
                    g, v = g_open, v_open
                elif pr == "cadence":
                    g, v = g_cad, v_cad
                elif pr == "answer":
                    g, v = g_ans, v_ans

                bar_start = float(bar) * float(bpb2)
                bar_end = bar_start + float(bpb2)
                st = float(ev.start_beats)
                dur = float(ev.duration_beats)
                new_dur = max(0.10, dur * max(0.7, min(1.2, float(g))))
                new_dur = min(new_dur, max(0.10, (bar_end - st) - 1e-3))
                new_vel = int(max(1, min(127, round(float(ev.velocity) * max(0.8, min(1.2, float(v)))))))
                shaped.append(
                    Event(
                        channel=ev.channel,
                        midi=ev.midi,
                        velocity=new_vel,
                        start_beats=ev.start_beats,
                        duration_beats=float(new_dur),
                        notes=list(ev.notes),
                    )
                )
            except Exception:
                shaped.append(ev)
        typed_events = shaped

    typed_events = _apply_melody_phrase_boundary_breath_typed(typed_events, plan)

    if owner.humanize and hasattr(plan.emotion, "humanization") and plan.emotion.humanization:
        typed_events = owner.event_pipeline.humanize_event_objects(
            typed_events, plan.emotion.humanization, owner.humanization_probability
        )

    # Cinematic micro-timing (chords + arp): small deterministic offsets to avoid robotic grid feel.
    mt_enabled = resolve_config("composition", "micro_timing_enabled", True, bool)
    mt_ch_ms = resolve_config("composition", "micro_timing_chords_max_ms", 18.0, float)
    mt_arp_ms = resolve_config("composition", "micro_timing_arp_max_ms", 14.0, float)
    mt_mel_enabled = resolve_config("composition", "melody_microtiming_enabled", True, bool)
    mt_mel_ms = resolve_config("composition", "melody_microtiming_max_ms", 10.0, float)
    mel_swing_enabled = resolve_config("composition", "melody_swing_enabled", False, bool)
    mel_swing_amt = resolve_config("composition", "melody_swing_amount", 0.0, float)
    bpm = resolve_config("composition", "emotion", 70.0, float)
    bpm = max(20.0, min(320.0, float(bpm)))
    # If hard 16th quantization is enabled, disable microtiming/swing layers.
    if resolve_config("composition", "quantize_16th_enabled", False, bool):
        mt_enabled = False
        mt_mel_enabled = False
        mel_swing_enabled = False
    if mt_enabled and typed_events:
        bpb = float(getattr(plan, "beats_per_bar", 4.0) or 4.0)
        bars = int(getattr(plan, "bars", 0) or 0)
        # Convert ms -> beats.
        beat_s = 60.0 / float(bpm)
        ch_max = max(0.0, float(mt_ch_ms)) / 1000.0 / beat_s
        arp_max = max(0.0, float(mt_arp_ms)) / 1000.0 / beat_s
        mel_max = max(0.0, float(mt_mel_ms)) / 1000.0 / beat_s if mt_mel_enabled else 0.0
        # Clamp to safe fractions of a beat (never smear rhythmic intent).
        ch_max = max(0.0, min(0.08, float(ch_max)))
        arp_max = max(0.0, min(0.08, float(arp_max)))
        mel_max = max(0.0, min(0.08, float(mel_max)))

        def _phrase_role(bar_idx: int) -> str:
            try:
                phrase_len = phrase_length_bars_clamped(1, 16)
                return owner.chord_utils.phrase_role(int(bar_idx), int(bars), phrase_length=int(phrase_len))
            except Exception:
                return ""

        def _role_scale(role: str) -> float:
            r = str(role or "")
            if r == "opening":
                return 0.85
            if r == "continuation":
                return 1.0
            if r == "answer":
                return 0.95
            if r == "cadence":
                return 0.35
            return 0.75

        shifted: List[Event] = []
        for ev in typed_events:
            try:
                ch = int(ev.channel)
                if ch not in {1, 2, 3}:
                    shifted.append(ev)
                    continue
                max_off = ch_max if ch == 1 else (arp_max if ch == 3 else mel_max)
                if max_off <= 1e-9:
                    shifted.append(ev)
                    continue
                bar = int(float(ev.start_beats) // bpb) if bpb > 1e-9 else 0
                if bar < 0 or (bars and bar >= bars):
                    shifted.append(ev)
                    continue
                role = _phrase_role(bar)
                sc = _role_scale(role)
                # Deterministic RNG: seed + (microtiming, ch, bar, onset within bar)
                try:
                    drng = owner.deterministic_rng("microtiming", int(ch), int(bar), round(float(ev.start_beats), 3))
                except Exception:
                    drng = getattr(owner, "rng", None) or __import__("random")
                # Cinematic: opening slightly late; continuation symmetric; cadence tight.
                if str(role) == "opening":
                    off = abs(float(drng.uniform(-1.0, 1.0))) * float(max_off) * float(sc)
                else:
                    off = float(drng.uniform(-1.0, 1.0)) * float(max_off) * float(sc)

                # Melody swing (channel 2 only): delay every other 8th-grid step slightly.
                if ch == 2 and mel_swing_enabled and float(mel_swing_amt) > 1e-6:
                    amt = max(0.0, min(0.25, float(mel_swing_amt)))
                    # Use an 8th-note feel if the onset is close to an 8th grid.
                    pos = float(ev.start_beats) - (float(bar) * float(bpb))
                    step = int(round(pos / 0.5)) if 0.5 > 1e-9 else 0
                    if step % 2 == 1:
                        off += float(0.5) * float(amt)
                # Clamp within bar so events never cross boundaries.
                bar_start = float(bar) * float(bpb)
                bar_end = bar_start + float(bpb)
                start = float(ev.start_beats)
                dur = float(ev.duration_beats)
                # Keep a small guard so end doesn't exceed bar end too much.
                guard = 1e-3
                new_start = max(bar_start + guard, min(bar_end - max(guard, min(0.25, dur)), start + off))
                if abs(new_start - start) <= 1e-6:
                    shifted.append(ev)
                    continue
                shifted.append(
                    Event(
                        channel=ev.channel,
                        midi=ev.midi,
                        velocity=ev.velocity,
                        start_beats=float(new_start),
                        duration_beats=ev.duration_beats,
                        notes=list(ev.notes),
                    )
                )
            except Exception:
                shifted.append(ev)
        typed_events = shifted

    # Dynamics safety: prevent surprising bar-to-bar velocity jumps (per channel).
    lim_enabled = resolve_config("composition", "bar_velocity_jump_limit_enabled", True, bool)
    lim_ratio = resolve_config("composition", "bar_velocity_jump_limit_ratio", 1.15, float)
    lim_ratio = max(1.01, min(1.75, float(lim_ratio)))
    # Tighten the limiter automatically for high-energy emotions (dense + fast),
    # which otherwise can read as “pumping” or “slammy” dynamics (e.g. surprise).
    try:
        from data.audit import normalize_emotion_scalars

        emo = getattr(plan, "emotion", None)
        if emo is not None:
            t_m, _v_m, d_m = normalize_emotion_scalars(emo)
            # Surprise-like: fast + dense -> stricter jump limit.
            if float(t_m) >= 1.50 and float(d_m) >= 0.75:
                lim_ratio = min(float(lim_ratio), 1.10)
    except Exception:
        pass
    if lim_enabled and typed_events:
        bpb = float(getattr(plan, "beats_per_bar", 4.0) or 4.0)
        bars = int(getattr(plan, "bars", 0) or 0)
        # Collect per-bar mean velocity per channel.
        sums = {}
        counts = {}
        for ev in typed_events:
            try:
                ch = int(ev.channel)
                if ch == 4:
                    continue
                bar = int(float(ev.start_beats) // bpb) if bpb > 0 else 0
                if bar < 0 or (bars and bar >= bars):
                    continue
                key = (ch, bar)
                sums[key] = float(sums.get(key, 0.0)) + float(ev.velocity)
                counts[key] = int(counts.get(key, 0)) + 1
            except Exception:
                continue
        means = {}
        for (ch, bar), s in sums.items():
            c = max(1, int(counts.get((ch, bar), 1)))
            means[(ch, bar)] = float(s) / float(c)

        # Compute per-(ch,bar) scaling factors to keep changes within lim_ratio.
        scales = {}
        for ch in {int(k[0]) for k in means.keys()}:
            prev = None
            for bar in range(max(0, bars)):
                cur = means.get((ch, bar))
                if cur is None or cur <= 1e-6:
                    continue
                if prev is None or prev <= 1e-6:
                    prev = float(cur)
                    continue
                r = float(cur) / float(prev)
                if r > lim_ratio:
                    scales[(ch, bar)] = float((prev * lim_ratio) / cur)
                    prev = float(prev * lim_ratio)
                elif r < (1.0 / lim_ratio):
                    scales[(ch, bar)] = float((prev / lim_ratio) / cur)
                    prev = float(prev / lim_ratio)
                else:
                    prev = float(cur)

        if scales:
            limited: List[Event] = []
            for ev in typed_events:
                try:
                    ch = int(ev.channel)
                    if ch == 4:
                        limited.append(ev)
                        continue
                    bar = int(float(ev.start_beats) // bpb) if bpb > 0 else 0
                    sc = float(scales.get((ch, bar), 1.0))
                    if abs(sc - 1.0) <= 1e-6:
                        limited.append(ev)
                        continue
                    nv = int(max(1, min(127, round(float(ev.velocity) * sc))))
                    if nv == int(ev.velocity):
                        limited.append(ev)
                        continue
                    limited.append(
                        Event(
                            channel=ev.channel,
                            midi=ev.midi,
                            velocity=nv,
                            start_beats=ev.start_beats,
                            duration_beats=ev.duration_beats,
                            notes=list(ev.notes),
                        )
                    )
                except Exception:
                    limited.append(ev)
            typed_events = limited

    # Stability contract (fast post-check invariants).
    try:
        typed_events = _apply_stability_contract_typed(typed_events, plan=plan)
    except Exception:
        pass

    # Final arp-bed completion: after all texture/transition thinning, keep
    # active arp bars from ending early. This mirrors the reference MIDI
    # behavior where the arp usually completes the bar even when softened.
    try:
        bpb = float(getattr(plan, "beats_per_bar", 4.0) or 4.0)
        bars = int(getattr(plan, "bars", 0) or 0)
        curve_arp = dict(getattr(plan, "arrangement_curve", None) or {})
        arp_allowed = float(curve_arp.get("arp_enabled", 0.0) or 0.0) >= 0.5
        if typed_events and bars > 0 and bpb > 1e-9 and arp_allowed:
            arp_by_bar: Dict[int, List[Event]] = {i: [] for i in range(bars)}
            for ev in list(typed_events or []):
                try:
                    if int(ev.channel) != 3:
                        continue
                    bi = int(float(ev.start_beats) // bpb)
                    if 0 <= bi < bars:
                        arp_by_bar[int(bi)].append(ev)
                except Exception:
                    continue
            additions: List[Event] = []
            for bi, evs in arp_by_bar.items():
                if not evs:
                    continue
                bar_end = float(bi + 1) * bpb
                has_end = False
                for ev in evs:
                    try:
                        if float(ev.start_beats) >= bar_end - 1.0 or float(ev.start_beats) + float(ev.duration_beats) >= bar_end - 0.10:
                            has_end = True
                            break
                    except Exception:
                        continue
                if has_end:
                    continue
                pcs = []
                try:
                    if getattr(plan, "chosen_chord", None) and int(bi) < len(plan.chosen_chord):
                        pcs = [int(n) % 12 for n in list(plan.chosen_chord[int(bi)] or []) if isinstance(n, (int, float)) and int(n) > 0]
                except Exception:
                    pcs = []
                if not pcs:
                    continue
                try:
                    median_pitch = sorted(int(e.midi) for e in evs if isinstance(e.midi, (int, float)))[len(evs) // 2]
                except Exception:
                    median_pitch = 67
                present = {int(e.midi) % 12 for e in evs if isinstance(e.midi, (int, float))}
                missing = [pc for pc in sorted(set(pcs)) if int(pc) not in present]
                pc = int(missing[0] if missing else sorted(set(pcs))[int(bi) % len(set(pcs))])
                base_oct = (int(median_pitch) // 12) * 12
                cands = []
                for k in (-2, -1, 0, 1, 2):
                    cand0 = base_oct + int(pc) + 12 * int(k)
                    for cand in (cand0, cand0 - 12):
                        cands.append(int(RANGE_LIMITER.clamp_note(int(cand), 3)))
                pitch = int(min(cands, key=lambda n: abs(int(n) - int(median_pitch)))) if cands else int(median_pitch)
                try:
                    vel = int(round(sum(int(e.velocity) for e in evs) / max(1, len(evs))))
                except Exception:
                    vel = 54
                additions.append(
                    Event(
                        channel=3,
                        midi=int(pitch),
                        velocity=int(max(1, min(127, round(float(vel) * 0.82)))),
                        start_beats=float(bar_end - 0.25),
                        duration_beats=0.25,
                        notes=[int(pitch)],
                    )
                )
            if additions:
                typed_events = list(typed_events or []) + additions
    except Exception:
        pass

    try:
        curve = dict(getattr(plan, "arrangement_curve", None) or {})
        cm_mult = float(curve.get("counter_melody_enabled_mult", 0.0) or 0.0)
        role_lc = str(getattr(plan, "section_role", "") or "").strip().lower()
        has_counter = any(int(getattr(ev, "channel", -1)) == 5 for ev in list(typed_events or []))
        if (
            cm_mult >= 0.08
            and not has_counter
            and role_lc in {"a", "verse", "a_prime", "b", "chorus", "hook", "tag"}
        ):
            from data.emotion_scales import melody_scale_intervals_for_emotion

            scale = list(melody_scale_intervals_for_emotion(plan.emotion) or [0, 2, 4, 5, 7, 9, 11])
            bpb = float(getattr(plan, "beats_per_bar", 4.0) or 4.0)
            bars = max(1, int(getattr(plan, "bars", 1) or 1))
            bar = min(bars - 1, max(1, bars // 2))
            root = int(plan.roots[bar]) if 0 <= bar < len(plan.roots or []) else int(getattr(plan, "root_note", 60) or 60)
            degree = 2 if len(scale) > 2 else 0
            midi = int(root) + int(scale[degree]) - 12
            t = float(bar) * float(bpb) + (1.5 if bpb >= 4.0 else 0.5)
            lead_pitch = None
            for ev in list(typed_events or []):
                if int(getattr(ev, "channel", -1)) != 2:
                    continue
                st = float(getattr(ev, "start_beats", 0.0))
                dur = float(getattr(ev, "duration_beats", 0.0))
                if st <= t < st + dur:
                    notes = list(getattr(ev, "notes", []) or [])
                    lead_pitch = int(notes[0]) if notes else int(getattr(ev, "midi", 0) or 0)
                    break
            if lead_pitch is not None and midi >= int(lead_pitch) - 7:
                midi -= 12
            midi = int(RANGE_LIMITER.clamp_note(int(midi), 5))
            vel = int(max(1, min(127, round(52 * float(getattr(plan.emotion, "velocity_multiplier", 1.0) or 1.0)))))
            typed_events.append(
                Event(
                    channel=5,
                    midi=int(midi),
                    velocity=int(vel),
                    start_beats=float(t),
                    duration_beats=0.5,
                    notes=[int(midi)],
                )
            )
    except Exception:
        pass

    typed_events = owner.event_pipeline.validate_event_objects(typed_events)
    typed_events.sort(key=lambda e: e.start_beats)
    plan.events = [e.to_tuple() for e in typed_events]

    # Absolute final strict-scale snap on every pitched channel. Many
    # post-passes can move a pitch onto a non-modal pc:
    #   - lead / counter: octave-clash resolver, perfect-fifth unison
    #     shift, pickup/anticipation gestures, low-flow chord-tone
    #     stabiliser, motif injection;
    #   - arp: ``repair_arp_consecutive_same_midi`` substitutes from raw
    #     chord tones (which include borrowed-chord pcs);
    #   - bass: clamp-after-quantize edge cases on extreme octaves.
    # This is the last choke-point before events leave the planner, so the
    # entire MIDI output is locked to the emotion's strict perceptual
    # scale regardless of what ran upstream. Drone (4) and kick (6) are
    # not pitched-modal layers and stay untouched.
    if resolve_config("composition", "melody_strict_scale_enabled", True, bool):
        from composition.melody_arp_octave_resolve import snap_lead_events_to_strict_scale
        section_root_pc = int(getattr(owner, "_section_root_pc", 0)) % 12
        plan.melody_events = snap_lead_events_to_strict_scale(
            list(plan.melody_events or []),
            emotion=_perceptual_scale_emotion(owner, plan.emotion),
            section_root_pc=int(section_root_pc),
            melody_channel=2,
        )
    # Final professional-polish sweep on the combined plan.events. Many
    # upstream passes (octave resolver, unison shifter, anticipation
    # gestures, motif injection, scale-snap collapse) can re-introduce
    # consecutive same-MIDI repeats and unfilled large leaps on the lead
    # channels (2, 5) AFTER `convert_melody_tokens_to_events` ran its own
    # post-passes. This last sweep applies the strict no-repeat clamp and
    # leap-and-fill smoothing on the merged event list so the final MIDI
    # output meets the professional-melody criteria. Only modifies pitches
    # on channels 2 and 5; durations and start times are untouched.
    sweep_on = resolve_config("composition", "melody_section_final_polish_sweep_enabled", True)
    if sweep_on:
        runtime = getattr(owner, "melody_runtime", None)
        if runtime is not None and plan.events:
            try:
                thr = resolve_config(
                    "composition", "melody_leap_and_fill_threshold_semitones", 5, int
                )
                bridge_on = resolve_config(
                    "composition", "melody_conjunct_bridge_enabled", True, bool
                )
            except Exception:
                thr = 5
                bridge_on = True
            try:
                from composition.markov_style_profiles import style_profile_for_emotion_and_role

                leap_allow = float(
                    getattr(
                        style_profile_for_emotion_and_role(
                            str(getattr(plan.emotion, "name", "") or ""),
                            section_role=str(getattr(plan, "section_role", "") or ""),
                        ),
                        "leap_allowance",
                        0.5,
                    )
                )
            except Exception:
                leap_allow = 0.5
            swept = list(plan.events or [])
            for _ch in (2, 5):
                thr_eff = int(thr)
                try:
                    role_lc = str(getattr(plan, "section_role", "") or "").strip().lower()
                except Exception:
                    role_lc = ""
                if leap_allow <= 0.36:
                    thr_eff = max(4, int(thr_eff) - 1)
                elif leap_allow >= 0.54 and role_lc in {"b", "chorus", "hook", "tag"}:
                    thr_eff = int(thr_eff)
                elif role_lc in {"intro", "outro"}:
                    thr_eff = max(4, int(thr_eff) - 1)
                try:
                    swept = runtime._apply_strict_no_repeat_post_pass(
                        swept, emotion=plan.emotion, channel=int(_ch)
                    )
                except Exception:
                    pass
                if bridge_on:
                    try:
                        swept = runtime._apply_conjunct_bridge_post_pass(
                            swept,
                            emotion=plan.emotion,
                            channel=int(_ch),
                            threshold_st=int(thr_eff),
                        )
                    except Exception:
                        pass
                try:
                    swept = runtime._apply_leap_and_fill_post_pass(
                        swept,
                        emotion=plan.emotion,
                        channel=int(_ch),
                        threshold_st=int(thr_eff),
                    )
                except Exception:
                    pass
                try:
                    swept = runtime._apply_strict_no_repeat_post_pass(
                        swept, emotion=plan.emotion, channel=int(_ch)
                    )
                except Exception:
                    pass
            try:
                emo_lc = str(getattr(getattr(plan, "emotion", None), "name", "") or "").strip().lower()
                weak_leap_emotions = {
                    "desire",
                    "disappointment",
                    "disgust",
                    "embarrassment",
                    "fear",
                    "grief",
                }
                leap_cap = 8 if emo_lc in weak_leap_emotions else 9
                swept = _cap_large_leaps_events(
                    swept,
                    emotion=plan.emotion,
                    channel=2,
                    max_interval=int(leap_cap),
                )
                swept = _cap_large_leaps_events(
                    swept,
                    emotion=plan.emotion,
                    channel=5,
                    max_interval=int(leap_cap + 1),
                )
            except Exception:
                pass
            try:
                swept = _repair_phrase_end_chord_tone_events(plan, swept, channel=2)
            except Exception:
                pass
            try:
                swept = _cap_large_leaps_events(
                    swept,
                    emotion=plan.emotion,
                    channel=2,
                    max_interval=int(leap_cap),
                )
            except Exception:
                pass
            try:
                swept = _repair_phrase_end_chord_tone_events(plan, swept, channel=2)
            except Exception:
                pass
            try:
                swept = _break_repeated_lead_notes_events(plan, swept, channel=2)
            except Exception:
                pass
            try:
                emo_lc2 = str(getattr(getattr(plan, "emotion", None), "name", "") or "").strip().lower()
                target_leap_caps = {
                    "fear": 7,
                    "nervousness": 7,
                    "caring": 8,
                    "disappointment": 7,
                    "disgust": 8,
                    "grief": 8,
                    "disapproval": 8,
                    "amusement": 8,
                    "annoyance": 8,
                    "love": 8,
                }
                if emo_lc2 in target_leap_caps:
                    swept = _smooth_target_emotion_leaps_events(
                        plan,
                        swept,
                        channel=2,
                        max_interval=int(target_leap_caps[emo_lc2]),
                    )
            except Exception:
                pass
            try:
                swept = _break_repeated_lead_notes_events(plan, swept, channel=2)
            except Exception:
                pass
            try:
                swept = _repair_phrase_end_chord_tone_events(plan, swept, channel=2)
            except Exception:
                pass
            try:
                emo_lc4 = str(getattr(getattr(plan, "emotion", None), "name", "") or "").strip().lower()
                if emo_lc4 == "disappointment":
                    swept = _smooth_target_emotion_leaps_events(
                        plan,
                        swept,
                        channel=2,
                        max_interval=7,
                    )
                    swept = _cap_large_leaps_events(
                        swept,
                        emotion=plan.emotion,
                        channel=2,
                        max_interval=7,
                    )
                swept = _break_repeated_lead_notes_events(plan, swept, channel=2)
            except Exception:
                pass
            try:
                emo_lc3 = str(getattr(getattr(plan, "emotion", None), "name", "") or "").strip().lower()
                if emo_lc3 in {"gratitude", "relief"}:
                    from composition.melody_arp_octave_resolve import snap_lead_events_to_strict_scale

                    section_root_pc = int(getattr(owner, "_section_root_pc", 0)) % 12
                    scale_emotion = _perceptual_scale_emotion(owner, plan.emotion)
                    swept = snap_lead_events_to_strict_scale(
                        list(swept or []),
                        emotion=scale_emotion,
                        section_root_pc=int(section_root_pc),
                        melody_channel=2,
                    )
                    swept = _repair_phrase_end_chord_tone_events(plan, swept, channel=2)
                    swept = _break_repeated_lead_notes_events(plan, swept, channel=2)
                    swept = snap_lead_events_to_strict_scale(
                        list(swept or []),
                        emotion=scale_emotion,
                        section_root_pc=int(section_root_pc),
                        melody_channel=2,
                    )
            except Exception:
                pass
            plan.events = swept

    # ------------------------------------------------------------------
    # Optional: export a full joint training row (bass + chords + lead + arp + counter)
    # aligned to the harmonic plan. This complements the lead-only export hook in
    # ai/markov/melody/generation/phrase_generation.py.
    # ------------------------------------------------------------------
    enabled = resolve_config("composition", "export_live_joint_training_enabled", False, bool)
    out_path = resolve_config("composition", "export_live_joint_training_path", '', str)
    if enabled and out_path:
        try:
            import json
            from pathlib import Path

            # Best-effort tokenization: represent each monophonic lane as degree+dur pairs
            # relative to the bar root + emotion scale. Also store pitch-class offsets (0..11)
            # so out-of-scale color tones can still be learned if desired.
            emo = getattr(plan, "emotion", None)
            scale_intervals = list(getattr(emo, "scale_intervals", []) or []) if emo is not None else []
            scale_pcs = [int(iv) % 12 for iv in scale_intervals] if scale_intervals else []
            roots = list(getattr(plan, "roots", []) or [])
            bpb = float(getattr(plan, "beats_per_bar", 4.0) or 4.0)
            bars = int(getattr(plan, "bars", 0) or 0)

            def _bar_index(t_beats: float) -> int:
                if bpb <= 1e-9:
                    return 0
                return int(float(t_beats) // float(bpb))

            def _pc_from_midi(midi: int, root_midi: int) -> int:
                return int((int(midi) - int(root_midi)) % 12)

            def _degree_from_midi(midi: int, root_midi: int) -> int:
                if not scale_pcs:
                    return -2
                rel = _pc_from_midi(int(midi), int(root_midi))
                try:
                    return int(scale_pcs.index(int(rel)))
                except ValueError:
                    return -2

            def _events_to_tokens(events: list, *, channel: int) -> dict:
                deg_seq = []
                pc_seq = []
                midi_seq = []
                for ev in list(events or []):
                    try:
                        if not (isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == int(channel)):
                            continue
                        st = float(ev[3])
                        dur = float(ev[4])
                        midi = int(ev[1])
                        bi = _bar_index(float(st))
                        if bi < 0 or (bars and bi >= bars) or bi >= len(roots) or not roots:
                            continue
                        root_m = int(roots[bi])
                        deg = _degree_from_midi(int(midi), int(root_m))
                        pc = _pc_from_midi(int(midi), int(root_m))
                        # Keep only positive durations (defensive).
                        dur = float(max(0.0, dur))
                        deg_seq.append([int(deg), float(dur)])
                        pc_seq.append([int(pc), float(dur)])
                        midi_seq.append([int(midi), float(dur)])
                    except Exception:
                        continue
                return {
                    "degrees": deg_seq or None,
                    "pcs": pc_seq or None,
                    "midi": midi_seq or None,
                }

            # Chord markov tokens (degree + stable bucket).
            chord_markov_tokens = None
            chord_sequence = list(getattr(plan, "chords", []) or [])
            if chord_sequence:
                try:
                    from data.tokens import ChordToken

                    toks = []
                    for ch in chord_sequence:
                        try:
                            s = str(ch or "").strip()
                            rlc = s.lower()
                            if "dim" in rlc or "°" in s or "ø" in s:
                                bucket = "dim"
                            elif "aug" in rlc or "+" in s:
                                bucket = "aug"
                            elif "sus" in rlc:
                                bucket = "sus"
                            elif "min" in rlc or (s and s[0].islower()):
                                bucket = "min"
                            elif "maj" in rlc or (s and s[0].isupper() and not rlc.startswith("v")):
                                bucket = "maj"
                            elif rlc.startswith("v") or "7" in s:
                                bucket = "dom"
                            else:
                                bucket = "dom"
                        except Exception:
                            bucket = "dom"
                        toks.append(ChordToken.from_symbol(str(ch), bucket=bucket).serialize(use_degree=True))
                    chord_markov_tokens = toks
                except Exception:
                    chord_markov_tokens = None

            # Use the finalized tuple events as the source of truth for per-lane sequences.
            evs = list(getattr(plan, "events", []) or [])
            lead = _events_to_tokens(evs, channel=2)
            arp = _events_to_tokens(evs, channel=3)
            counter = _events_to_tokens(evs, channel=5)
            bass = _events_to_tokens(evs, channel=0)

            phrase_contours: list = []
            phrase_roles: list = []
            try:
                phrase_contours = list(getattr(owner, "_last_generated_phrase_contours", []) or [])
            except Exception:
                phrase_contours = []
            mg = getattr(owner, "melody_gen", None)
            if not phrase_contours and mg is not None:
                try:
                    phrase_contours = list(getattr(mg, "_last_phrase_contours", []) or [])
                except Exception:
                    pass
            if mg is not None:
                try:
                    phrase_plans = getattr(mg, "_last_phrase_plans", None)
                    if isinstance(phrase_plans, list):
                        phrase_roles = [
                            str(getattr(pp, "phrase_role", "") or "") for pp in phrase_plans if pp is not None
                        ]
                except Exception:
                    pass
            if not phrase_roles and int(bars) > 0:
                try:
                    phrase_len = phrase_length_bars_clamped(1, 32)
                    for pid in range(int((int(bars) + int(phrase_len) - 1) // int(phrase_len))):
                        bar_start = int(pid * int(phrase_len))
                        phrase_roles.append(
                            str(owner.chord_utils.phrase_role(bar_start, int(bars), phrase_length=int(phrase_len)) or "")
                        )
                except Exception:
                    pass
            if not phrase_contours and phrase_roles:
                phrase_contours = ["static" for _ in phrase_roles]

            melody_pairs = None
            try:
                deg_seq = (lead or {}).get("degrees")
                if isinstance(deg_seq, list) and deg_seq:
                    melody_pairs = [[int(d), float(dur)] for d, dur in deg_seq]
            except Exception:
                melody_pairs = None

            row = {
                "schema": "live_joint_training.v1",
                "emotion": str(getattr(emo, "name", "") or "") if emo is not None else None,
                "section_role": str(getattr(plan, "section_role", "") or ""),
                "section_index": int(getattr(plan, "section_index", 0) or 0),
                "bars": int(bars),
                "beats_per_bar": float(bpb),
                "root_note": int(getattr(plan, "root_note", 0) or 0),
                "scale_intervals": [int(iv) for iv in scale_intervals] if scale_intervals else None,
                "chord_sequence": chord_sequence or None,
                "roots": [int(r) for r in roots] if roots else None,
                "chord_markov_tokens": chord_markov_tokens,
                "lead": lead,
                "arp": arp,
                "counter": counter,
                "bass": bass,
                "phrase_contours": phrase_contours or None,
                "phrase_roles": phrase_roles or None,
                "melody": melody_pairs,
                # Keep accept_score for compatibility with the existing split scripts.
                "accept_score": 1.0,
            }

            p = Path(str(out_path)).expanduser()
            if not p.is_absolute():
                p = Path.cwd() / p
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
        except Exception:
            # Never break realtime composition due to dataset export issues.
            pass

    # ------------------------------------------------------------------
    # Semantic annotations (sidecar): phrase spans + per-event tags.
    # Keeps tuple playback stable while enabling motif-/phrase-aware passes.
    # ------------------------------------------------------------------
    try:
        bars = int(getattr(plan, "bars", 0) or 0)
        bpb = float(getattr(plan, "beats_per_bar", 4.0) or 4.0)
    except Exception:
        bars = 0
        bpb = 4.0

    # Prefer the actual PhrasePlanner outputs from the Markov melody generator when available.
    phrase_plans = None
    try:
        mg = getattr(owner, "melody_gen", None)
        phrase_plans = getattr(mg, "_last_phrase_plans", None) if mg is not None else None
    except Exception:
        phrase_plans = None
    try:
        phrase_end_beats_actual = list(getattr(mg, "_last_phrase_end_beats", None) or []) if mg is not None else []
    except Exception:
        phrase_end_beats_actual = []

    phrase_len_fallback = phrase_length_bars_clamped(1, 32)

    def _layer_for_channel(ch: int) -> str:
        return CHANNEL_NAMES.get(int(ch), "other")

    # Phrase spans:
    # - If phrase plans exist, use their phrase_role/cadence_degree and map them across bars.
    # - Otherwise fall back to fixed-length bar phrases.
    phrase_spans: list[dict] = []
    phrase_id_by_bar: list[int] = [0 for _ in range(max(0, bars))]
    try:
        if bars > 0 and bpb > 1e-9 and isinstance(phrase_plans, list) and phrase_plans:
            nphr = max(1, int(len(phrase_plans)))
            # Map phrase plans to bar windows (equal-sized chunks across section bars).
            for pid, pp in enumerate(list(phrase_plans)):
                start_beats = float(phrase_end_beats_actual[pid - 1]) if pid > 0 and pid - 1 < len(phrase_end_beats_actual) else float((float(pid) / float(nphr)) * float(bars) * float(bpb))
                end_beats = float(phrase_end_beats_actual[pid]) if pid < len(phrase_end_beats_actual) else float((float(pid + 1) / float(nphr)) * float(bars) * float(bpb))
                start_beats = max(0.0, min(float(bars) * float(bpb), float(start_beats)))
                end_beats = max(float(start_beats), min(float(bars) * float(bpb), float(end_beats)))
                bar_start = int(float(start_beats) // float(bpb))
                bar_end = int((float(end_beats) + max(1e-9, float(bpb) * 0.25)) // float(bpb))
                if pid == nphr - 1:
                    bar_end = int(bars)
                bar_start = max(0, min(int(bars), int(bar_start)))
                bar_end = max(int(bar_start), min(int(bars), int(bar_end)))
                for b in range(bar_start, bar_end):
                    if 0 <= b < len(phrase_id_by_bar):
                        phrase_id_by_bar[b] = int(pid)
                length_beats = max(0.0, float(end_beats) - float(start_beats))
                try:
                    phr_role = str(getattr(pp, "phrase_role", "") or "")
                except Exception:
                    phr_role = ""
                try:
                    cad_deg = int(getattr(pp, "cadence_degree", 0) or 0)
                except Exception:
                    cad_deg = 0
                phrase_spans.append(
                    {
                        "phrase_id": int(pid),
                        "start_beats": float(start_beats),
                        "length_beats": float(length_beats),
                        "end_beats": float(end_beats),
                        "bar_start": int(bar_start),
                        "bar_end": int(bar_end),
                        "phrase_role": str(phr_role or ""),
                        "cadence_degree": int(cad_deg),
                    }
                )
        elif bars > 0 and bpb > 1e-9:
            # Fixed-length fallback.
            phrase_len = int(phrase_len_fallback)
            for pid in range(int((bars + phrase_len - 1) // phrase_len)):
                bar_start = int(pid * phrase_len)
                bar_end = int(min(bars, (pid + 1) * phrase_len))
                for b in range(bar_start, bar_end):
                    if 0 <= b < len(phrase_id_by_bar):
                        phrase_id_by_bar[b] = int(pid)
                start_beats = float(bar_start) * float(bpb)
                length_beats = float(max(0, bar_end - bar_start)) * float(bpb)
                phr_role = ""
                try:
                    phr_role = str(owner.chord_utils.phrase_role(bar_start, bars, phrase_length=phrase_len) or "")
                except Exception:
                    phr_role = ""
                phrase_spans.append(
                    {
                        "phrase_id": int(pid),
                        "start_beats": float(start_beats),
                        "length_beats": float(length_beats),
                        "end_beats": float(start_beats + length_beats),
                        "bar_start": int(bar_start),
                        "bar_end": int(bar_end),
                        "phrase_role": phr_role,
                        "cadence_degree": None,
                    }
                )
    except Exception:
        phrase_spans = []
        phrase_id_by_bar = [0 for _ in range(max(0, bars))]

    # Per-event annotations aligned with final `plan.events`.
    annotations: list[dict] = []
    try:
        sec_idx = int(getattr(plan, "section_index", 0) or 0)
    except Exception:
        sec_idx = 0
    try:
        role = str(getattr(plan, "section_role", "") or "")
    except Exception:
        role = ""

    for ev in plan.events:
        try:
            ch = int(ev[0])
            st = float(ev[3])
            bar_index = int(st // bpb) if bpb > 1e-9 else 0
        except Exception:
            ch = -1
            st = 0.0
            bar_index = 0
        if 0 <= int(bar_index) < len(phrase_id_by_bar):
            pid = int(phrase_id_by_bar[int(bar_index)])
        else:
            pid = int(bar_index // phrase_len_fallback) if phrase_len_fallback > 0 else 0
        phr_role = ""
        try:
            # Derive phrase role from bar index.
            phr_role = str(owner.chord_utils.phrase_role(bar_index, bars, phrase_length=phrase_len_fallback) or "")
        except Exception:
            phr_role = ""
        annotations.append(
            {
                "section_index": sec_idx,
                "role": role,
                "layer": _layer_for_channel(ch),
                "channel": ch,
                "start_beats": float(st),
                "bar_index": int(bar_index),
                "phrase_id": int(pid),
                "phrase_role": phr_role,
                # Motif tags populated later by motif injection / development passes.
                "motif_id": None,
                "motif_variant": None,
            }
        )

    # Tag motif windows (if the motif planner recorded them on the plan).
    try:
        tags = getattr(plan, "_motif_slot_tags", None)
    except Exception:
        tags = None
    if isinstance(tags, list) and annotations:
        try:
            for a in annotations:
                ch = int(a.get("channel", -1))
                st = float(a.get("start_beats", 0.0))
                for t in tags:
                    try:
                        tch = int(t.get("channel", -1))
                        if tch != ch:
                            continue
                        t0 = float(t.get("start_beats", 0.0))
                        t1 = t0 + float(t.get("length_beats", 0.0))
                        if st + 1e-6 < t0 or st > t1 - 1e-6:
                            continue
                        a["motif_id"] = t.get("motif_id")
                        a["motif_variant"] = t.get("motif_variant")
                        break
                    except Exception:
                        continue
        except Exception:
            pass

    try:
        plan.phrase_spans = phrase_spans
    except Exception:
        pass
    try:
        plan.event_annotations = annotations
    except Exception:
        pass

    # ------------------------------------------------------------------
    # Debug trace (compact per-bar).
    # Exposes: harmonic feature key, phrase role, (best-effort) contour/cadence,
    # chosen chord-hit action, and realized arp↔melody overlaps.
    # ------------------------------------------------------------------
    try:
        from ai.markov.melody.ensemble import MarkovModelSet
    except Exception:
        MarkovModelSet = None

    try:
        bars = int(getattr(plan, "bars", 0) or 0)
        bpb = float(getattr(plan, "beats_per_bar", 4.0) or 4.0)
        chords = list(getattr(plan, "chords", []) or [])
        roots = list(getattr(plan, "roots", []) or [])
        tension = list((getattr(plan, "timeline_targets", None) or {}).get("tension", []) or [])

        # Harmonic rhythm chosen actions (from HarmonyManager).
        hr_actions = []
        try:
            hr_actions = list(getattr(owner.harmony_manager, "_debug_hr_action_by_bar", []) or [])
        except Exception:
            hr_actions = []

        # Best-effort phrase contours (engine keeps the last generated phrase contours).
        contours = []
        try:
            contours = list(getattr(owner, "_last_generated_phrase_contours", []) or [])
        except Exception:
            contours = []

        # Emotion anchors (for trace).
        cadence_style = "authentic"
        tension_arc = ""
        try:
            from data.emotion_anchors import anchors_for_emotion

            anc = anchors_for_emotion(getattr(plan, "emotion", None))
            cadence_style = str(getattr(anc, "cadence", "authentic") or "authentic")
            tension_arc = str(getattr(anc, "tension_arc", "") or "")
        except Exception:
            cadence_style = "authentic"
            tension_arc = ""

        # Build per-bar overlap counts: melody onsets that fall during an arp event.
        # (Computed from the typed event stream to reflect finalization/humanization.)
        arp_by_bar: list[list[tuple[float, float]]] = [[] for _ in range(max(0, bars))]
        mel_onsets_by_bar: list[list[float]] = [[] for _ in range(max(0, bars))]
        for ev in typed_events:
            try:
                bar = int(float(ev.start_beats) // bpb) if bpb > 1e-9 else 0
            except Exception:
                bar = 0
            if bar < 0 or bar >= bars:
                continue
            s = float(ev.start_beats) - float(bar) * bpb
            e = s + float(ev.duration_beats)
            if int(ev.channel) == 3:
                arp_by_bar[bar].append((s, e))
            elif int(ev.channel) == 2:
                mel_onsets_by_bar[bar].append(float(s))

        def _count_overlaps(bar: int) -> int:
            if bar < 0 or bar >= bars:
                return 0
            intervals = arp_by_bar[bar]
            if not intervals:
                return 0
            c = 0
            for t0 in mel_onsets_by_bar[bar]:
                for a0, a1 in intervals:
                    if a0 - 1e-6 <= t0 <= a1 + 1e-6:
                        c += 1
                        break
            return int(c)

        trace: list[dict] = []
        # Optional per-bar texture script computed during section build.
        try:
            tex = getattr(plan, "texture_by_bar", None)
            tex = list(tex) if isinstance(tex, list) else []
        except Exception:
            tex = []
        # Tension targets (from timeline) + tension used (from harmony manager).
        try:
            tension_target = list((getattr(plan, "timeline_targets", None) or {}).get("tension", []) or [])
        except Exception:
            tension_target = []
        try:
            t_used = getattr(getattr(owner, "harmony_manager", None), "_debug_tension_used_by_bar", None)
            t_used = list(t_used) if isinstance(t_used, list) else []
        except Exception:
            t_used = []
        # Color cap debug exported by chord planner (section-level scalar).
        try:
            color_cap = getattr(owner, "_debug_harmony_color_cap", None)
            color_cap = float(color_cap) if color_cap is not None else None
        except Exception:
            color_cap = None

        # Style profile debug (section-level).
        style_profile_id = ""
        style_leap_allowance = None
        style_harmony_motion_allowance = None
        style_harmony_color_allowance = None
        style_melody_rhythm_activity = None
        s = markov_style_strength()
        if float(s) > 1e-6:
            try:
                from composition.markov_style_profiles import style_profile_for_emotion_and_role

                emo_name = str(getattr(getattr(plan, "emotion", None), "name", "") or "")
                sec_role = str(getattr(plan, "section_role", "") or "")
                prof = style_profile_for_emotion_and_role(emo_name, sec_role)
                style_profile_id = str(getattr(prof, "profile_id", "") or "")
                style_leap_allowance = float(getattr(prof, "leap_allowance", 0.5) or 0.5)
                style_harmony_motion_allowance = float(getattr(prof, "harmony_motion_allowance", 0.5) or 0.5)
                style_harmony_color_allowance = float(getattr(prof, "harmony_color_allowance", 0.5) or 0.5)
                style_melody_rhythm_activity = float(getattr(prof, "melody_rhythm_activity", 0.5) or 0.5)
            except Exception:
                pass
        for bar in range(max(0, bars)):
            chord_sym = chords[bar] if bar < len(chords) else ""
            feat = None
            if MarkovModelSet is not None:
                try:
                    feat = str(MarkovModelSet.extract_harmonic_feature_key(str(chord_sym or "")))
                except Exception:
                    feat = None
            # Predict melody cadence target degrees (best-effort).
            # These correspond to the logic in NoteGenerator:
            # - authentic/plagal -> cadence_degree (usually 0)
            # - suspended -> prefer 2 or 4 (deg 1 or 3), dominant favors 4
            # - avoid -> prefer 2 or 7 (deg 1 or 6), dominant favors 7
            mel_cad_target_current = None
            mel_cad_target_next = None
            try:
                func_cur = MarkovModelSet.extract_harmonic_function(str(chord_sym or "")) if MarkovModelSet is not None else "other"
            except Exception:
                func_cur = "other"
            try:
                func_next = MarkovModelSet.extract_harmonic_function(str(chords[bar + 1] or "")) if (MarkovModelSet is not None and (bar + 1) < len(chords)) else "other"
            except Exception:
                func_next = "other"
            is_dom_cur = str(func_cur or "").lower() == "dom"
            is_dom_next = str(func_next or "").lower() == "dom"
            if str(cadence_style).lower() in {"suspended", "avoid"}:
                if str(cadence_style).lower() == "suspended":
                    mel_cad_target_current = 3 if is_dom_cur else 1
                    mel_cad_target_next = 3 if is_dom_next else 1
                else:
                    mel_cad_target_current = 6 if is_dom_cur else 1
                    mel_cad_target_next = 6 if is_dom_next else 1
            else:
                mel_cad_target_current = 0
                mel_cad_target_next = 0
            try:
                phrase_len = phrase_length_bars_clamped(1, 16)
                role = owner.chord_utils.phrase_role(int(bar), int(bars), phrase_length=int(phrase_len))
            except Exception:
                role = ""
            # Contours are per-phrase; map bar->phrase_idx using the configured phrase length.
            phrase_idx = int(bar // max(1, int(phrase_len))) if bar >= 0 else 0
            contour = ""
            if contours and 0 <= phrase_idx < len(contours):
                try:
                    contour = str(contours[phrase_idx] or "")
                except Exception:
                    contour = ""
            action = ""
            if hr_actions and 0 <= bar < len(hr_actions) and hr_actions[bar] is not None:
                action = str(hr_actions[bar] or "")
            tbar = None
            if tension and 0 <= bar < len(tension):
                try:
                    tbar = float(tension[bar])
                except Exception:
                    tbar = None
            trace.append(
                {
                    "bar": int(bar),
                    "chord": str(chord_sym or ""),
                    "feature_key": feat or "",
                    "phrase_role": str(role or ""),
                    "contour": str(contour or ""),
                    "cadence_style": str(cadence_style or ""),
                    "tension_arc": str(tension_arc or ""),
                    "mel_cad_target_current": mel_cad_target_current,
                    "mel_cad_target_next": mel_cad_target_next,
                    "hit_action": str(action or ""),
                    "melody_over_arp": int(_count_overlaps(bar)),
                    "tension": tbar,
                    "tension_target": (
                        float(tension_target[bar])
                        if 0 <= int(bar) < len(tension_target) and tension_target[bar] is not None
                        else None
                    ),
                    "tension_used": (
                        float(t_used[bar])
                        if 0 <= int(bar) < len(t_used) and t_used[bar] is not None
                        else None
                    ),
                    "harmony_color_cap": float(color_cap) if color_cap is not None else None,
                    "style_profile": str(style_profile_id or ""),
                    "style_leap_allowance": float(style_leap_allowance) if style_leap_allowance is not None else None,
                    "style_harmony_motion_allowance": (
                        float(style_harmony_motion_allowance) if style_harmony_motion_allowance is not None else None
                    ),
                    "style_harmony_color_allowance": (
                        float(style_harmony_color_allowance) if style_harmony_color_allowance is not None else None
                    ),
                    "style_melody_rhythm_activity": (
                        float(style_melody_rhythm_activity) if style_melody_rhythm_activity is not None else None
                    ),
                    "root": int(roots[bar]) if bar < len(roots) and roots[bar] is not None else None,
                    "chord_center": (
                        int(sorted(int(n) for n in (getattr(plan, "chosen_chord", []) or [])[bar] if isinstance(n, int))[
                            len(sorted(int(n) for n in (getattr(plan, "chosen_chord", []) or [])[bar] if isinstance(n, int))) // 2
                        ])
                        if getattr(plan, "chosen_chord", None)
                        and 0 <= int(bar) < len(getattr(plan, "chosen_chord", []) or [])
                        and (getattr(plan, "chosen_chord", []) or [])[bar]
                        else None
                    ),
                    "handoff_common_tones": (
                        int(getattr(owner, "_last_handoff_bar0_common_tones", 0) or 0)
                        if int(bar) == 0 and getattr(owner, "_emotion_transition_handoff_ctx", None)
                        else None
                    ),
                    # Texture script (realtime orchestration intents)
                    "drop_level": (
                        float((tex[bar] or {}).get("drop_level", 0.0))
                        if 0 <= int(bar) < len(tex) and isinstance(tex[bar], dict)
                        else 0.0
                    ),
                    "lead_focus": (
                        float((tex[bar] or {}).get("lead_focus", 0.0))
                        if 0 <= int(bar) < len(tex) and isinstance(tex[bar], dict)
                        else 0.0
                    ),
                    "register_lift_semitones": (
                        int((tex[bar] or {}).get("register_lift_semitones", 0))
                        if 0 <= int(bar) < len(tex) and isinstance(tex[bar], dict)
                        else 0
                    ),
                    "fx_space_boost": (
                        float((tex[bar] or {}).get("fx_space_boost", 0.0))
                        if 0 <= int(bar) < len(tex) and isinstance(tex[bar], dict)
                        else 0.0
                    ),
                    "fx_width_boost": (
                        float((tex[bar] or {}).get("fx_width_boost", 0.0))
                        if 0 <= int(bar) < len(tex) and isinstance(tex[bar], dict)
                        else 0.0
                    ),
                    "fx_grit_boost": (
                        float((tex[bar] or {}).get("fx_grit_boost", 0.0))
                        if 0 <= int(bar) < len(tex) and isinstance(tex[bar], dict)
                        else 0.0
                    ),
                    # Harmony Markov debug (opt-in; collected during chord sampling).
                    "harmony_markov": (
                        (getattr(owner, "_debug_harmony_markov_trace_by_bar", []) or [])[bar]
                        if isinstance(getattr(owner, "_debug_harmony_markov_trace_by_bar", None), list)
                        and 0 <= int(bar) < len(getattr(owner, "_debug_harmony_markov_trace_by_bar", []) or [])
                        else None
                    ),
                    "stability_fixes": {
                        "chord_one_note_fixes": int(getattr(plan, "_debug_stability_chord_one_note_fixes", 0) or 0),
                        "arp_repeat_runs": int(getattr(plan, "_debug_stability_arp_repeat_runs", 0) or 0),
                    },
                }
            )

        plan.debug_trace_by_bar = trace
    except Exception:
        # Never fail generation for debug output.
        try:
            plan.debug_trace_by_bar = []
        except Exception:
            pass
    return plan
