"""Chorus hook memory capture/apply across song sections."""

from __future__ import annotations
from audiogen_core.config import resolve_config

from typing import Any

from midi.midi_range_limiter import RANGE_LIMITER

from ..section_plan import SectionPlan
from .chorus_hook_blueprint import chorus_hook_emotion_key_from_plan
from .final_chorus_payoff import resolve_final_chorus_payoff_state

def capture_chorus_hook_memory(owner: Any, plan: SectionPlan, *, section_role: str, section_index: int) -> None:
    role = str(section_role or "").strip().lower()
    if role not in {"a", "verse", "pre_chorus", "b", "chorus", "hook"}:
        return
    emo_key = chorus_hook_emotion_key_from_plan(plan) or "neutral"
    by = getattr(owner, "_chorus_hook_memory_by_emotion", None)
    if not isinstance(by, dict):
        by = {}
        try:
            setattr(owner, "_chorus_hook_memory_by_emotion", by)
        except Exception:
            pass
    if not resolve_config("composition", "whole_song_chorus_hook_memory_enabled", True, bool):
        return
    try:
        seq = owner.arrangement_policy._FORM_SEQUENCES.get(owner.arrangement_policy.form_mode) or owner.arrangement_policy._FORM_SEQUENCES["default"]
        first_chorus = next(i for i, r in enumerate(seq) if str(r).strip().lower() in {"b", "chorus", "hook"})
    except Exception:
        first_chorus = int(section_index)
    provisional_role = role in {"a", "verse", "pre_chorus"} and int(section_index) < int(first_chorus)
    if not provisional_role and int(section_index) != int(first_chorus):
        return
    existing = by.get(emo_key) if isinstance(by, dict) else None
    if isinstance(existing, dict):
        existing_role = str(existing.get("source_role") or "").strip().lower()
        if provisional_role:
            return
        if existing_role in {"b", "chorus", "hook"}:
            return
    bpb = float(getattr(plan, "beats_per_bar", 4.0) or 4.0)
    span = min(float(bpb) * 2.0, float(getattr(plan, "bars", 1) or 1) * float(bpb))
    rows = []
    root = int(getattr(plan, "root_note", 60) or 60)
    for ev in sorted(list(getattr(plan, "melody_events", []) or []), key=lambda e: float(e[3]) if len(e) == 6 else 0.0):
        if not (isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == 2):
            continue
        st = float(ev[3])
        if st < -1e-6 or st >= span - 1e-6:
            continue
        try:
            midi = int(ev[5][0]) if isinstance(ev[5], list) and ev[5] else int(ev[1])
        except Exception:
            continue
        dur = max(0.125, min(float(ev[4]), span - st))
        rows.append(
            {
                "start": float(st),
                "dur": float(dur),
                "root_offset": int(midi) - int(root),
                "velocity": int(max(1, min(127, int(ev[2])))),
            }
        )
        if len(rows) >= 10:
            break
    if len(rows) >= 3:
        mem = {"emotion_key": str(emo_key), "span": float(span), "events": list(rows), "source_role": str(role)}
        try:
            if isinstance(by, dict):
                by[str(emo_key)] = mem
        except Exception:
            pass
        setattr(owner, "_chorus_hook_memory", mem)
        try:
            sm = getattr(owner, "song_memory", None)
            if sm is not None and hasattr(sm, "remember_chorus_hook"):
                sm.remember_chorus_hook(mem)
        except Exception:
            pass

