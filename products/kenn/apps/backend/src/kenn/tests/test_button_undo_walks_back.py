"""A change undone with the card's Undo button is not offered back by a later "Undo that"."""

from __future__ import annotations

import pytest

from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_action_service import LiveActionService
from kenn.core.live_command import handle_command
from kenn.core.live_receipt_journal import record_receipt
from kenn.core.session_context import note_pending_undo, note_undo_applied, undo_target
from kenn.routes import daw_command_handler


class _Handler:
    def send_json(self, status, body):
        self.sent = (status, body)


@pytest.fixture()
def kenn(monkeypatch, tmp_path):
    from kenn.core import live_receipt_journal

    monkeypatch.setattr(live_receipt_journal, "JOURNAL_PATH", tmp_path / "receipts.jsonl")
    monkeypatch.setenv("KENN_ALLOW_DAW_CONTROL", "1")
    for name in ("KENN_LIVE_LLM_ENABLED", "KENN_LLM_ENABLED", "KENN_LLM_ENABLED_COMMAND"):
        monkeypatch.delenv(name, raising=False)
    service = LiveActionService(FakeLiveBackend())
    # The route builds its own LiveActionService; hand it ours so both paths see the same fake set.
    monkeypatch.setattr(daw_command_handler, "_get_live_action_service", lambda: lambda: service)
    return service, f"button-{tmp_path.name}"


def _do(service, session, text):
    proposal = handle_command(text, session_id=session, service=service).get("proposal") or {}
    applied = handle_command(text, session_id=session, service=service, proposal=proposal,
                             confirm_token=proposal["confirmation_token"], idempotency_key=proposal.get("action_id"))
    record_receipt(applied["receipt"], session_id=session)
    return applied["receipt"]


def _press_undo(session, receipt):
    # Both phases exactly as undoKennAction in api/kenn.ts sends them.
    handler = _Handler()
    daw_command_handler.handle_osc_undo(handler, {"session_id": session, "receipt": receipt})
    proposal = handler.sent[1]["proposal"]
    daw_command_handler.handle_osc_undo(handler, {
        "session_id": session, "receipt": receipt, "proposal": proposal,
        # Device proposals have no action_id; the frontend then falls back to a made-up key, as here.
        "confirm_token": proposal["confirmation_token"], "idempotency_key": proposal.get("action_id") or "undo-button",
    })
    assert handler.sent[0] == 200
    return handler.sent[1]["receipt"]


def _synth(service):
    return next(t["volume"] for t in service.snapshot()["tracks"] if t["name"] == "Synth")


def test_undo_that_after_the_undo_button_walks_back_instead_of_redoing(kenn) -> None:
    # Regression (9 Oct 2026 adversary review): the button's undo went through /api/ableton/osc/undo, which kept
    # no link to the change it reversed, so "Undo that" offered to set the synth down 2 dB again.
    service, session = kenn
    start = _synth(service)
    _do(service, session, "Set the synth to -4 dB")
    after_first = _synth(service)
    second = _do(service, session, "Turn the synth down 2 dB")
    _press_undo(session, second)
    assert _synth(service) == pytest.approx(after_first, abs=1e-4)
    _do(service, session, "Undo that")
    assert _synth(service) == pytest.approx(start, abs=1e-4)


def test_a_recipe_undone_with_the_button_leaves_nothing_for_undo_that(kenn) -> None:
    # A recipe undo is itself a recipe, so its receipt has to carry the proposal's action_id for the link to hold.
    service, session = kenn
    _press_undo(session, _do(service, session, "Push the synth back"))
    answer = handle_command("Undo that", session_id=session, service=service)["answer"]
    assert "don't have a verified change" in answer


@pytest.mark.parametrize("undo_with", ["button", "chat"])
def test_a_device_parameter_undo_is_walked_past_too(kenn, undo_with) -> None:
    # Device proposals carry "id", not "action_id", so before 9 Oct their undos were never linked from either
    # path and the next "Undo that" offered the threshold change back.
    service, session = kenn
    start = _synth(service)
    _do(service, session, "Set the synth to -4 dB")
    threshold = _do(service, session, "set the Drum Bus compressor threshold to -20 dB")
    if undo_with == "button":
        _press_undo(session, threshold)
    else:
        _do(service, session, "Undo that")
    _do(service, session, "Undo that")
    assert _synth(service) == pytest.approx(start, abs=1e-4)


def test_a_receipt_with_no_action_id_never_counts_as_an_undo(kenn) -> None:
    # The old "" key let a gain-staging receipt (no action_id) consume a device undo's pending entry, so the
    # walk skipped a gain staging nobody reversed and a device change that was still in place.
    _, session = kenn
    note_pending_undo(session, {"schema": "kenn.action_proposal.v1"}, "receipt-device-change")
    gain_stage = {"receipt_id": "receipt-gain-stage", "status": "applied", "verified": True}
    note_undo_applied(session, gain_stage)
    device_change = {"receipt_id": "receipt-device-change", "status": "applied", "verified": True}
    assert undo_target(session, [gain_stage, device_change]) is gain_stage
