"""Tests for studio-side proactive alerts in thursday/monitor.py.

docs/CAPABILITY_IMPROVEMENTS_2026-07-06.md flagged that the proactive
monitor was business-only (stale leads, overdue invoices, etc.) despite
studio-side triggers ("render finished," "mix review flagged") being
planned. The alert infrastructure itself (severity, dedup, ack) was
already solid — it just never got studio inputs.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from thursday import monitor  # noqa: E402


def _iso(hours_ago: float) -> str:
    return (datetime.now() - timedelta(hours=hours_ago)).isoformat()


def _no_records(_table: str) -> list[dict]:
    return []


def test_flagged_mix_review_generates_a_warning_alert() -> None:
    reviews = [
        {"id": "r1", "title": "Jordan Smith - Final Mix", "created_at": _iso(1), "flags": ["low-end mud", "harsh top end"]},
    ]
    alerts = monitor._check_flagged_mix_reviews(lambda: reviews)
    assert len(alerts) == 1
    assert alerts[0]["type"] == "mix_review_flagged"
    assert alerts[0]["severity"] == "warning"
    assert "2 issue(s)" in alerts[0]["message"]


def test_unflagged_mix_review_generates_no_alert() -> None:
    reviews = [{"id": "r1", "title": "Clean Mix", "created_at": _iso(1), "flags": []}]
    assert monitor._check_flagged_mix_reviews(lambda: reviews) == []


def test_old_flagged_mix_review_is_not_re_alerted() -> None:
    reviews = [{"id": "r1", "title": "Old Mix", "created_at": _iso(48), "flags": ["mud"]}]
    assert monitor._check_flagged_mix_reviews(lambda: reviews, hours=24) == []


def test_finished_render_generates_an_info_alert() -> None:
    jobs = [{"id": "job1", "status": "completed", "emotion": "joy", "finished_at": _iso(1)}]
    alerts = monitor._check_finished_renders(lambda: jobs)
    assert len(alerts) == 1
    assert alerts[0]["type"] == "render_finished"
    assert alerts[0]["severity"] == "info"
    assert "job1" in alerts[0]["message"]


def test_failed_render_generates_a_warning_alert() -> None:
    jobs = [{"id": "job2", "status": "failed", "emotion": "sad", "finished_at": _iso(1), "error": "OOM"}]
    alerts = monitor._check_finished_renders(lambda: jobs)
    assert len(alerts) == 1
    assert alerts[0]["type"] == "render_failed"
    assert alerts[0]["severity"] == "warning"
    assert "OOM" in alerts[0]["message"]


def test_running_render_generates_no_alert() -> None:
    jobs = [{"id": "job3", "status": "running", "emotion": "joy", "finished_at": ""}]
    assert monitor._check_finished_renders(lambda: jobs) == []


def test_old_finished_render_is_not_re_alerted() -> None:
    jobs = [{"id": "job4", "status": "completed", "emotion": "joy", "finished_at": _iso(48)}]
    assert monitor._check_finished_renders(lambda: jobs, hours=24) == []


def test_run_checks_degrades_gracefully_when_studio_sources_fail() -> None:
    def broken_reviews() -> list[dict]:
        raise RuntimeError("audio_analysis import failed")

    def broken_jobs() -> list[dict]:
        raise RuntimeError("audiogen_bridge import failed")

    # Must not raise — business-side checks still have to work even if
    # studio-side sources are unavailable (e.g. torch import failure).
    alerts = monitor.run_checks(_no_records, list_mix_reviews=broken_reviews, list_audiogen_jobs=broken_jobs)
    assert alerts == []


def test_run_checks_includes_studio_alerts_alongside_business_alerts(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(monitor, "ALERTS_DIR", tmp_path)
    reviews = [{"id": "r1", "title": "Flagged Mix", "created_at": _iso(1), "flags": ["mud"]}]
    jobs = [{"id": "job1", "status": "completed", "emotion": "joy", "finished_at": _iso(1)}]

    alerts = monitor.run_checks(_no_records, list_mix_reviews=lambda: reviews, list_audiogen_jobs=lambda: jobs)
    types = {a["type"] for a in alerts}
    assert "mix_review_flagged" in types
    assert "render_finished" in types
