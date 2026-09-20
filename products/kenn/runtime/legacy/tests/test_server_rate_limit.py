"""kenn/server_rate_limit.py -- extracted from kenn/server.py 2026-07-14
(docs/codebase_scan_12_07.md §2.2 "large un-decomposed files"). Its actual
rate-limiting logic (not just presence) had zero test coverage before this
extraction; the only existing test mocks enforce_rate_limit() to bypass it
entirely."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
KENN = ROOT / "studio" / "kenn"
if str(KENN) not in sys.path:
    sys.path.insert(0, str(KENN))

from kenn import server_rate_limit as rl  # noqa: E402


class _FakeHandler:
    def __init__(self, headers=None, client_address=("1.2.3.4", 5555)):
        self.headers = headers or {}
        self.client_address = client_address


def test_client_key_prefers_cf_connecting_ip_header():
    handler = _FakeHandler(headers={"CF-Connecting-IP": "9.9.9.9"})
    assert rl.client_key(handler) == "9.9.9.9"


def test_client_key_falls_back_to_client_address():
    handler = _FakeHandler(headers={}, client_address=("10.0.0.5", 1234))
    assert rl.client_key(handler) == "10.0.0.5"


def test_client_key_truncates_to_80_chars():
    handler = _FakeHandler(headers={"X-Forwarded-For": "a" * 200})
    assert len(rl.client_key(handler)) == 80


def test_rate_allowed_permits_within_limit(monkeypatch):
    monkeypatch.setattr(rl, "RATE_LIMITS", {"test_scope": (3, 60)})
    monkeypatch.setattr(rl, "RATE_BUCKETS", rl.defaultdict(rl.deque))

    for _ in range(3):
        allowed, retry = rl.rate_allowed("client-a", "test_scope")
        assert allowed is True
        assert retry == 0


def test_rate_allowed_blocks_once_limit_exceeded(monkeypatch):
    monkeypatch.setattr(rl, "RATE_LIMITS", {"test_scope": (2, 60)})
    monkeypatch.setattr(rl, "RATE_BUCKETS", rl.defaultdict(rl.deque))

    rl.rate_allowed("client-b", "test_scope")
    rl.rate_allowed("client-b", "test_scope")
    allowed, retry = rl.rate_allowed("client-b", "test_scope")

    assert allowed is False
    assert retry > 0


def test_rate_allowed_scopes_are_independent_per_client(monkeypatch):
    monkeypatch.setattr(rl, "RATE_LIMITS", {"test_scope": (1, 60)})
    monkeypatch.setattr(rl, "RATE_BUCKETS", rl.defaultdict(rl.deque))

    rl.rate_allowed("client-c", "test_scope")
    allowed_other_client, _ = rl.rate_allowed("client-d", "test_scope")

    assert allowed_other_client is True


def test_rate_allowed_unknown_scope_uses_default_limit(monkeypatch):
    monkeypatch.setattr(rl, "RATE_BUCKETS", rl.defaultdict(rl.deque))

    allowed, retry = rl.rate_allowed("client-e", "totally_unknown_scope")

    assert allowed is True
    assert retry == 0
