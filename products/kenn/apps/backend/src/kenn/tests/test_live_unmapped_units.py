"""A clear request KENN can't do yet gets the specific reason, not "I'm not sure what you're asking"."""

from __future__ import annotations

import pytest

from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_action_service import LiveActionService
from kenn.core.live_command import handle_command


@pytest.fixture()
def say(monkeypatch, tmp_path):
    from kenn.core import live_receipt_journal

    monkeypatch.setattr(live_receipt_journal, "JOURNAL_PATH", tmp_path / "receipts.jsonl")
    monkeypatch.setenv("KENN_ALLOW_DAW_CONTROL", "1")
    for name in ("KENN_LIVE_LLM_ENABLED", "KENN_LLM_ENABLED", "KENN_LLM_ENABLED_COMMAND"):
        monkeypatch.delenv(name, raising=False)
    service = LiveActionService(FakeLiveBackend())
    return lambda command: handle_command(command, session_id=f"units-{tmp_path.name}", service=service)


@pytest.mark.parametrize("command, reason", [
    ("set the compressor attack on the drum bus to 10 ms", "I can't set Compressor Attack to 10 ms yet"),
    ("set the compressor ratio on the drum bus to 4:1", "I can't set Compressor Ratio to 4:1 yet"),
    ("set the threshold on the kick to -20 dB", "I couldn't find that device on the track"),
])
def test_the_specific_reason_reaches_the_producer(say, command, reason) -> None:
    result = say(command)
    assert result["status"] == "clarification_required" and result["changed"] is False
    assert result["answer"].startswith(reason)
