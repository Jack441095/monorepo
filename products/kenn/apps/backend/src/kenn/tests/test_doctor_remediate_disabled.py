"""/api/session/doctor/remediate answered 500 for every request and, had it got further, said "applied" for a
confirmed token without writing to Live. It is closed until it goes through the proposal service.
"""

from __future__ import annotations

import pytest

from kenn.routes import doctor_handler


class _Handler:
    def __init__(self):
        self.sent = None

    def send_json(self, status, body):
        self.sent = (status, body)


@pytest.mark.parametrize("payload", [
    {},
    {"issue_code": "SUB_KICK_CLASH", "track_index": 2},
    {"issue_code": "SUB_KICK_CLASH", "track_index": 2, "confirm_token": "anything"},
])
def test_doctor_remediation_is_closed_and_never_claims_a_change(payload):
    handler = _Handler()
    doctor_handler.handle_post_doctor_remediate(handler, payload)
    status, body = handler.sent
    assert status == 410 and body["ok"] is False
    assert "applied" not in str(body).lower()


def test_the_mcp_session_doctor_does_not_post_a_batch_to_a_route_that_does_not_exist(monkeypatch):
    from types import SimpleNamespace

    from kenn.core.mcp import session_intelligence
    from kenn.core.session_doctor import SessionDoctor

    class Client:
        def get(self, path, params=None):
            return {"tracks": []}

        def post(self, path, body):
            raise AssertionError(f"posted to {path}")

    report = SimpleNamespace(track_count=1, issues_found=1, summary="x", issues=[], remediation_batch=[{"action": "set_volume"}])
    monkeypatch.setattr(SessionDoctor, "audit", classmethod(lambda cls, *a, **k: report))
    result = session_intelligence.kenn_session_doctor(SimpleNamespace(client=Client()), {"auto_remediate": True})
    assert result["remediation_execution"]["status"] == "not_executed" and result["remediation_execution"]["ok"] is False
    assert result["remediation_batch"] == [{"action": "set_volume"}]