def apply_chorus_hook_memory(owner: Any, plan: SectionPlan, *, section_role: str, section_index: int) -> None:
    role = str(section_role or "").strip().lower()
    if role not in {"b", "chorus", "hook", "tag"}:
        return
    emo_key = chorus_hook_emotion_key_from_plan(plan) or "neutral"
    mem = None
    by = getattr(owner, "_chorus_hook_memory_by_emotion", None)
    if isinstance(by, dict) and emo_key in by:
        mem = by.get(emo_key)
    if not isinstance(mem, dict):
        legacy = getattr(owner, "_chorus_hook_memory", None)
        if isinstance(legacy, dict):
            leg_em = str(legacy.get("emotion_key") or "").strip().lower()
            if not leg_em or leg_em == emo_key:
                mem = legacy
    if not isinstance(mem, dict):
        try:
            sm = getattr(owner, "song_memory", None)
            rows = list(getattr(sm, "chorus_hook_events", []) or [])
            span = float(getattr(sm, "chorus_hook_span", 0.0) or 0.0)
            sm_key = str(getattr(sm, "chorus_hook_emotion_key", "") or "").strip().lower()
            if rows and span > 1e-6 and sm_key == emo_key:
                mem = {"emotion_key": emo_key, "span": span, "events": rows}
            else:
                return
        except Exception:
            return
    if not resolve_config("composition", "whole_song_chorus_hook_memory_enabled", True, bool):
        return
    strength = resolve_config("composition", "whole_song_chorus_hook_memory_strength", 0.68, float)
    s = max(0.0, min(1.0, float(strength)))
    if s <= 1e-6:
        return
    try:
        seq = owner.arrangement_policy._FORM_SEQUENCES.get(owner.arrangement_policy.form_mode) or owner.arrangement_policy._FORM_SEQUENCES["default"]
        first_chorus = next(i for i, r in enumerate(seq) if str(r).strip().lower() in {"b", "chorus", "hook"})
    except Exception:
        first_chorus = 0
    source_role = str(mem.get("source_role") or "").strip().lower()
    if source_role in {"b", "chorus", "hook"}:
        if int(section_index) <= int(first_chorus):
            return
    else:
        if int(section_index) < int(first_chorus):
            return
        if role not in {"b", "chorus", "hook"}:
            return
        if int(section_index) > int(first_chorus):
            return
    events = list(mem.get("events", []) or [])
    if len(events) < 3:
        return
    if source_role in {"a", "verse"}:
        keep_n = max(3, min(5, len(events)))
    elif source_role == "pre_chorus":
        keep_n = max(3, min(6, len(events)))
    else:
        keep_n = max(3, int(round(len(events) * (0.45 + 0.55 * s))))
    span = float(mem.get("span", 8.0) or 8.0)
    span = max(1.0, min(float(span), float(getattr(plan, "bars", 1) or 1) * float(getattr(plan, "beats_per_bar", 4.0) or 4.0)))
    root = int(getattr(plan, "root_note", 60) or 60)
    lift = 0
    try:
        payoff = resolve_final_chorus_payoff_state(
            owner,
            role=str(role),
            section_index=int(section_index),
            form_section_count=int(owner.arrangement_policy.form_section_count()),
        )
        if bool(payoff.get("is_final_chorus", False)):
            lift = 5
        elif role == "tag":
            lift = 2
    except Exception:
        lift = 0

    rebuilt = []
    for row in events[:keep_n]:
        try:
            st = float(row.get("start", 0.0))
            dur = float(row.get("dur", 0.5))
            midi = int(root) + int(row.get("root_offset", 0)) + int(lift)
            midi = int(RANGE_LIMITER.clamp_note(int(midi), 2))
            vel = int(max(1, min(127, round(float(row.get("velocity", 92)) * (1.0 + 0.08 * s)))))
        except Exception:
            continue
        if st < span - 1e-6:
            rebuilt.append((2, int(midi), int(vel), float(st), float(max(0.125, dur)), [int(midi)]))
    if len(rebuilt) < 3:
        return
    original = [
        ev for ev in list(getattr(plan, "melody_events", []) or [])
        if not (isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == 2 and float(ev[3]) < span - 1e-6)
    ]
    plan.melody_events = sorted(list(rebuilt) + original, key=lambda e: float(e[3]) if len(e) == 6 else 0.0)