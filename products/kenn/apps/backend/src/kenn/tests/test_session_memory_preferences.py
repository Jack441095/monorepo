from __future__ import annotations

from kenn.core.session_memory import infer_preferences


def test_creative_direction_preference_pattern_supports_supported_python_runtimes() -> None:
    assert infer_preferences("I'm aiming for warm and intimate")["creative_direction"] == "warm and intimate"
