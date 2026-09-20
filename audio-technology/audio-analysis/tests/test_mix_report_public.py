"""Tests for the public signed-token Mix Doctor report route (plan.md §14.6).

Covers three layers:
- token: make/verify round-trip, tamper, wrong-id, and expiry;
- policy: `GET /mix-report/<id>` is classified SIGNED_TOKEN (so it bypasses the
  dashboard auth gate and self-verifies) — mirroring `/invoice/`;
- handler: a valid token renders HTML; a bad/missing token is rejected 401; a
  missing review is 404. A duck-typed fake handler captures the response.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (REPO_ROOT / "business", REPO_ROOT / "business" / "app", REPO_ROOT / "studio" / "audio_analysis"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import mix_report_tokens  # noqa: E402
from nite_core.endpoint_policy import EndpointAccess, endpoint_policy  # noqa: E402


# ---- token round-trip -------------------------------------------------------

def test_token_round_trip():
    tok = mix_report_tokens.make_report_token("rev-123")
    assert mix_report_tokens.verify_report_token("rev-123", tok)


def test_token_rejects_wrong_id():
    tok = mix_report_tokens.make_report_token("rev-123")
    assert not mix_report_tokens.verify_report_token("rev-999", tok)


def test_token_rejects_tamper():
    tok = mix_report_tokens.make_report_token("rev-123")
    tampered = ("A" if tok[0] != "A" else "B") + tok[1:]
    assert not mix_report_tokens.verify_report_token("rev-123", tampered)


def test_token_rejects_empty():
    assert not mix_report_tokens.verify_report_token("rev-123", "")


def test_token_expires():
    tok = mix_report_tokens.make_report_token("rev-123", ttl_seconds=-1)
    assert not mix_report_tokens.verify_report_token("rev-123", tok)


def test_report_url_shape():
    info = mix_report_tokens.report_url("rev-123")
    assert info["url"].startswith("http://127.0.0.1:8080/mix-report/rev-123?token=")
    assert info["expires_in_days"] == 30


# ---- policy classification --------------------------------------------------

def test_policy_classifies_mix_report_as_signed_token():
    policy = endpoint_policy("business", "GET", "/mix-report/rev-123")
    assert policy.access == EndpointAccess.SIGNED_TOKEN


def test_policy_invoice_still_signed_token():
    # Regression: extending the prefix tuple must not break the invoice route.
    policy = endpoint_policy("business", "GET", "/invoice/INV-1")
    assert policy.access == EndpointAccess.SIGNED_TOKEN


def test_policy_classifies_mix_report_status_poll_as_signed_token_too():
    # The /status sub-path shares the "/mix-report/" prefix on purpose, so
    # it inherits the same classification without a separate policy entry.
    policy = endpoint_policy("business", "GET", "/mix-report/rev-123/status")
    assert policy.access == EndpointAccess.SIGNED_TOKEN


# ---- handler ----------------------------------------------------------------

class _FakeHandler:
    def __init__(self, *, authed: bool = False):
        self._authed = authed
        self.status = None
        self.body = b""
        self.content_type = None
        self.payload = None

    def authorized(self) -> bool:
        return self._authed

    def send_bytes(self, status, body, content_type, filename=None):
        self.status = status
        self.body = body
        self.content_type = content_type

    def send_json(self, status, payload):
        self.status = status
        self.payload = payload
        self.body = repr(payload).encode()


@pytest.fixture
def routes(monkeypatch):
    from app.routes import mix_review_routes as mr

    sample = {
        "title": "Shared Track",
        "rating": "Good",
        "technical_score": 80,
        "metrics": {"integrated_lufs": -10.0},
        "action_plan": [{"priority": "high", "focus": "Headroom", "action": "Drop 2 dB."}],
    }
    monkeypatch.setattr(mr.mix_review, "mix_review_status", lambda rid: {"ok": True, "review": sample} if rid == "rev-1" else {"ok": False, "error": "nope"})
    return mr


def test_handler_renders_with_valid_token(routes):
    tok = mix_report_tokens.make_report_token("rev-1")
    h = _FakeHandler()
    handled = routes.handle_mix_report_public_get(h, f"/mix-report/rev-1?token={tok}")
    assert handled is True
    assert h.status == 200
    assert h.content_type.startswith("text/html")
    assert b"Shared Track" in h.body
    assert b"Drop 2 dB." in h.body


def test_handler_rejects_bad_token(routes):
    h = _FakeHandler()
    handled = routes.handle_mix_report_public_get(h, "/mix-report/rev-1?token=garbage")
    assert handled is True
    assert h.status == 401


def test_handler_allows_authed_user_without_token(routes):
    h = _FakeHandler(authed=True)
    assert routes.handle_mix_report_public_get(h, "/mix-report/rev-1") is True
    assert h.status == 200
    assert b"Shared Track" in h.body


def test_handler_404_for_missing_review(routes):
    tok = mix_report_tokens.make_report_token("rev-missing")
    h = _FakeHandler()
    routes.handle_mix_report_public_get(h, f"/mix-report/rev-missing?token={tok}")
    assert h.status == 404


def test_handler_ignores_non_matching_path(routes):
    h = _FakeHandler()
    handled = routes.handle_mix_report_public_get(h, "/api/admin/something")
    assert handled is False
    assert h.status is None


# ---- /mix-report/<id>/status (JSON poll) ------------------------------------

@pytest.fixture
def status_routes(monkeypatch):
    from app.routes import mix_review_routes as mr

    reviews = {
        "rev-pending": {"title": "Still Cooking", "status": "pending"},
        "rev-done": {"title": "Finished Track", "status": "completed"},
        "rev-err": {"title": "Broke", "status": "error", "error": "decode failed"},
    }

    def fake_status(rid):
        if rid in reviews:
            return {"ok": True, "review": reviews[rid]}
        return {"ok": False, "error": "nope"}

    monkeypatch.setattr(mr.mix_review, "mix_review_status", fake_status)
    return mr


def test_status_poll_reports_pending(status_routes):
    tok = mix_report_tokens.make_report_token("rev-pending")
    h = _FakeHandler()
    handled = status_routes.handle_mix_report_public_get(h, f"/mix-report/rev-pending/status?token={tok}")
    assert handled is True
    assert h.status == 200
    assert h.payload == {"ok": True, "id": "rev-pending", "status": "pending", "error": None}


def test_status_poll_reports_completed(status_routes):
    tok = mix_report_tokens.make_report_token("rev-done")
    h = _FakeHandler()
    handled = status_routes.handle_mix_report_public_get(h, f"/mix-report/rev-done/status?token={tok}")
    assert handled is True
    assert h.status == 200
    assert h.payload["status"] == "completed"


def test_status_poll_reports_error_state(status_routes):
    tok = mix_report_tokens.make_report_token("rev-err")
    h = _FakeHandler()
    handled = status_routes.handle_mix_report_public_get(h, f"/mix-report/rev-err/status?token={tok}")
    assert handled is True
    assert h.payload["status"] == "error"
    assert h.payload["error"] == "decode failed"


def test_status_poll_rejects_bad_token(status_routes):
    h = _FakeHandler()
    handled = status_routes.handle_mix_report_public_get(h, "/mix-report/rev-pending/status?token=garbage")
    assert handled is True
    assert h.status == 401
    assert h.payload["ok"] is False


def test_status_poll_404_for_missing_review(status_routes):
    tok = mix_report_tokens.make_report_token("rev-missing")
    h = _FakeHandler()
    handled = status_routes.handle_mix_report_public_get(h, f"/mix-report/rev-missing/status?token={tok}")
    assert handled is True
    assert h.status == 404


def test_status_poll_allows_authed_user_without_token(status_routes):
    h = _FakeHandler(authed=True)
    handled = status_routes.handle_mix_report_public_get(h, "/mix-report/rev-pending/status")
    assert handled is True
    assert h.status == 200
    assert h.payload["status"] == "pending"


def test_status_poll_does_not_leak_into_the_html_report_branch(status_routes):
    """A wrong-token request for the real HTML report must still 401 with
    plain text, not accidentally take the JSON status branch."""
    h = _FakeHandler()
    handled = status_routes.handle_mix_report_public_get(h, "/mix-report/rev-pending?token=garbage")
    assert handled is True
    assert h.status == 401
    assert h.content_type == "text/plain; charset=utf-8"
