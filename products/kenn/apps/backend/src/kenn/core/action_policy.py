"""Explicit opt-in policy for actions that leave the local application boundary.

Ported into this standalone repository (not a live dependency on the old
NITE DSP platform): pure stdlib, environment-variable-gated safety checks.
"""

from __future__ import annotations

import os

ACTION_FLAGS = {
    "external_email": "AUDIO_TOO_ALLOW_EXTERNAL_EMAIL",
    "desktop_automation": "AUDIO_TOO_ALLOW_DESKTOP_AUTOMATION",
    "daw_control": "AUDIO_TOO_ALLOW_DAW_CONTROL",
    "daw_control": "KENN_ALLOW_DAW_CONTROL",
    "audio_capture": "AUDIO_TOO_ALLOW_AUDIO_CAPTURE",
    "autonomous_mode": "KENN_AUTONOMOUS_MODE",
}

# Backward compatibility alias
_LEGACY_DAW_CONTROL_FLAG = "AUDIO_TOO_ALLOW_DAW_CONTROL"


def action_allowed(action: str) -> bool:
    variable = ACTION_FLAGS.get(action)
    if not variable:
        return False
    val = os.getenv(variable, "").strip().lower()
    if val in {"1", "true", "yes", "on"}:
        return True
    if action == "daw_control":
        legacy_val = os.getenv(_LEGACY_DAW_CONTROL_FLAG, "").strip().lower()
        return legacy_val in {"1", "true", "yes", "on"}
    return False


def action_denied_message(action: str) -> str:
    variable = ACTION_FLAGS.get(action, "an explicit allow flag")
    return f"Action disabled by policy. Set {variable}=1 only after reviewing the security boundary."


class AutonomousSafetyEvaluator:
    """Evaluates whether a proposed DAW action is within the safe autonomous envelope."""

    MAX_GAIN_DELTA_NORMALIZED = 0.20  # Approx ~3.0 dB delta in Ableton's tapered fader curve
    FORBIDDEN_TRACK_NAMES = frozenset({"master", "main"})
    FORBIDDEN_ACTIONS = frozenset({"delete_track", "delete_device", "delete_clip", "delete_scene"})

    @classmethod
    def is_autonomous_mode_enabled(cls) -> bool:
        return action_allowed("autonomous_mode") or os.getenv("KENN_AUTONOMOUS_MODE", "").strip().lower() in {"1", "true", "yes", "on"}

    @classmethod
    def evaluate_proposal(
        cls,
        action: str,
        *,
        current_value: float | None = None,
        target_value: float | None = None,
        track_name: str | None = None,
        is_master: bool = False,
    ) -> tuple[bool, str]:
        """Verify action is mathematically bounded, non-destructive, and not mutating master."""
        if action in cls.FORBIDDEN_ACTIONS:
            return False, f"Destructive action '{action}' is strictly prohibited in autonomous mode."

        if is_master or (track_name and track_name.lower().strip() in cls.FORBIDDEN_TRACK_NAMES):
            if action in {"set_volume", "set_mute", "set_solo"}:
                return False, "Mutating master track volume/mute/solo is prohibited in autonomous mode."

        if action == "set_volume" and current_value is not None and target_value is not None:
            delta = abs(target_value - current_value)
            if delta > cls.MAX_GAIN_DELTA_NORMALIZED:
                return False, f"Volume delta {delta:.3f} exceeds maximum autonomous threshold {cls.MAX_GAIN_DELTA_NORMALIZED:.3f} (~3.0 dB)."

        return True, "Action approved within autonomous safety envelope."
