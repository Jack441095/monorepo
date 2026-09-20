"""Chorus hook blueprint selection and application."""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional, Tuple, cast

from midi.midi_range_limiter import RANGE_LIMITER

from ..section_plan import SectionPlan

_CHORUS_HOOK_FAMILY_BY_EMOTION: Dict[str, str] = {
    "admiration": "anthem",
    "amusement": "bright_motor",
    "anger": "anthem",
    "approval": "anthem",
    "caring": "yearning_pulse",
    "confusion": "tension_step",
    "curiosity": "tension_step",
    "desire": "yearning_pulse",
    "disappointment": "yearning_pulse",
    "disapproval": "tension_step",
    "disgust": "tension_step",
    "fear": "tension_step",
    "joy": "bright_motor",
    "love": "yearning_pulse",
    "neutral": "anthem",
    "pride": "anthem",
    "surprise": "bright_motor",
}

_MASKING_FOCUS_EMOTIONS: Dict[str, float] = {
    "embarrassment": 1.00,
}


_CHORUS_HOOK_BLUEPRINTS: Dict[str, List[Dict[str, Any]]] = {
    "bright_motor": [
        {
            "name": "motor_lift",
            "span_bars": 2,
            "melody_steps_by_bar": [[0, 4, 8, 12], [0, 6, 8, 12]],
            "arp_steps_by_bar": [[0, 2, 4, 6, 8, 10, 12, 14], [0, 2, 4, 6, 8, 10, 12, 14]],
            "melody_register_floor": 74,
            "arp_density_mult_min": 1.16,
            "target_notes_per_bar_min": 8.0,
            "chorus_interaction_mode": "fill",
        },
        {
            "name": "syncopated_motor",
            "span_bars": 2,
            "melody_steps_by_bar": [[0, 3, 8, 12], [0, 4, 10, 12]],
            "arp_steps_by_bar": [[0, 3, 4, 7, 8, 11, 12, 15], [0, 2, 4, 7, 8, 10, 12, 15]],
            "melody_register_floor": 75,
            "arp_density_mult_min": 1.12,
            "target_notes_per_bar_min": 7.6,
            "chorus_interaction_mode": "fill",
        },
    ],
    "anthem": [
        {
            "name": "anthem_pulse",
            "span_bars": 2,
            "melody_steps_by_bar": [[0, 4, 8, 12], [0, 4, 10, 12]],
            "arp_steps_by_bar": [[0, 4, 8, 12, 14], [0, 4, 8, 10, 12, 14]],
            "melody_register_floor": 72,
            "arp_density_mult_min": 1.02,
            "target_notes_per_bar_min": 6.2,
            "chorus_interaction_mode": "coexist",
        },
        {
            "name": "anthem_answer",
            "span_bars": 2,
            "melody_steps_by_bar": [[0, 6, 8, 12], [0, 4, 8, 14]],
            "arp_steps_by_bar": [[0, 4, 8, 12], [0, 4, 8, 10, 12]],
            "melody_register_floor": 73,
            "arp_density_mult_min": 1.00,
            "target_notes_per_bar_min": 6.0,
            "chorus_interaction_mode": "coexist",
        },
    ],
    "tension_step": [
        {
            "name": "step_probe",
            "span_bars": 2,
            "melody_steps_by_bar": [[0, 2, 6, 8, 12], [0, 2, 7, 8, 12]],
            "arp_steps_by_bar": [[0, 4, 6, 8, 12, 14], [0, 4, 6, 8, 12, 14]],
            "melody_register_floor": 71,
            "arp_density_mult_min": 0.96,
            "target_notes_per_bar_min": 6.0,
            "chorus_interaction_mode": "fill",
        },
        {
            "name": "suspended_question",
            "span_bars": 2,
            "melody_steps_by_bar": [[0, 4, 7, 8, 12], [0, 3, 8, 10, 12]],
            "arp_steps_by_bar": [[0, 4, 8, 10, 12, 14], [0, 4, 7, 8, 12, 15]],
            "melody_register_floor": 70,
            "arp_density_mult_min": 0.98,
            "target_notes_per_bar_min": 6.2,
            "chorus_interaction_mode": "fill",
        },
    ],
    "yearning_pulse": [
        {
            "name": "yearning_pulse",
            "span_bars": 2,
            "melody_steps_by_bar": [[0, 4, 10, 12], [0, 4, 8, 12]],
            "arp_steps_by_bar": [[0, 4, 8, 12], [0, 4, 8, 10, 12]],
            "melody_register_floor": 72,
            "arp_density_mult_min": 0.94,
            "target_notes_per_bar_min": 5.6,
            "chorus_interaction_mode": "coexist",
        },
        {
            "name": "suspended_longing",
            "span_bars": 2,
            "melody_steps_by_bar": [[0, 6, 8, 12], [0, 4, 8, 12]],
            "arp_steps_by_bar": [[0, 4, 8, 12], [0, 4, 8, 12, 14]],
            "melody_register_floor": 71,
            "arp_density_mult_min": 0.92,
            "target_notes_per_bar_min": 5.4,
            "chorus_interaction_mode": "coexist",
        },
    ],
}


