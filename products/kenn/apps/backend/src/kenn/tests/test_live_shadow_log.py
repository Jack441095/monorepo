"""Durable evidence logging for observational command plans."""

from __future__ import annotations

import json

from kenn.core.live_shadow_log import record_shadow_result


def test_only_shadow_results_are_persisted(tmp_path) -> None:
    path = tmp_path / "shadow.jsonl"
    assert record_shadow_result({"command": "mute bass", "llm": {"mode": "off"}}, path=path) is False
    assert not path.exists()

    assert record_shadow_result({
        "command": "mute bass",
        "status": "confirmation_required",
        "llm": {
            "mode": "shadow",
            "status": "accepted",
            "plan": {"schema": "kenn.ableton_llm_plan.v1", "action": "set_mute"},
            "comparison": {"status": "match", "deterministic_action": "set_mute", "llm_action": "set_mute"},
        },
        "intent": {"action": "set_mute"},
    }, path=path) is True

    row = json.loads(path.read_text(encoding="utf-8"))
    assert row["schema"] == "kenn.ableton_llm_shadow_log.v1"
    assert row["llm"]["comparison"]["status"] == "match"
    assert row["deterministic_intent"] == {"action": "set_mute"}
    assert path.stat().st_mode & 0o077 == 0
