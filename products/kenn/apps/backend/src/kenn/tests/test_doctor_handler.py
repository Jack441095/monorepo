"""The session doctor's audit route answers even when it finds something."""

from __future__ import annotations

from kenn.routes import doctor_handler


class _Handler:
    def send_json(self, status, body) -> None:
        self.status, self.body = status, body


def test_an_audit_that_finds_issues_is_not_a_server_error(monkeypatch) -> None:
    # 26 Sept 2026: every audit with an issue read masking-only fields off the doctor's Issue and returned 500.
    from kenn import mixing_doctor

    hot = {"status": "connected", "tracks": [
        {"index": 0, "name": "Lead Vocal", "volume": 0.95, "pan": 0.0, "muted": False, "soloed": False, "devices": []},
        {"index": 1, "name": "Bass", "volume": 0.5, "pan": 0.0, "muted": False, "soloed": False, "devices": []}]}
    monkeypatch.setattr(mixing_doctor, "get_latest_session_state", lambda: hot)
    handler = _Handler()
    doctor_handler.handle_get_doctor_audit(handler)
    assert handler.status == 200 and handler.body["issues_found"] >= 1
    assert "conflict_track_name" not in handler.body["issues"][0]

    doctor_handler.handle_post_doctor_audit(handler, {"session_state": hot})
    assert handler.status == 200 and handler.body["issues_found"] >= 1

