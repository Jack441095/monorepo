"""The FastAPI Live command route used to be a second copy of the stdlib handler and had drifted from it.

A MIDI clip, duplication, rename, audition or sample proposal went to the generic planner and came back
"requires confirmation" for ever, and a command that did apply recorded no receipt, so Undo had nothing to find.
"""

from __future__ import annotations

import pytest

from kenn.routes import daw_command_handler, daw_routes
from kenn.core import midi_clip_service


class _Service:
    def execute_create(self, proposal, *, confirm_token, session_id, **kwargs):
        _Service.seen = (confirm_token, session_id)
        return {"ok": True, "receipt": {"receipt_id": "r1", "verified": True, "target": {}}}


@pytest.fixture(autouse=True)
def live_allowed(monkeypatch):
    monkeypatch.setattr(daw_command_handler, "action_allowed", lambda _name: True)
    monkeypatch.setattr(daw_command_handler, "MidiClipActionService", _Service)


def test_a_midi_clip_proposal_is_applied_through_fastapi_and_its_receipt_is_kept(monkeypatch):
    receipts = []
    monkeypatch.setattr(daw_command_handler, "record_receipt", lambda receipt, session_id: receipts.append((receipt["receipt_id"], session_id)))
    payload = {
        "session_id": "s", "confirmation_token": "tok",
        "proposal": {"schema": midi_clip_service.CREATE_PROPOSAL_SCHEMA},
    }
    status, body = daw_routes.handle_live_command(payload, pending_proposals={})
    assert status == 200 and body["ok"] is True
    assert _Service.seen == ("tok", "s") and receipts == [("r1", "s")]


def test_fastapi_and_the_stdlib_server_answer_a_proposal_the_same_way():
    class Handler:
        def send_json(self, status, body):
            self.sent = (status, body)

    payload = {"session_id": "s", "confirm_token": "tok", "proposal": {"schema": midi_clip_service.CREATE_PROPOSAL_SCHEMA}}
    handler = Handler()
    daw_command_handler.handle_live_command(handler, None, {}, dict(payload))
    assert handler.sent == daw_routes.handle_live_command(dict(payload), pending_proposals={})


def test_the_session_id_argument_still_fills_in_a_payload_without_one(monkeypatch):
    seen = []
    monkeypatch.setattr(daw_command_handler, "record_receipt", lambda *a, **k: None)
    monkeypatch.setattr(_Service, "execute_create", lambda self, proposal, *, confirm_token, session_id, **kw: seen.append(session_id) or {"ok": True})
    daw_routes.handle_live_command(
        {"proposal": {"schema": midi_clip_service.CREATE_PROPOSAL_SCHEMA}}, pending_proposals={}, session_id="from-arg")
    assert seen == ["from-arg"]


def test_a_denied_live_policy_is_a_403_on_fastapi_too(monkeypatch):
    monkeypatch.setattr(daw_command_handler, "action_allowed", lambda _name: False)
    status, body = daw_routes.handle_live_command(
        {"session_id": "s", "proposal": {"schema": midi_clip_service.CREATE_PROPOSAL_SCHEMA}}, pending_proposals={})
    assert status == 403 and body["ok"] is False


def test_a_pending_proposal_is_found_by_its_token_and_new_ones_are_kept_in_the_shared_dict(monkeypatch):
    monkeypatch.setattr(daw_command_handler, "record_receipt", lambda *a, **k: None)
    pending = {"tok": {"schema": midi_clip_service.CREATE_PROPOSAL_SCHEMA}}
    status, body = daw_routes.handle_live_command({"session_id": "s", "confirm_token": "tok"}, pending_proposals=pending)
    assert status == 200 and _Service.seen == ("tok", "s")

    monkeypatch.setattr(daw_command_handler, "_get_handle_command", lambda: lambda *a, **k: {
        "status": "requires_confirmation", "proposal": {"confirmation_token": "new-tok"}})
    daw_routes.handle_live_command({"session_id": "s", "command": "mute drums"}, pending_proposals=pending)
    assert "new-tok" in pending


class _ClipService:
    def propose_undo(self, receipt, *, session_id):
        return {"ok": True, "proposal": {"planned_for": receipt["receipt_id"]}}

    def execute_undo(self, proposal, *, confirm_token, session_id, **kwargs):
        _ClipService.applied = (confirm_token, session_id)
        return {"ok": True, "receipt": {"receipt_id": "undo-1"}}


def test_a_clip_duplication_undo_is_planned_and_applied_through_fastapi(monkeypatch):
    from kenn.core import clip_duplication_service as dup

    receipts = []
    monkeypatch.setattr(daw_command_handler, "ClipDuplicationActionService", _ClipService)
    monkeypatch.setattr(daw_command_handler, "action_allowed", lambda _name: True)
    monkeypatch.setattr(daw_command_handler, "record_receipt", lambda receipt, session_id: receipts.append(receipt["receipt_id"]))

    receipt = {"schema": dup.RECEIPT_SCHEMA, "receipt_id": "r9"}
    status, body = daw_routes.handle_osc_undo({"session_id": "s", "receipt": receipt})
    assert status == 200 and body["proposal"] == {"planned_for": "r9"}

    status, body = daw_routes.handle_osc_undo({
        "session_id": "s", "receipt": receipt, "confirm_token": "tok",
        "proposal": {"schema": dup.UNDO_PROPOSAL_SCHEMA},
    })
    assert status == 200 and _ClipService.applied == ("tok", "s") and receipts == ["undo-1"]


def test_fastapi_and_the_stdlib_server_answer_an_undo_request_the_same_way(monkeypatch):
    from kenn.core import clip_duplication_service as dup

    class Handler:
        def send_json(self, status, body):
            self.sent = (status, body)

    monkeypatch.setattr(daw_command_handler, "ClipDuplicationActionService", _ClipService)
    for payload in (
        {"session_id": "s", "receipt": {"schema": dup.RECEIPT_SCHEMA, "receipt_id": "r9"}},
        {"session_id": "", "receipt": {}},
    ):
        handler = Handler()
        daw_command_handler.handle_osc_undo(handler, dict(payload))
        assert handler.sent == daw_routes.handle_osc_undo(dict(payload))
