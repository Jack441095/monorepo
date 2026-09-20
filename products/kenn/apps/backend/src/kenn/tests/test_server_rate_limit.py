"""RATE_BUCKETS is a module-level dict keyed by (client_key, scope). Each
bucket's own deque already self-prunes by time window, but nothing removed
a (key, scope) pair from the dict itself once its bucket went empty -- so a
deployment where client_key comes from an untrusted, client-supplied header
(CF-Connecting-IP/X-Forwarded-For/X-Real-IP) could grow RATE_BUCKETS without
bound simply by varying that header on every request. This verifies the new
bucket-count cap actually evicts stale buckets instead of only pruning
entries inside each one."""

from __future__ import annotations

import pytest

from kenn import server_rate_limit


@pytest.fixture(autouse=True)
def _reset_rate_state():
    server_rate_limit.RATE_BUCKETS.clear()
    yield
    server_rate_limit.RATE_BUCKETS.clear()


def test_requests_within_the_limit_are_allowed():
    for _ in range(5):
        allowed, retry_after = server_rate_limit.rate_allowed("client-a", "report")
        assert allowed is True
        assert retry_after == 0


def test_exceeding_the_limit_is_rejected_with_a_retry_after():
    limit, _window = server_rate_limit.RATE_LIMITS["ask"]
    for _ in range(limit):
        assert server_rate_limit.rate_allowed("client-b", "ask")[0] is True
    allowed, retry_after = server_rate_limit.rate_allowed("client-b", "ask")
    assert allowed is False
    assert retry_after > 0


def test_distinct_keys_and_scopes_are_tracked_independently():
    limit, _window = server_rate_limit.RATE_LIMITS["ask"]
    for _ in range(limit):
        assert server_rate_limit.rate_allowed("client-c", "ask")[0] is True
    assert server_rate_limit.rate_allowed("client-c", "ask")[0] is False
    # A different client, and the same client under a different scope, are
    # unaffected by client-c's exhausted "ask" bucket.
    assert server_rate_limit.rate_allowed("client-d", "ask")[0] is True
    assert server_rate_limit.rate_allowed("client-c", "report")[0] is True


def test_bucket_count_is_bounded_even_with_many_distinct_client_keys(monkeypatch):
    monkeypatch.setattr(server_rate_limit, "MAX_TRACKED_BUCKETS", 50)
    monkeypatch.setattr(server_rate_limit, "_MAX_WINDOW_SECONDS", 0)
    for index in range(500):
        allowed, _retry_after = server_rate_limit.rate_allowed(f"spoofed-client-{index}", "report")
        assert allowed is True
    # Every bucket's single entry is already older than the (patched, zero)
    # max window by the time eviction runs, so the dict never grows past a
    # small multiple of the cap instead of accumulating one entry per key.
    assert len(server_rate_limit.RATE_BUCKETS) <= server_rate_limit.MAX_TRACKED_BUCKETS + 1


def test_a_bucket_with_no_recent_activity_does_not_block_a_later_request(monkeypatch):
    monkeypatch.setattr(server_rate_limit, "MAX_TRACKED_BUCKETS", 0)
    limit, _window = server_rate_limit.RATE_LIMITS["ask"]
    for _ in range(limit):
        assert server_rate_limit.rate_allowed("client-e", "ask")[0] is True
    assert server_rate_limit.rate_allowed("client-e", "ask")[0] is False
    # Forcing eviction on every call (cap of 0) must never evict a bucket
    # that still has live, unexpired entries -- only genuinely stale ones.
    assert ("client-e", "ask") in server_rate_limit.RATE_BUCKETS