def chorus_hook_emotion_key_from_plan(plan: SectionPlan) -> str:
    try:
        return str(getattr(getattr(plan, "emotion", None), "name", "") or "").strip().lower()
    except Exception:
        return ""


def _chorus_hook_family_for_emotion(emotion_name: str) -> str:
    return _CHORUS_HOOK_FAMILY_BY_EMOTION.get(str(emotion_name or "").strip().lower(), "anthem")


def _masking_focus_strength_for_emotion(emotion_name: str, *, section_role: str) -> float:
    role = str(section_role or "").strip().lower()
    emo = str(emotion_name or "").strip().lower()
    if role in {"pre_chorus", "b", "chorus", "hook", "tag"}:
        return float(_MASKING_FOCUS_EMOTIONS.get(emo, 0.0))
    if role == "a":
        return float(_MASKING_FOCUS_EMOTIONS.get(emo, 0.0)) * 0.35
    return 0.0


def _normalized_hook_steps(steps: List[int]) -> List[int]:
    return [int(s) for s in sorted({max(0, min(15, int(s))) for s in list(steps or [])})]


def _select_seeded_chorus_hook_blueprint(
    owner: Any,
    plan: SectionPlan,
    *,
    section_role: str,
    section_index: int,
) -> Optional[Dict[str, Any]]:
    role = str(section_role or "").strip().lower()
    if role not in {"b", "chorus", "hook", "tag"}:
        return None
    emo_key = chorus_hook_emotion_key_from_plan(plan) or "neutral"
    store = getattr(owner, "_chorus_hook_blueprint_by_emotion", None)
    if not isinstance(store, dict):
        store = {}
        try:
            setattr(owner, "_chorus_hook_blueprint_by_emotion", store)
        except Exception:
            pass
    if emo_key in store and isinstance(store.get(emo_key), dict):
        return dict(store.get(emo_key) or {})

    family = _chorus_hook_family_for_emotion(emo_key)
    choices = list(_CHORUS_HOOK_BLUEPRINTS.get(family, []) or [])
    if not choices:
        return None
    try:
        drng = getattr(owner, "deterministic_rng", None)
        rr_any = drng("chorus_hook_blueprint", str(emo_key), str(family), int(section_index)) if callable(drng) else getattr(owner, "rng", random)
        rr = cast(Any, rr_any)
        pick = dict(rr.choice(choices))
    except Exception:
        pick = dict(random.choice(choices))
    pick["family"] = str(family)
    try:
        store[str(emo_key)] = dict(pick)
    except Exception:
        pass
    return dict(pick)


def _apply_chorus_hook_blueprint_to_arp_plan(
    arp_plan: Dict[str, Any],
    blueprint: Optional[Dict[str, Any]],
    *,
    bars: int,
) -> Dict[str, Any]:
    plan_out = dict(arp_plan or {})
    if not isinstance(blueprint, dict):
        return plan_out
    try:
        span_bars = max(1, int(blueprint.get("span_bars", 2) or 2))
    except Exception:
        span_bars = 2
    cell = list(blueprint.get("arp_steps_by_bar", []) or [])
    if cell:
        try:
            existing_span = int(plan_out.get("rhythm_cell_span_bars", 0) or 0)
        except Exception:
            existing_span = 0
        if not (existing_span >= 4 and plan_out.get("onset_steps_by_bar")):
            onset_steps_by_bar: List[List[int]] = []
            for bi in range(max(0, int(bars))):
                onset_steps_by_bar.append(list(cell[bi % max(1, span_bars)]))
            plan_out["onset_steps_by_bar"] = onset_steps_by_bar
            plan_out["rhythm_cell_span_bars"] = int(span_bars)
    try:
        dmm = float(blueprint.get("arp_density_mult_min", 0.0) or 0.0)
        if dmm > 1e-6:
            plan_out["density_mult"] = max(float(plan_out.get("density_mult", 1.0) or 1.0), float(dmm))
    except Exception:
        pass
    try:
        tnpb = float(blueprint.get("target_notes_per_bar_min", 0.0) or 0.0)
        if tnpb > 1e-6:
            plan_out["target_notes_per_bar"] = max(float(plan_out.get("target_notes_per_bar", 0.0) or 0.0), float(tnpb))
    except Exception:
        pass
    try:
        plan_out["lane_half_width"] = int(max(5, min(10, int(plan_out.get("lane_half_width", 8) or 8))))
    except Exception:
        pass
    return plan_out


