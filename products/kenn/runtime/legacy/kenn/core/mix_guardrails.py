"""Deterministic pre-execution mix guardrails (item 2,
docs/KENN_WEEKLY_OPTIMIZATION_PLAN_2026-08-08.md).

Distinct from parameter clamping (already existed before this file --
every OSC write already clamps its own value to a safe range, see
ableton_osc_bridge.py's set_track_volume/set_track_pan/set_tempo). This
is about the *combined effect* of a write given the track's current
measured state, not just whether the raw input number itself is in
range -- e.g. a volume value of 0.9 is perfectly in-range on its own,
but pushing it there on a track whose output is already reading near
the ceiling is a different kind of risk clamping alone can't catch.

Deliberately conservative on precision: Track.output_meter_level and
mixer_device.volume share the same documented 0.0-1.0 Live Object Model
scale, so comparing them directly is valid -- but neither this module
nor the rest of this codebase has a verified formula for Ableton's
exact fader-to-dBFS curve, so these rules reason in that shared linear
scale rather than asserting a specific dB number nothing here can back
up. Ship the rule that's honestly calibrated over one that sounds more
precise than it is.
"""

from __future__ import annotations

NEAR_CEILING_METER_THRESHOLD = 0.9


def volume_increase_risks_clipping(
    *,
    current_meter_level: float | None,
    requested_volume: float,
    current_volume: float | None,
) -> tuple[bool, str]:
    """Returns (risky, warning).

    Advisory, not a block: the write still executes either way (see
    tool_set_ableton_volume in autonomous_agent.py) -- this only flags a
    volume INCREASE on a track whose most recently measured output level
    is already near the ceiling, matching this codebase's established
    "inform, don't block" philosophy for judgment calls (Mixing Doctor's
    alerts work the same way: surfaced with a suggested fix, never
    auto-applied or hard-blocked). A decrease, or a request at/below the
    current volume, is never flagged even at a high meter reading --
    only a further increase adds clipping risk.

    current_meter_level of None (no live meter reading available yet --
    e.g. the session just connected, or this Ableton hasn't been
    restarted to pick up the meter fields yet) is never flagged: absence
    of evidence isn't a reason to warn, the same "don't fail closed on
    missing optional data" principle every other optional LOM field in
    this codebase already follows.
    """
    if current_meter_level is None:
        return False, ""
    if current_volume is not None and requested_volume <= current_volume:
        return False, ""
    if current_meter_level >= NEAR_CEILING_METER_THRESHOLD:
        return True, (
            f"Heads up: this track's current output level "
            f"({current_meter_level:.2f} on Ableton's 0.0-1.0 meter scale) was "
            "already near the ceiling before this change -- the increase may "
            "clip. Worth a listen."
        )
    return False, ""
