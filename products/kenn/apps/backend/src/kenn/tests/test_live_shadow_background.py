"""Shadow planning must not add model latency to the user's command."""

import threading
import time

from kenn.core import live_command


def test_shadow_runs_in_the_background_and_logs_the_comparison(monkeypatch) -> None:
    release = threading.Event()
    recorded = []

    def slow_plan(command, snapshot):
        release.wait(5)
        return {"schema": live_command.LLM_PLAN_SCHEMA, "action": "set_mute"}, {"status": "accepted"}

    monkeypatch.setattr(live_command, "_generate_llm_plan", slow_plan)
    monkeypatch.setattr(live_command, "record_shadow_result", recorded.append)
    monkeypatch.delenv("KENN_LIVE_LLM_SHADOW_INLINE", raising=False)
    started = time.monotonic()
    assert live_command._submit_background_shadow("mute the snare", {"tracks": []}, {"action": "set_mute"}, "s1")
    assert time.monotonic() - started < 1.0  # returned before the model finished
    assert recorded == []
    release.set()
    deadline = time.monotonic() + 5
    while not recorded and time.monotonic() < deadline:
        time.sleep(0.02)
    row = recorded[0]
    assert row["llm"]["mode"] == "shadow" and row["llm"]["background"] is True
    assert row["llm"]["plan"]["action"] == "set_mute" and "comparison" in row["llm"]


def test_background_shadow_skips_when_the_backlog_is_full(monkeypatch) -> None:
    monkeypatch.setattr(live_command, "_SHADOW_PENDING", live_command.SHADOW_MAX_PENDING)
    assert live_command._submit_background_shadow("solo the kick", {}, {}, "s1") is False
