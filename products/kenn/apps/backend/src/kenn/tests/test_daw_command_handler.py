"""The command route passes a missing idempotency key on as missing, not as the text "None"."""

from __future__ import annotations

import pytest

from kenn.routes import daw_command_handler


def test_a_null_idempotency_key_is_not_shared_between_requests(monkeypatch) -> None:
    # 26 Sept 2026: str(None) made every keyless confirm use the key "None", so after one device change every later
    # one was refused as "already executed" (and a script's undo with it, leaving a compressor at 4:1).
    seen = []
    monkeypatch.setattr(daw_command_handler, "action_allowed", lambda _name: True)
    monkeypatch.setattr(daw_command_handler, "_get_handle_command",
                        lambda: lambda command, **kwargs: seen.append(kwargs["idempotency_key"]) or {"status": "applied"})

    class Handler:
        def send_json(self, status, body) -> None:
            self.status = status

    payload = {"command": "", "session_id": "keyless", "proposal": {"id": "proposal-1", "target": "ableton_device"},
               "confirm_token": "token", "idempotency_key": None}
    daw_command_handler.handle_live_command(Handler(), None, {}, payload)
    assert seen == [""]


class _Recorder:
    def __init__(self) -> None:
        self.status = None

    def send_json(self, status, body) -> None:
        self.status = status


def test_a_confirmation_token_alias_reaches_a_generic_command(monkeypatch) -> None:
    # The handler found the pending proposal under either key but then passed only confirm_token to the services,
    # so a client using the confirmation_token name was refused with an empty token.
    seen = []
    monkeypatch.setattr(daw_command_handler, "action_allowed", lambda _name: True)
    monkeypatch.setattr(daw_command_handler, "_get_handle_command",
                        lambda: lambda command, **kwargs: seen.append(kwargs["confirm_token"]) or {"status": "applied"})
    pending = {"tok-1": {"id": "proposal-1", "target": "ableton_device"}}
    daw_command_handler.handle_live_command(_Recorder(), None, pending, {"session_id": "s", "confirmation_token": "tok-1"})
    assert seen == ["tok-1"]


class _AnyService:
    """Records the confirm_token whichever execute method the handler picks."""

    seen: list = []

    def __getattr__(self, name):
        def execute(proposal, *, confirm_token, **kwargs):
            _AnyService.seen.append((name, confirm_token))
            return {"ok": False}
        return execute


def _schema(attr, module):
    import importlib

    return getattr(importlib.import_module(module), attr)


@pytest.mark.parametrize("service,schema,extra,method", [
    ("MidiClipActionService", ("CREATE_PROPOSAL_SCHEMA", "kenn.core.midi_clip_service"), {}, "execute_create"),
    ("MidiClipActionService", ("UPDATE_PROPOSAL_SCHEMA", "kenn.core.midi_clip_service"), {}, "execute_update"),
    ("ClipDuplicationActionService", ("PROPOSAL_SCHEMA", "kenn.core.clip_duplication_service"), {}, "execute"),
    ("ClipRenameActionService", ("PROPOSAL_SCHEMA", "kenn.core.clip_rename_service"), {}, "execute"),
    ("ClipAuditionActionService", ("PROPOSAL_SCHEMA", "kenn.core.clip_audition_service"), {}, "execute"),
    ("ClipAuditionActionService", ("PROPOSAL_SCHEMA", "kenn.core.clip_audition_service"), {"action": "stop_clip"}, "execute_stop"),
    ("SampleImportService", ("IMPORT_PROPOSAL_SCHEMA", "kenn.core.sample_import_service"), {}, "execute_import"),
    ("SampleImportService", ("REMOVE_PROPOSAL_SCHEMA", "kenn.core.sample_import_service"), {}, "execute_remove"),
])
def test_a_confirmation_token_alias_reaches_every_schema_apply(monkeypatch, service, schema, extra, method) -> None:
    _AnyService.seen = []
    monkeypatch.setattr(daw_command_handler, "action_allowed", lambda _name: True)
    monkeypatch.setattr(daw_command_handler, service, _AnyService)
    proposal = {"schema": _schema(*schema), **extra}
    daw_command_handler.handle_live_command(
        _Recorder(), None, {}, {"session_id": "s", "proposal": proposal, "confirmation_token": "tok-2"})
    assert _AnyService.seen == [(method, "tok-2")]


def test_confirm_token_still_wins_when_both_keys_are_sent(monkeypatch) -> None:
    seen = []
    monkeypatch.setattr(daw_command_handler, "action_allowed", lambda _name: True)
    monkeypatch.setattr(daw_command_handler, "_get_handle_command",
                        lambda: lambda command, **kwargs: seen.append(kwargs["confirm_token"]) or {"status": "applied"})
    proposal = {"id": "proposal-1", "target": "ableton_device"}
    daw_command_handler.handle_live_command(
        _Recorder(), None, {}, {"session_id": "s", "proposal": proposal,
                                "confirm_token": "first", "confirmation_token": "second"})
    assert seen == ["first"]


def test_a_confirmation_token_alias_reaches_a_safe_live_action_apply(monkeypatch) -> None:
    seen = []

    class _Service:
        def execute(self, proposal, *, confirm_token, **kwargs):
            seen.append(confirm_token)
            return {"ok": True}

    monkeypatch.setattr(daw_command_handler, "action_allowed", lambda _name: True)
    monkeypatch.setattr(daw_command_handler, "_get_live_action_service", lambda: _Service)
    daw_command_handler.handle_safe_live_action(
        _Recorder(), "apply", {"session_id": "s", "proposal": {"id": "p"}, "confirmation_token": "tok-3"})
    assert seen == ["tok-3"]
