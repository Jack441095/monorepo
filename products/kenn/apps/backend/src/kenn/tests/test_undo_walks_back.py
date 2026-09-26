""""Undo that" twice walks back through changes; it never undoes the undo."""

from __future__ import annotations

import pytest

from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_action_service import LiveActionService
from kenn.core.live_command import handle_command
from kenn.core.live_receipt_journal import record_receipt


@pytest.fixture()
def kenn(monkeypatch, tmp_path):
    from kenn.core import live_receipt_journal

    monkeypatch.setattr(live_receipt_journal, "JOURNAL_PATH", tmp_path / "receipts.jsonl")
    monkeypatch.setenv("KENN_ALLOW_DAW_CONTROL", "1")
    for name in ("KENN_LIVE_LLM_ENABLED", "KENN_LLM_ENABLED", "KENN_LLM_ENABLED_COMMAND"):
        monkeypatch.delenv(name, raising=False)
    fake = FakeLiveBackend()
    service = LiveActionService(fake)
    session = f"undo-{tmp_path.name}"

    def do(text: str) -> dict:
        proposal = handle_command(text, session_id=session, service=service).get("proposal") or {}
        assert proposal.get("confirmation_token"), text
        applied = handle_command(text, session_id=session, service=service, proposal=proposal,
                                 confirm_token=proposal["confirmation_token"], idempotency_key=proposal.get("action_id"))
        record_receipt(applied["receipt"], session_id=session)
        return applied

    def volume(name: str) -> float:
        return next(t["volume"] for t in service.snapshot()["tracks"] if t["name"] == name)

    return do, volume, lambda: handle_command("Undo that", session_id=session, service=service)


def test_two_undos_undo_two_changes(kenn) -> None:
    do, volume, _ask_undo = kenn
    start = volume("Synth")
    do("Set the synth to -4 dB")
    after_first = volume("Synth")
    do("Turn the synth down 2 dB")
    do("Undo that")
    assert volume("Synth") == pytest.approx(after_first, abs=1e-4)
    # Regression (26 Sept): the second undo reversed the first undo instead of the change before it.
    do("Undo that")
    assert volume("Synth") == pytest.approx(start, abs=1e-4)


def test_nothing_left_to_undo_says_so(kenn) -> None:
    do, _volume, ask_undo = kenn
    do("Set the synth to -4 dB")
    do("Undo that")
    assert "don't have a verified change" in ask_undo()["answer"]
