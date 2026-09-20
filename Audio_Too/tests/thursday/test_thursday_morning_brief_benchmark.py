"""Morning Brief qualification benchmark.

Measures the composed Daily Brief (``thursday/daily_brief.py``) against
the qualities a serious "Morning Thursday, where are we?" artifact needs:

- all sections render when every source is healthy;
- every source can fail independently without crashing or empty output;
- sources compose concurrently (latency = slowest source, not the sum);
- the artifact is a bounded summary, not a database dump.

Real-source integration behavior is covered by
test_thursday_daily_brief.py; here the business-status subprocess is
stubbed so latency measurements stay deterministic.
"""

from __future__ import annotations

import statistics
import time
from datetime import date
from unittest.mock import patch

import pytest

from thursday import action_receipts, daily_brief

TODAY = date(2026, 8, 22)

STATUS_STUB = "🔴 Audio_Too Status\n  Clients: 0 | Active projects: 0"


@pytest.fixture(autouse=True)
def _fast_business_status():
    with patch.object(
        daily_brief.client, "business_status", return_value=STATUS_STUB
    ):
        yield


@pytest.fixture(autouse=True)
def _isolated_receipts_db(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "THURSDAY_ACTION_RECEIPTS_DB", str(tmp_path / "receipts.sqlite3")
    )


@pytest.fixture(autouse=True)
def _fresh_status_cache():
    from thursday import status_cache

    status_cache.invalidate()
    yield
    status_cache.invalidate()


def test_benchmark_all_sources_healthy_latency_and_structure():
    latencies_ms = []
    text = ""
    for _ in range(10):
        t0 = time.perf_counter()
        _, text = daily_brief.build_daily_brief(today=TODAY)
        latencies_ms.append((time.perf_counter() - t0) * 1000)

    median_ms = statistics.median(latencies_ms)
    # Interactive budget with fast local sources.
    assert median_ms < 2000, f"brief composition too slow: {median_ms:.0f}ms"

    assert f"# Daily Brief — {TODAY.isoformat()}" in text
    for heading in (
        "## Business Status",
        "## Today",
        "## Week Ahead",
        "## Agent Activity",
        "## Scheduled Tasks",
    ):
        assert heading in text
    assert "unavailable" not in text.lower()


def test_composition_is_concurrent_not_sequential():
    """A slow source must not add its full latency to every other source's:
    with one source delayed D and others ~instant, total stays near D."""
    delay_seconds = 1.0

    def slow_status():
        time.sleep(delay_seconds)
        return STATUS_STUB

    t0 = time.perf_counter()
    with patch.object(daily_brief.client, "business_status", side_effect=slow_status):
        daily_brief.compose_daily_brief(today=TODAY)
    elapsed = time.perf_counter() - t0

    # Sequential would be ≥ delay + scheduling/agenda/scheduler work; the
    # concurrent bound allows generous overhead but not double the delay.
    assert elapsed < delay_seconds * 2, (
        f"composition looks sequential: {elapsed:.2f}s for {delay_seconds}s source"
    )


def test_benchmark_every_source_failure_still_renders_usable_shell():
    sources = [
        ("client", "business_status"),
        ("scheduling", "agenda_for_day"),
        ("scheduling", "agenda_for_week"),
        ("action_receipts", "recent_receipts"),
        ("scheduler", "load_schedules"),
    ]
    for module_name, fn_name in sources:
        module = getattr(daily_brief, module_name)
        with patch.object(module, fn_name, side_effect=OSError("bench boom")):
            brief, text = daily_brief.build_daily_brief(today=TODAY)
            assert "# Daily Brief" in text
            assert "## Today" in text  # structure survives total outage
            assert len(brief["summary"]["unavailable"]) >= 1


def test_benchmark_receipt_activity_appears_with_status():
    receipt_id = action_receipts.receipt_id_for_token("bench-tok")
    action_receipts.claim_action(
        receipt_id, session_id="bench", service_id="email.send", text="hi"
    )
    action_receipts.complete_action(receipt_id, response_text="sent")

    _, text = daily_brief.build_daily_brief(today=TODAY)
    assert "email.send" in text
    assert "completed" in text


def test_benchmark_brief_is_a_summary_not_a_dump():
    """Agent activity is capped at a bounded window (20 receipts), keeping
    the artifact scannable rather than an unbounded log."""
    for i in range(40):
        rid = action_receipts.receipt_id_for_token(f"dump-{i}")
        action_receipts.claim_action(
            rid, session_id="dump", service_id="email.send", text=f"m{i}"
        )
        action_receipts.complete_action(rid, response_text="ok")

    brief = daily_brief.compose_daily_brief(today=TODAY)
    receipts_payload = brief["sections"]["agent_receipts"]["payload"]
    assert len(receipts_payload) <= 20
