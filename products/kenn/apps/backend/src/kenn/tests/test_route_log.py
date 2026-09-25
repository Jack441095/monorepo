"""Every chat route is timed; nothing about the question is kept."""

from __future__ import annotations

import json

from kenn.core import route_log


def test_routes_are_logged_with_timings_only(tmp_path) -> None:
    log = tmp_path / "routes.jsonl"
    for ms in (100, 200, 300):
        route_log.record("production", ms, brain=True, proposal=False, path=log)
    route_log.record("live_command", 50, brain=False, proposal=True, path=log)
    rows = [json.loads(line) for line in log.read_text().splitlines()]
    assert set(rows[0]) == {"at", "route", "ms", "brain", "proposal"}
    report = route_log.summary(log)
    assert report["production"] == {"requests": 3, "p50_ms": 200.0, "p95_ms": 200.0, "brain": 3}
    assert report["live_command"]["requests"] == 1


def test_the_log_keeps_only_the_newest_requests(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(route_log, "MAX_LINES", 10)
    log = tmp_path / "routes.jsonl"
    for number in range(40):
        route_log.record(f"r{number}", 1, brain=False, proposal=False, path=log)
    assert len(log.read_text().splitlines()) <= 40 and "r39" in log.read_text()
