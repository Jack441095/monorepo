"""The returns cache refetches only when stale and never attaches a half answer."""

from __future__ import annotations

from kenn.core.return_tracks_cache import attach_return_tracks


def test_cache_miss_fetches_once_and_attaches_the_returns() -> None:
    calls: list[str] = []

    def fetch():
        calls.append("poll")
        return [{"name": "A-Reverb"}]

    snapshot, cached = attach_return_tracks({"tracks": []}, None, now=100.0, fetch=fetch)
    assert snapshot["return_tracks"] == [{"name": "A-Reverb"}]
    assert cached == (100.0, [{"name": "A-Reverb"}])
    assert calls == ["poll"]


def test_fresh_cache_reuses_the_poll_without_touching_live() -> None:
    def fetch():  # pragma: no cover - must not run while the entry is fresh
        raise AssertionError("stale fetch on a fresh cache")

    snapshot, cached = attach_return_tracks(
        {"tracks": []}, (100.0, [{"name": "A-Reverb"}]), now=105.0, fetch=fetch
    )
    assert snapshot["return_tracks"] == [{"name": "A-Reverb"}]
    assert cached == (100.0, [{"name": "A-Reverb"}])


def test_stale_cache_refetches_after_the_ttl() -> None:
    snapshot, cached = attach_return_tracks(
        {"tracks": []}, (100.0, [{"name": "A-Reverb"}]), now=121.0,
        fetch=lambda: [{"name": "A-Reverb"}, {"name": "B-Delay"}],
    )
    assert snapshot["return_tracks"] == [{"name": "A-Reverb"}, {"name": "B-Delay"}]
    assert cached[0] == 121.0


def test_failed_fetch_clears_the_cache_and_leaves_the_snapshot_untouched() -> None:
    def fetch():
        raise OSError("Live offline")

    snapshot, cached = attach_return_tracks({"tracks": []}, None, now=100.0, fetch=fetch)
    assert "return_tracks" not in snapshot
    assert cached is None
