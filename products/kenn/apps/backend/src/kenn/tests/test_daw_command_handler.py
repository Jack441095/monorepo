"""The command route passes a missing idempotency key on as missing, not as the text "None"."""

from __future__ import annotations

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
