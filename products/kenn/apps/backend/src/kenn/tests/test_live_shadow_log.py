"""Durable evidence logging for observational command plans."""

from __future__ import annotations

import json
from pathlib import Path

from kenn.core import live_shadow_log
from kenn.core.live_shadow_log import record_shadow_result


def test_suite_default_shadow_log_is_isolated_from_runtime_evidence() -> None:
    runtime_default = Path(live_shadow_log.__file__).resolve().parents[1] / "data" / "live_llm_shadow.jsonl"

    assert live_shadow_log.SHADOW_LOG_PATH != runtime_default
    assert Path(live_shadow_log.SHADOW_LOG_PATH).name == "live_llm_shadow.jsonl"


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