def _apply_chorus_hook_blueprint_to_melody(
    plan: SectionPlan,
    blueprint: Optional[Dict[str, Any]],
    *,
    section_role: str,
) -> None:
    role = str(section_role or "").strip().lower()
    if role not in {"b", "chorus", "hook", "tag"}:
        return
    if not isinstance(blueprint, dict):
        return
    events = list(getattr(plan, "melody_events", []) or [])
    if not events:
        return
    try:
        bpb = float(getattr(plan, "beats_per_bar", 4.0) or 4.0)
    except Exception:
        bpb = 4.0
    if bpb <= 1e-9:
        return
    try:
        span_bars = max(1, int(blueprint.get("span_bars", 2) or 2))
    except Exception:
        span_bars = 2
    span = float(span_bars) * float(bpb)
    steps_by_bar = list(blueprint.get("melody_steps_by_bar", []) or [])
    if not steps_by_bar:
        return
    target_pos: List[float] = []
    for bi in range(span_bars):
        steps = list(steps_by_bar[bi % len(steps_by_bar)] or [])
        for stp in steps:
            target_pos.append(float(bi) * float(bpb) + 0.25 * float(int(stp)))
    target_pos = sorted({round(float(x), 6) for x in target_pos if 0.0 <= float(x) < span - 1e-6})
    if len(target_pos) < 3:
        return
    lead = [
        ev for ev in sorted(events, key=lambda e: float(e[3]) if len(e) == 6 else 0.0)
        if isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == 2
    ]
    lead_open = [ev for ev in lead if float(ev[3]) < span - 1e-6]
    if len(lead_open) < 3:
        return
    try:
        register_floor = int(blueprint.get("melody_register_floor", 72) or 72)
    except Exception:
        register_floor = 72
    rebuilt: List[tuple] = []
    keep_n = min(len(lead_open), len(target_pos))
    replaced_ids = {id(ev) for ev in lead_open[:keep_n]}
    for i in range(keep_n):
        ev = lead_open[i]
        try:
            midi = int(ev[5][0]) if isinstance(ev[5], list) and ev[5] else int(ev[1])
        except Exception:
            midi = int(ev[1])
        while int(midi) < int(register_floor):
            midi += 12
        midi = int(RANGE_LIMITER.clamp_note(int(midi), 2))
        st = float(target_pos[i])
        nxt = float(target_pos[i + 1]) if i + 1 < keep_n else float(min(span, st + 1.0))
        dur = max(0.25, min(float(ev[4]), max(0.25, nxt - st)))
        rebuilt.append((2, int(midi), int(ev[2]), float(st), float(dur), [int(midi)]))
    passthrough = [
        ev for ev in events
        if not (
            isinstance(ev, tuple)
            and len(ev) == 6
            and int(ev[0]) == 2
            and id(ev) in replaced_ids
        )
    ]
    plan.melody_events = sorted(list(rebuilt) + list(passthrough), key=lambda e: float(e[3]) if len(e) == 6 else 0.0)


def _apply_bright_chorus_payoff_to_melody(
    plan: SectionPlan,
    blueprint: Optional[Dict[str, Any]],
    *,
    section_role: str,
) -> None:
    """
    Restate the bright chorus hook in the final span when the chorus ending
    carries substantially less lead coverage than the opening statement.
    """
    role = str(section_role or "").strip().lower()
    if role not in {"b", "chorus", "hook"} or not isinstance(blueprint, dict):
        return
    if str(blueprint.get("family", "") or "").strip().lower() != "bright_motor":
        return
    events = list(getattr(plan, "melody_events", []) or [])
    if not events:
        return
    try:
        bars = int(getattr(plan, "bars", 0) or 0)
        bpb = float(getattr(plan, "beats_per_bar", 4.0) or 4.0)
        span_bars = max(1, int(blueprint.get("span_bars", 2) or 2))
    except Exception:
        return
    if bars < span_bars * 2 or bpb <= 1e-9:
        return
    span = float(span_bars) * float(bpb)
    final_start = float(bars - span_bars) * float(bpb)
    if final_start <= span - 1e-6:
        return

    lead = [
        ev for ev in events
        if isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == 2
    ]
    opening = [ev for ev in lead if 0.0 <= float(ev[3]) < span - 1e-6]
    ending = [ev for ev in lead if final_start - 1e-6 <= float(ev[3]) < final_start + span - 1e-6]
    if len(opening) < 3:
        return
    opening_beats = float(sum(max(0.0, float(ev[4])) for ev in opening))
    ending_beats = float(sum(max(0.0, float(ev[4])) for ev in ending))
    # Do not densify a chorus that already sustains its closing answer.
    if ending_beats >= max(1.5, opening_beats * 0.82):
        return

    occupied = {round(float(ev[3]), 6) for ev in ending}
    try:
        register_floor = int(blueprint.get("melody_register_floor", 72) or 72)
    except Exception:
        register_floor = 72
    additions: List[Tuple] = []
    for ev in opening:
        rel = float(ev[3])
        target_start = round(float(final_start) + rel, 6)
        if target_start >= float(bars) * float(bpb) - float(bpb) - 1e-6 or target_start in occupied:
            continue
        try:
            midi = int(ev[5][0]) if isinstance(ev[5], list) and ev[5] else int(ev[1])
        except Exception:
            midi = int(ev[1])
        while midi < register_floor:
            midi += 12
        midi = int(RANGE_LIMITER.clamp_note(int(midi), 2))
        velocity = max(1, min(127, int(ev[2]) + 4))
        additions.append((2, midi, velocity, float(target_start), float(ev[4]), [midi]))
        occupied.add(target_start)
    if additions:
        plan.melody_events = sorted(list(events) + additions, key=lambda e: float(e[3]) if len(e) == 6 else 0.0)

