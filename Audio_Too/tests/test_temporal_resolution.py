"""Tests for wiring temporal reference resolution into actual use.

docs/CAPABILITY_IMPROVEMENTS_2026-07-06.md flagged that _resolve_temporal
(thursday/resolver.py) already extracted flags like "last_week"/"yesterday"
into resolved_entities every turn, but nothing consumed them. This adds
temporal_date_range() to convert those flags into an inclusive (start, end)
date range, threads it through the orchestrator's handler_ctx as
"_temporal_range", and wires client_timeline/client_summary to filter by it.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "business" / "agents"))

from thursday.resolver import temporal_date_range  # noqa: E402
from thursday.registry.handlers import _handle_client_info  # noqa: E402
from Shared.client_history import _make_timeline_events, client_summary, client_timeline  # noqa: E402

_TUESDAY = date(2026, 7, 7)  # a known weekday for stable this/last-week math


def test_yesterday_range() -> None:
    assert temporal_date_range({"yesterday": True}, today=_TUESDAY) == ("2026-07-06", "2026-07-06")


def test_today_range() -> None:
    assert temporal_date_range({"today": True}, today=_TUESDAY) == ("2026-07-07", "2026-07-07")


def test_this_week_range() -> None:
    # 2026-07-07 is a Tuesday; the week starts Monday 2026-07-06.
    assert temporal_date_range({"this_week": True}, today=_TUESDAY) == ("2026-07-06", "2026-07-07")


def test_last_week_range() -> None:
    assert temporal_date_range({"last_week": True}, today=_TUESDAY) == ("2026-06-29", "2026-07-05")


def test_this_month_range() -> None:
    assert temporal_date_range({"this_month": True}, today=_TUESDAY) == ("2026-07-01", "2026-07-07")


def test_last_month_range() -> None:
    assert temporal_date_range({"last_month": True}, today=_TUESDAY) == ("2026-06-01", "2026-06-30")


def test_last_year_range() -> None:
    assert temporal_date_range({"last_year": True}, today=_TUESDAY) == ("2025-01-01", "2025-12-31")


def test_no_supported_flag_returns_none() -> None:
    assert temporal_date_range({}, today=_TUESDAY) is None
    assert temporal_date_range({"last_time": True, "next_week": True}, today=_TUESDAY) is None


def _no_records(_table: str) -> list[dict]:
    return []


def test_timeline_events_filtered_by_date_range() -> None:
    events = [
        {"id": "1", "title": "Jordan Smith - v1", "created_at": "2026-06-15", "status": "completed", "flags": []},
        {"id": "2", "title": "Jordan Smith - v2", "created_at": "2026-07-05", "status": "completed", "flags": []},
    ]
    filtered = _make_timeline_events(
        "Jordan Smith", _no_records, list_mix_reviews=lambda: events, date_range=("2026-07-01", "2026-07-31")
    )
    assert len(filtered) == 1
    assert "v2" in filtered[0]["summary"]


def test_timeline_events_no_range_returns_everything() -> None:
    events = [
        {"id": "1", "title": "Jordan Smith - v1", "created_at": "2026-06-15", "status": "completed", "flags": []},
        {"id": "2", "title": "Jordan Smith - v2", "created_at": "2026-07-05", "status": "completed", "flags": []},
    ]
    all_events = _make_timeline_events("Jordan Smith", _no_records, list_mix_reviews=lambda: events)
    assert len(all_events) == 2


def test_client_timeline_reports_empty_range_distinctly() -> None:
    output = client_timeline(_no_records, "Jordan Smith", date_range=("2026-01-01", "2026-01-31"))
    assert "in that time range" in output


def test_client_summary_respects_date_range() -> None:
    events = [{"id": "1", "title": "Jordan Smith - old", "created_at": "2026-01-01", "status": "completed", "flags": ["mud"]}]
    output = client_summary(
        _no_records, "Jordan Smith", list_mix_reviews=lambda: events, date_range=("2026-07-01", "2026-07-31")
    )
    assert "Latest mix review:" not in output


def test_handle_client_info_passes_temporal_range_through() -> None:
    calls = {}

    class FakeApi:
        def client_summary(self, list_records, name, *, date_range=None):
            calls["summary"] = (name, date_range)
            return f"Client: {name}"

        def client_timeline(self, list_records, name, *, date_range=None):
            calls["timeline"] = (name, date_range)
            return f"Timeline: {name}"

    ctx = {"_list_records": _no_records, "_temporal_range": ("2026-06-01", "2026-06-30")}
    result = _handle_client_info(FakeApi(), "tell me about Jordan last month", ctx)
    assert result == "Client: Jordan"
    assert calls["summary"] == ("Jordan", ("2026-06-01", "2026-06-30"))

    result = _handle_client_info(FakeApi(), "show me the timeline for Jordan last month", ctx)
    assert result == "Timeline: Jordan"
    assert calls["timeline"] == ("Jordan", ("2026-06-01", "2026-06-30"))


def test_handle_client_info_works_without_temporal_range() -> None:
    class FakeApi:
        def client_summary(self, list_records, name, *, date_range=None):
            assert date_range is None
            return f"Client: {name}"

    ctx = {"_list_records": _no_records}
    result = _handle_client_info(FakeApi(), "tell me about Jordan", ctx)
    assert result == "Client: Jordan"
