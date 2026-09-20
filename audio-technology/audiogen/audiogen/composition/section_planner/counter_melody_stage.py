"""Per-section counter-melody generation and thinning (extracted from planner)."""

from __future__ import annotations
from audiogen_core.config import resolve_config

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from audiogen_core.composition_runtime_flags import phrase_length_bars_clamped

from ..harmonic_plan import HarmonicPlan
from ..section_plan import SectionPlan
from .observability import log_degraded

logger = logging.getLogger(__name__)

_CHORUS_ROLES = frozenset({"b", "chorus", "hook", "tag"})
_COUNTER_ROLES = frozenset({"a", "verse", "a_prime", "b", "chorus", "hook", "tag"})


@dataclass(frozen=True)
class CounterMelodyStageResult:
    enabled: bool
    skipped: bool
    strings_mode_blocked: bool
    counter_mode: str
    cm_mult: float
    raw_count: int = 0
    post_script_count: int = 0
    final_count: int = 0
    restored: bool = False


def thin_counter_against_lead(plan: SectionPlan, *, strength: float) -> None:
    """Lower or drop counter hits that overlap the lead in time."""
    s = max(0.0, min(1.0, float(strength)))
    if s <= 1e-6 or not getattr(plan, "counter_events", None) or not getattr(plan, "melody_events", None):
        return
    try:
        lead_spans = []
        for ev in list(plan.melody_events or []):
            if isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == 2:
                st = float(ev[3])
                lead_spans.append((st, st + float(ev[4])))
        if not lead_spans:
            return
        out = []
        for ev in list(plan.counter_events or []):
            if not (isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == 5):
                out.append(ev)
                continue
            ch, midi, vel, st, dur, notes = ev
            e0 = float(st) + float(dur)
            overlap = any(float(st) < le - 1e-6 and e0 > ls + 1e-6 for ls, le in lead_spans)
            if overlap:
                vel = int(max(1, min(127, round(float(vel) * (1.0 - 0.32 * s)))))
                if float(dur) <= 0.5 and s >= 0.72:
                    continue
            out.append((int(ch), midi, int(vel), float(st), float(dur), notes))
        plan.counter_events = out
    except Exception:
        return


def apply_counter_presence_multiplier(
    plan: SectionPlan,
    *,
    role: str,
    multiplier: float,
) -> None:
    """Scale counter event count by arrangement curve mult with chorus floors."""
    m = max(0.0, min(1.0, float(multiplier)))
    events = list(getattr(plan, "counter_events", None) or [])
    if not events:
        return
    if m >= 0.999:
        return
    role_lc = str(role or "").strip().lower()

    typed: List[tuple] = []
    passthrough: List[tuple] = []
    for ev in events:
        if isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == 5:
            typed.append(ev)
        else:
            passthrough.append(ev)
    if not typed:
        return

    if m <= 1e-6:
        plan.counter_events = passthrough
        return

    target_n = int(round(float(len(typed)) * m))
    if role_lc in {"intro"} and m <= 0.18:
        target_n = 0
    elif role_lc in _CHORUS_ROLES and m >= 0.18:
        target_n = max(4, target_n)
    elif role_lc in _CHORUS_ROLES and m >= 0.12:
        target_n = max(3, target_n)
    elif m < 0.35:
        target_n = max(1, target_n)
    else:
        target_n = max(2, target_n)
    target_n = max(0, min(len(typed), int(target_n)))
    if target_n >= len(typed):
        scaled = typed
    elif target_n <= 0:
        scaled = []
    else:
        keep_idx = {
            int(round(i * float(len(typed) - 1) / float(max(1, target_n - 1))))
            for i in range(target_n)
        }
        scaled = []
        for idx, ev in enumerate(typed):
            if idx not in keep_idx:
                continue
            ch, midi, vel, st, dur, notes = ev
            vel_scale = 0.76 + 0.24 * float(m)
            scaled.append(
                (
                    int(ch),
                    midi,
                    int(max(1, min(127, round(float(vel) * vel_scale)))),
                    float(st),
                    float(dur),
                    notes,
                )
            )
    plan.counter_events = sorted(
        list(passthrough) + list(scaled),
        key=lambda e: float(e[3]) if isinstance(e, tuple) and len(e) == 6 else 0.0,
    )


def _load_counter_config() -> Dict[str, Any]:
    c = resolve_config("composition", "", None)
    return {
        "enabled": bool(getattr(c, "counter_melody_enabled", True)) if c is not None else True,
        "counter_mode": str(getattr(c, "counter_melody_mode", "counter") or "counter").strip().lower() if c is not None else "counter",
        "strings_harmony_enabled": bool(getattr(c, "strings_harmony_enabled", False)) if c is not None else False,
        "strings_hold_beats": float(getattr(c, "strings_harmony_hold_beats", 3.5) or 3.5) if c is not None else 3.5,
        "strings_velocity_scale": float(getattr(c, "strings_harmony_velocity_scale", 0.92) or 0.92) if c is not None else 0.92,
        "script_on": bool(getattr(c, "countermelody_script_enabled", True)) if c is not None else True,
        "script_strength": float(getattr(c, "countermelody_script_strength", 0.72) or 0.72) if c is not None else 0.72,
        "follow_counter": float(getattr(c, "counter_melody_follow_lead_strength", 0.55) or 0.55) if c is not None else 0.55,
        "bus_enabled": bool(getattr(c, "cross_lane_motif_bus_enabled", True)) if c is not None else True,
        "octave_offset": int(getattr(c, "counter_melody_octave_offset", 0) or 0) if c is not None else 0,
    }
