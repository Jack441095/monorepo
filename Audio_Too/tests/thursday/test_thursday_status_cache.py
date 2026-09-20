"""Status-cache behaviour tests (synthetic, no real subprocess calls)."""

from __future__ import annotations

import time

import pytest

from thursday import status_cache


@pytest.fixture(autouse=True)
def _reset_cache():
    status_cache.invalidate()
    yield
    status_cache.invalidate()


def test_first_call_is_live_then_cached():
    calls = {"n": 0}

    def fake():
        calls["n"] += 1
        return "STATUS-TEXT"

    with patch_client(fake):
        first = status_cache.get_business_status()
        second = status_cache.get_business_status()

    assert calls["n"] == 1  # second served from cache
    assert first[0] == "STATUS-TEXT"
    assert second[0] == "STATUS-TEXT"
    assert first[1] < second[1] or (first[1] == 0.0 and second[1] >= 0.0)


def test_force_refresh_bypasses_cache():
    calls = {"n": 0}

    def fake():
        calls["n"] += 1
        return f"S{calls['n']}"

    with patch_client(fake):
        status_cache.get_business_status()
        refreshed = status_cache.get_business_status(force_refresh=True)

    assert calls["n"] == 2
    assert refreshed[0] == "S2"
    assert refreshed[1] == 0.0


def test_ttl_expiry_triggers_refresh():
    calls = {"n": 0}

    def fake():
        calls["n"] += 1
        return f"S{calls['n']}"

    with patch_client(fake):
        status_cache.get_business_status(ttl_seconds=0.01)
        time.sleep(0.02)
        later = status_cache.get_business_status(ttl_seconds=0.01)

    assert calls["n"] == 2
    assert later[0] == "S2"


def test_stale_fallback_on_live_failure():
    calls = {"n": 0}

    def good():
        return "GOOD"

    def broken():
        raise RuntimeError("cli exploded")

    from unittest.mock import patch

    with patch.object(status_cache.client, "business_status", good):
        status_cache.get_business_status()
    with patch.object(status_cache.client, "business_status", broken):
        served, age = status_cache.get_business_status(force_refresh=True)

    assert served == "GOOD"  # stale but served honestly
    assert age > 0


def test_age_note_wording():
    assert status_cache.age_note(30) == ""
    note = status_cache.age_note(600)
    assert "cached" in note and "10 min ago" in note


class patch_client:
    """Patch business_status on the module's client reference."""

    def __init__(self, fn):
        self.fn = fn

    def __enter__(self):
        self.p = patch_object(status_cache.client, "business_status", self.fn)
        self.p.__enter__()
        return self

    def __exit__(self, *exc):
        return self.p.__exit__(*exc)


def patch_object(obj, name, value):
    from unittest.mock import patch

    return patch.object(obj, name, value)


def test_no_cache_live_failure_raises_for_honest_degradation():
    """With no cached fallback, live failure must propagate so section-level
    degradation (brief 'unavailable') stays truthful."""
    from unittest.mock import patch

    def broken():
        raise RuntimeError("cli exploded")

    with patch.object(status_cache.client, "business_status", broken):
        with pytest.raises(RuntimeError):
            status_cache.get_business_status()
