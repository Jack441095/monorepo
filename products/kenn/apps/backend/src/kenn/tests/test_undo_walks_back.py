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


def test_undo_walks_past_a_card_refused_before_it_wrote_anything(kenn) -> None:
    # Regression (9 Oct 2026, L3 requal follow-up): a stale device card refused at Apply wrote a plain "failed"
    # receipt, and "Undo that" stopped on it even though Live was never touched.
    stale_card = kenn.propose("set the Drum Bus compressor threshold to -20 dB")
    start = kenn.volume("Synth")
    kenn.do("Set the synth to -4 dB")
    kenn.fake.set_device_parameter(stale_card["track_index"], stale_card["device_index"],
                                   stale_card["parameter_index"], float(stale_card["before"]) + 0.1)
    refused = kenn.apply("set the Drum Bus compressor threshold to -20 dB", stale_card)
    assert refused["receipt"]["status"] == "failed"
    assert refused["receipt"]["write_attempted"] is False
    kenn.do("Undo that")
    assert kenn.volume("Synth") == pytest.approx(start, abs=1e-4)


def test_a_failure_after_the_write_was_sent_still_stops_the_walk(kenn) -> None:
    # The marker has to be explicit False; a failed receipt from an older build, or one whose write went out,
    # carries no marker or True and keeps blocking, as in the parametrised test above.
    older = {"receipt_id": "receipt-older", "status": "applied", "verified": True}
    for marker in ({}, {"write_attempted": True}):
        failure = {"receipt_id": "receipt-failed", "status": "failed", "verified": False, **marker}
        assert undo_target(kenn.session, [failure, older]) is failure


def test_a_device_write_whose_readback_failed_still_stops_the_walk(kenn, monkeypatch) -> None:
    # The write went out and we could not read it back, so the threshold may have moved; undoing the older
    # synth change underneath it would leave the set wrong in two places.
    card = kenn.propose("set the Drum Bus compressor threshold to -20 dB")
    kenn.do("Set the synth to -4 dB")
    sent = []
    real_write, real_read = kenn.fake.set_device_parameter, kenn.fake.get_device_parameters

    def write(*args, **kwargs):
        sent.append(args)
        return real_write(*args, **kwargs)

    def read(*args, **kwargs):
        if sent:
            raise TimeoutError("no reply from Live")
        return real_read(*args, **kwargs)

    monkeypatch.setattr(kenn.fake, "set_device_parameter", write)
    monkeypatch.setattr(kenn.fake, "get_device_parameters", read)
    failed = kenn.apply("set the Drum Bus compressor threshold to -20 dB", card)
    monkeypatch.setattr(kenn.fake, "get_device_parameters", real_read)

    assert sent and failed["receipt"]["status"] == "unknown"
    assert "write_attempted" not in failed["receipt"]
    assert not (kenn.ask_undo().get("proposal") or {}).get("confirmation_token")
