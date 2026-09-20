"""Contract tests for machine-readable local command planning."""

from __future__ import annotations

from kenn.llm.llm_rewrite import _build_payload


def test_command_json_payload_is_deterministic_and_bounded() -> None:
    payload = _build_payload(
        {"model": "local-test"},
        [{"role": "user", "content": "mute track 2"}],
        answer_mode="command",
        json_mode=True,
    )

    assert payload["response_format"] == {"type": "json_object"}
    assert payload["temperature"] == 0.0
    assert payload["max_tokens"] == 256
