"""Section-role harmony pacing policy.

This module keeps the "how fast should harmony move here?" decision in one
place.  Chord choice still lives in ``ChordPlanner``; this policy only shapes
motion density and protected bars for section roles.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Set


@dataclass(frozen=True)
class HarmonyPacingPlan:
    role: str
    bars: int
    motion_multiplier: float
    min_change_spacing: int
    protected_hold_bars: Set[int]
    cadence_bars: Set[int]
    surprise_bars: Set[int]

    def should_protect_hold(self, bar_index: int) -> bool:
        return int(bar_index) in self.protected_hold_bars

    def is_cadence_bar(self, bar_index: int) -> bool:
        return int(bar_index) in self.cadence_bars

    def is_surprise_bar(self, bar_index: int) -> bool:
        return int(bar_index) in self.surprise_bars


def harmony_pacing_for_section(
    section_role: Optional[str],
    bars: int,
    *,
    next_role: Optional[str] = None,
) -> HarmonyPacingPlan:
    """Return a deterministic harmony pacing plan for a section role."""

    role = str(section_role or "").strip().lower()
    nxt = str(next_role or "").strip().lower()
    n = max(1, int(bars))
    cadence = {max(0, n - 1)}
    if n >= 4:
        cadence.add(max(0, n - 2))

    protected: Set[int] = set()
    surprise: Set[int] = set()
    motion = 1.0
    spacing = 1

    if role in {"intro"}:
        motion = 0.72
        spacing = 2
        protected.update(range(1, min(n, 3)))
    elif role in {"a", "verse"}:
        motion = 0.82
        spacing = 2
        protected.update(range(1, min(n, 2)))
    elif role == "pre_chorus":
        motion = 1.24
        spacing = 1
    elif role in {"b", "chorus", "hook"}:
        motion = 0.92
        spacing = 2
        protected.update(range(1, min(n, 2)))
    elif role in {"a_prime", "bridge"}:
        motion = 1.10
        spacing = 1
        if n >= 6:
            surprise.add(max(1, min(n - 2, n // 2)))
    elif role == "tag":
        motion = 0.86
        spacing = 2
        protected.update(range(1, min(n, 2)))
    elif role in {"outro", "ending"}:
        motion = 0.68
        spacing = 2
        if n >= 3:
            protected.update(range(max(1, n - 2), n))

    if role == "pre_chorus" and nxt in {"b", "chorus", "hook"}:
        motion = max(float(motion), 1.32)
    if role in {"b", "chorus", "hook", "tag"} and nxt in {"a", "verse"}:
        cadence.add(max(0, n - 1))

    return HarmonyPacingPlan(
        role=role,
        bars=n,
        motion_multiplier=float(max(0.45, min(1.65, motion))),
        min_change_spacing=max(1, int(spacing)),
        protected_hold_bars={int(x) for x in protected if 0 <= int(x) < n},
        cadence_bars={int(x) for x in cadence if 0 <= int(x) < n},
        surprise_bars={int(x) for x in surprise if 0 <= int(x) < n},
    )


def apply_harmony_pacing_to_tokens(tokens: List[str], plan: HarmonyPacingPlan) -> List[str]:
    """Apply role pacing to simplified chord tokens.

    This is deliberately conservative: it never rewrites bar 0, cadence bars, or
    surprise bars.  It only extends the previous token when a section role asks
    for static harmony or wider spacing between changes.
    """

    out = [str(x) for x in list(tokens or [])]
    if len(out) <= 1:
        return out

    last_change = 0
    for i in range(1, min(len(out), int(plan.bars))):
        if plan.is_cadence_bar(i) or plan.is_surprise_bar(i):
            if out[i] != out[i - 1]:
                last_change = i
            continue
        if plan.should_protect_hold(i):
            out[i] = out[i - 1]
            continue
        if out[i] != out[i - 1]:
            if i - last_change < int(plan.min_change_spacing):
                out[i] = out[i - 1]
            else:
                last_change = i
    return out