def _resolve_motif_rhythms(owner: Any, *, bus_enabled: bool) -> Optional[List[Any]]:
    try:
        hook = owner.motif_plan.theme() if hasattr(owner, "motif_plan") else None
        rhythms = list(getattr(hook, "rhythms", []) or []) if hook is not None else None
        if rhythms:
            return rhythms
    except Exception:
        pass
    if not bus_enabled:
        return None
    try:
        bus = getattr(owner, "_cross_lane_motif_bus", None)
        if isinstance(bus, dict):
            return list(bus.get("rhythms", []) or []) or None
    except Exception:
        pass
    return None


def _filter_counter_by_phrase_roles(
    events: List[Tuple],
    *,
    owner: Any,
    plan: SectionPlan,
    phrase_roles: List[Any],
    cad_win2: List[Any],
) -> List[Tuple]:
    bpb2 = float(getattr(plan, "beats_per_bar", 4.0) or 4.0)
    bars2 = int(getattr(plan, "bars", 0) or 0)
    if bars2 <= 0 or bpb2 <= 1e-9:
        return list(events or [])

    lead_counts = [0 for _ in range(int(bars2))]
    for ev in list(plan.melody_events or []):
        try:
            if not (isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == 2):
                continue
            bar = int(float(ev[3]) // float(bpb2))
            if 0 <= bar < int(bars2):
                lead_counts[bar] += 1
        except Exception:
            continue

    def _phrase_role_for_bar(bi: int) -> str:
        if 0 <= int(bi) < len(phrase_roles):
            try:
                return str(phrase_roles[int(bi)] or "")
            except Exception:
                return ""
        try:
            phrase_len = phrase_length_bars_clamped(1, 16)
            return owner.chord_utils.phrase_role(int(bi), int(bars2), phrase_length=int(phrase_len))
        except Exception:
            return ""

    filtered: List[Tuple] = []
    for ev in list(events or []):
        try:
            if not (isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == 5):
                filtered.append(ev)
                continue
            st = float(ev[3])
            bar = int(st // float(bpb2))
            if bar < 0 or bar >= int(bars2):
                continue
            if 0 <= int(bar) < len(cad_win2) and float(cad_win2[int(bar)]) >= 0.95:
                continue
            pr = str(_phrase_role_for_bar(int(bar)) or "").strip().lower()
            if pr in {"cadence", "opening"}:
                continue
            if pr in {"answer"} and int(lead_counts[bar]) > 1:
                continue
            filtered.append(ev)
        except Exception:
            filtered.append(ev)
    return filtered


def _restore_minimal_counter(
    raw_counter_events: List[Tuple],
    *,
    section_role: str,
    cm_mult: float,
) -> List[Tuple]:
    role_lc = str(section_role or "").strip().lower()
    if role_lc in _CHORUS_ROLES and float(cm_mult) >= 0.18:
        keep_n = 4
    elif role_lc in _CHORUS_ROLES and float(cm_mult) >= 0.12:
        keep_n = 3
    else:
        keep_n = 2 if float(cm_mult) >= 0.18 else 1
    restored: List[Tuple] = []
    for ev in list(raw_counter_events):
        if not (isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == 5):
            continue
        ch, midi, vel, st, dur, notes = ev
        restored.append(
            (
                int(ch),
                int(midi),
                int(max(1, min(127, round(float(vel) * 0.62)))),
                float(st),
                float(dur),
                list(notes),
            )
        )
        if len(restored) >= int(keep_n):
            break
    return restored


def run_counter_melody_stage(
    owner: Any,
    plan: SectionPlan,
    *,
    curve: Dict[str, Any],
    section_role: str,
    section_index: int,
) -> CounterMelodyStageResult:
    """Generate, script, thin, and scale counter-melody for one section plan."""
    plan.counter_events = []
    cfg = _load_counter_config()
    counter_mode = str(cfg["counter_mode"])
    strings_mode_blocked = False
    enabled = bool(cfg["enabled"])
    if counter_mode in {"strings", "strings_harmony", "harmony_strings"} and not bool(cfg["strings_harmony_enabled"]):
        enabled = False
        strings_mode_blocked = True

    try:
        cm_mult = float(curve.get("counter_melody_enabled_mult", 1.0) or 1.0)
    except Exception:
        cm_mult = 1.0
    enabled = bool(enabled and float(cm_mult) > 1e-9)

    if not enabled:
        logger.debug(
            "counter_melody skipped: role=%r cm_mult=%.3f mode=%r strings_mode_blocked=%s",
            section_role,
            float(cm_mult),
            counter_mode,
            strings_mode_blocked,
        )
        return CounterMelodyStageResult(
            enabled=False,
            skipped=True,
            strings_mode_blocked=strings_mode_blocked,
            counter_mode=counter_mode,
            cm_mult=float(cm_mult),
        )

    raw_n = 0
    post_script_n = 0
    restored = False
    try:
        from composition.counter_melody import (
            apply_countermelody_script,
            generate_counter_melody_events_from_harmonic_plan,
        )

        cad_win = list((plan.timeline_targets or {}).get("cadence_window", []) or [])
        motif_slots = list(getattr(plan, "_motif_slot_tags", []) or [])
        motif_rhythms = _resolve_motif_rhythms(owner, bus_enabled=bool(cfg["bus_enabled"]))
        from composition.counter_melody import CounterMelodyConfig
        hp = getattr(plan, "harmonic_plan", None) or HarmonicPlan.from_section_plan(plan)
        plan.counter_events = generate_counter_melody_events_from_harmonic_plan(
            hp,
            emotion=plan.emotion,
            cadence_window=list(cad_win),
            lead_events=list(plan.melody_events or []),
            motif_slots=list(motif_slots or []),
            motif_rhythms=(list(motif_rhythms) if motif_rhythms else None),
            mode=str(counter_mode),
            strings_hold_beats=float(cfg["strings_hold_beats"]),
            strings_velocity_scale=float(cfg["strings_velocity_scale"]),
            cfg=CounterMelodyConfig(
                channel=5,
                octave_offset=int(cfg.get("octave_offset", 0)),
            )
        )
        raw_n = len(plan.counter_events or [])
        raw_counter_events = list(plan.counter_events or [])

        bpb2 = float(getattr(plan, "beats_per_bar", 4.0) or 4.0)
        bars2 = int(getattr(plan, "bars", 0) or 0)
        phrase_roles = list((plan.timeline_targets or {}).get("phrase_role_by_bar", []) or [])
        cad_win2 = list((plan.timeline_targets or {}).get("cadence_window", []) or [])
        tex2 = list(getattr(plan, "texture_by_bar", []) or [])

        if (
            plan.counter_events
            and bars2 > 0
            and bpb2 > 1e-9
            and bool(cfg["script_on"])
            and counter_mode not in {"strings", "strings_harmony", "harmony_strings"}
        ):
            try:
                plan.counter_events = apply_countermelody_script(
                    list(plan.counter_events or []),
                    bars=int(bars2),
                    beats_per_bar=float(bpb2),
                    section_role=section_role,
                    next_role=str(getattr(owner, "_next_section_role_hint", "") or ""),
                    lead_events=list(plan.melody_events or []),
                    phrase_roles=list(phrase_roles or []),
                    cadence_window=list(cad_win2 or []),
                    texture_by_bar=list(tex2 or []),
                    strength=float(cfg["script_strength"]),
                )
            except Exception:
                pass
        elif plan.counter_events and bars2 > 0 and bpb2 > 1e-9:
            plan.counter_events = _filter_counter_by_phrase_roles(
                list(plan.counter_events or []),
                owner=owner,
                plan=plan,
                phrase_roles=phrase_roles,
                cad_win2=cad_win2,
            )

        post_script_n = len(plan.counter_events or [])
        thin_counter_against_lead(plan, strength=float(cfg["follow_counter"]))
        apply_counter_presence_multiplier(plan, role=str(section_role), multiplier=float(cm_mult))

        role_lc = str(section_role or "").strip().lower()
        if (
            not list(plan.counter_events or [])
            and raw_counter_events
            and float(cm_mult) >= 0.08
            and role_lc in _COUNTER_ROLES
        ):
            plan.counter_events = _restore_minimal_counter(
                raw_counter_events,
                section_role=str(section_role),
                cm_mult=float(cm_mult),
            )
            restored = bool(plan.counter_events)

        logger.debug(
            "counter_melody: role=%s cm_mult=%.3f mode=%s raw=%d post_script=%d final=%d restored=%s",
            section_role,
            float(cm_mult),
            counter_mode,
            int(raw_n),
            int(post_script_n),
            len(plan.counter_events or []),
            restored,
        )
    except Exception as exc:
        log_degraded(
            "counter_melody_generation",
            exc,
            section_index=int(section_index),
            section_role=str(section_role),
        )
        plan.counter_events = []
        return CounterMelodyStageResult(
            enabled=True,
            skipped=True,
            strings_mode_blocked=strings_mode_blocked,
            counter_mode=counter_mode,
            cm_mult=float(cm_mult),
            raw_count=int(raw_n),
            post_script_count=int(post_script_n),
            final_count=0,
            restored=False,
        )

    final_n = len(plan.counter_events or [])
    return CounterMelodyStageResult(
        enabled=True,
        skipped=False,
        strings_mode_blocked=strings_mode_blocked,
        counter_mode=counter_mode,
        cm_mult=float(cm_mult),
        raw_count=int(raw_n),
        post_script_count=int(post_script_n),
        final_count=int(final_n),
        restored=restored,
    )