""""Undo that" twice walks back through changes; it never undoes the undo."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_action_service import LiveActionService
from kenn.core.live_command import handle_command
from kenn.core.live_receipt_journal import record_receipt
from kenn.core.session_context import undo_target


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

    def propose(text: str) -> dict:
        proposal = handle_command(text, session_id=session, service=service).get("proposal") or {}
        assert proposal.get("confirmation_token"), text
        return proposal

    def apply(text: str, proposal: dict) -> dict:
        applied = handle_command(text, session_id=session, service=service, proposal=proposal,
                                 confirm_token=proposal["confirmation_token"], idempotency_key=proposal.get("action_id"))
        record_receipt(applied["receipt"], session_id=session)
        return applied

    def do(text: str) -> dict:
        return apply(text, propose(text))

    def volume(name: str) -> float:
        return next(t["volume"] for t in service.snapshot()["tracks"] if t["name"] == name)

    return SimpleNamespace(
        do=do, propose=propose, apply=apply, volume=volume, fake=fake, service=service, session=session,
        ask_undo=lambda: handle_command("Undo that", session_id=session, service=service),
    )


def test_two_undos_undo_two_changes(kenn) -> None:
    do, volume = kenn.do, kenn.volume
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
    kenn.do("Set the synth to -4 dB")
    kenn.do("Undo that")
    assert "don't have a verified change" in kenn.ask_undo()["answer"]


def test_undo_after_a_rolled_back_recipe_undoes_the_change_before_it(kenn) -> None:
    # Regression (8 Oct 2026 recipe requal): a stale recipe card failed and rolled back cleanly, then
    # "Undo that" picked the failed receipt and refused, so the producer's real change could not be undone.
    vocal = next(t["index"] for t in kenn.service.snapshot()["tracks"] if t["name"] == "Lead Vocal")
    stale_card = kenn.propose("Give the vocal some space")
    kenn.do("Set the delay send on the lead vocal to 40%")
    failed = kenn.apply("Give the vocal some space", stale_card)
    # Step 1 (the A-Reverb send) was written before step 2 found its send moved, then put back.
    assert failed["receipt"]["status"] == "failed_rolled_back"
    assert failed["receipt"]["step_count"] == 1
    kenn.do("Undo that")
    # The undo reached the producer's 40 % delay send and took it back to where the set started.
    assert kenn.fake.get_track_send(vocal, 1) == pytest.approx(0.0, abs=1e-4)


@pytest.mark.parametrize("status", ["partial_recovery", "failed"])
def test_an_unverified_failure_still_stops_undo_from_reaching_past_it(kenn, status) -> None:
    # Only a verified clean rollback is skipped. These two may have left a change we could not read back,
    # and undoing something older underneath it would leave the set wrong in two places.
    older = {"receipt_id": "receipt-older", "status": "applied", "verified": True}
    failure = {"receipt_id": "receipt-failed", "status": status, "verified": False}
    assert undo_target(kenn.session, [failure, older]) is failure
