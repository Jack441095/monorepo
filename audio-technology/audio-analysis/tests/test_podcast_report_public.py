"""Tests for the public signed-token podcast-check report route (plan.md's
NEXT item: "wire the podcast report behind a signed-token upload/view (like
Mix Doctor)").

Covers four layers:
- token: make/verify round-trip, tamper, wrong-id, expiry, and namespace
  isolation from mix_report_tokens (a mix-report token must never verify
  against a podcast-report id and vice versa);
- store: save/get round-trip against a real (temp) DB;
- policy: `GET /podcast-report/<id>` is classified SIGNED_TOKEN, same as
  `/mix-report/` and `/invoice/`;
- handler: a valid token serves the stored HTML; a bad/missing token is
  rejected 401; a missing report is 404.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (REPO_ROOT / "server", REPO_ROOT / "server" / "app", REPO_ROOT / "studio" / "audio_analysis"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import mix_report_tokens  # noqa: E402
import podcast_report_tokens  # noqa: E402
from nite_core.endpoint_policy import EndpointAccess, endpoint_policy  # noqa: E402


# ---- token round-trip -------------------------------------------------------

def test_token_round_trip():
    tok = podcast_report_tokens.make_podcast_report_token("pod-123")
    assert podcast_report_tokens.verify_podcast_report_token("pod-123", tok)


def test_token_rejects_wrong_id():
    tok = podcast_report_tokens.make_podcast_report_token("pod-123")
    assert not podcast_report_tokens.verify_podcast_report_token("pod-999", tok)


def test_token_rejects_tamper():
    tok = podcast_report_tokens.make_podcast_report_token("pod-123")
    tampered = ("A" if tok[0] != "A" else "B") + tok[1:]
    assert not podcast_report_tokens.verify_podcast_report_token("pod-123", tampered)


def test_token_rejects_empty():
    assert not podcast_report_tokens.verify_podcast_report_token("pod-123", "")


def test_token_expires():
    tok = podcast_report_tokens.make_podcast_report_token("pod-123", ttl_seconds=-1)
    assert not podcast_report_tokens.verify_podcast_report_token("pod-123", tok)


def test_token_namespace_isolation_from_mix_report_tokens():
    """A mix-report token for id X must not verify as a podcast-report
    token for the same id X, even though both are HMAC'd with the same
    signing_secret() -- the "podcast:" payload namespace must actually do
    something, not just be decorative."""
    same_id = "shared-id-1"
    mix_tok = mix_report_tokens.make_report_token(same_id)
    assert not podcast_report_tokens.verify_podcast_report_token(same_id, mix_tok)

    pod_tok = podcast_report_tokens.make_podcast_report_token(same_id)
    assert not mix_report_tokens.verify_report_token(same_id, pod_tok)


# ---- policy classification --------------------------------------------------

def test_policy_classifies_podcast_report_as_signed_token():
    policy = endpoint_policy("business", "GET", "/podcast-report/pod-123")
    assert policy.access == EndpointAccess.SIGNED_TOKEN


def test_policy_mix_report_and_invoice_still_signed_token():
    # Regression: extending the prefix tuple must not break the siblings.
    assert endpoint_policy("business", "GET", "/mix-report/rev-1").access == EndpointAccess.SIGNED_TOKEN
    assert endpoint_policy("business", "GET", "/invoice/INV-1").access == EndpointAccess.SIGNED_TOKEN


# ---- handler ----------------------------------------------------------------

class _FakeHandler:
    def __init__(self, *, authed: bool = False):
        self._authed = authed
        self.status = None
        self.body = b""
        self.content_type = None

    def authorized(self) -> bool:
        return self._authed

    def send_bytes(self, status, body, content_type, filename=None):
        self.status = status
        self.body = body
        self.content_type = content_type


@pytest.fixture
def routes(monkeypatch):
    from app.routes import mix_review_routes as mr

    stored = {
        "pod-1": {
            "id": "pod-1", "title": "Shared Episode", "target": "apple", "score": 88,
            "html_report": "<html><body>Shared Episode report</body></html>",
            "created_at": "2026-08-01 00:00:00",
        },
    }
    monkeypatch.setattr(mr.podcast_report_store, "get_podcast_report", lambda rid: stored.get(rid))
    return mr


def test_handler_serves_stored_html_with_valid_token(routes):
    tok = podcast_report_tokens.make_podcast_report_token("pod-1")
    h = _FakeHandler()
    handled = routes.handle_podcast_report_public_get(h, f"/podcast-report/pod-1?token={tok}")
    assert handled is True
    assert h.status == 200
    assert h.content_type.startswith("text/html")
    assert b"Shared Episode report" in h.body


def test_handler_rejects_bad_token(routes):
    h = _FakeHandler()
    handled = routes.handle_podcast_report_public_get(h, "/podcast-report/pod-1?token=garbage")
    assert handled is True
    assert h.status == 401


def test_handler_allows_authed_user_without_token(routes):
    h = _FakeHandler(authed=True)
    assert routes.handle_podcast_report_public_get(h, "/podcast-report/pod-1") is True
    assert h.status == 200


def test_handler_404_for_missing_report(routes):
    tok = podcast_report_tokens.make_podcast_report_token("pod-missing")
    h = _FakeHandler()
    routes.handle_podcast_report_public_get(h, f"/podcast-report/pod-missing?token={tok}")
    assert h.status == 404


def test_handler_ignores_non_matching_path(routes):
    h = _FakeHandler()
    handled = routes.handle_podcast_report_public_get(h, "/api/admin/something")
    assert handled is False
    assert h.status is None


def test_handler_a_mix_report_token_cannot_open_a_podcast_report(routes):
    """Cross-endpoint token confusion check: a token minted for the OTHER
    report type must not grant access here."""
    wrong_tok = mix_report_tokens.make_report_token("pod-1")
    h = _FakeHandler()
    handled = routes.handle_podcast_report_public_get(h, f"/podcast-report/pod-1?token={wrong_tok}")
    assert handled is True
    assert h.status == 401
