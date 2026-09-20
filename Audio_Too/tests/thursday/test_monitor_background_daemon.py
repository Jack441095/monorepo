"""Proactive checks (stale leads, overdue invoices, expiring links, flagged
mix reviews, finished renders) previously only ever fired inline from
orchestrator.py's handle() when a user happened to talk to Thursday and
CHECK_INTERVAL_MINUTES had elapsed -- if nobody talks to Thursday, checks
never ran at all. start_background_monitor() runs them on their own
schedule instead (P2 fix, 2026-07-13)."""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import thursday.monitor as monitor  # noqa: E402


def test_start_background_monitor_returns_running_daemon_thread(monkeypatch):
    monkeypatch.setattr(monitor, "should_check", lambda *a, **k: False)

    thread, stop_event = monitor.start_background_monitor(poll_seconds=0.01)
    try:
        assert thread.is_alive()
        assert thread.daemon is True
    finally:
        stop_event.set()
        thread.join(timeout=2)
    assert not thread.is_alive()


def test_monitor_loop_calls_run_checks_when_due(monkeypatch):
    calls = []
    monkeypatch.setattr(monitor, "should_check", lambda *a, **k: True)
    monkeypatch.setattr(monitor, "run_checks", lambda list_records: calls.append(1) or [])
    monkeypatch.setattr(monitor, "mark_checked", lambda: None)
    monkeypatch.setattr(monitor, "_resolve_list_records", lambda: (lambda _: []))

    thread, stop_event = monitor.start_background_monitor(poll_seconds=0.01)
    try:
        deadline = time.monotonic() + 2
        while not calls and time.monotonic() < deadline:
            time.sleep(0.01)
        assert calls, "run_checks() was never called by the background loop"
    finally:
        stop_event.set()
        thread.join(timeout=2)


def test_monitor_loop_skips_run_checks_when_not_due(monkeypatch):
    calls = []
    monkeypatch.setattr(monitor, "should_check", lambda *a, **k: False)
    monkeypatch.setattr(monitor, "run_checks", lambda list_records: calls.append(1) or [])

    thread, stop_event = monitor.start_background_monitor(poll_seconds=0.01)
    try:
        time.sleep(0.1)
    finally:
        stop_event.set()
        thread.join(timeout=2)
    assert calls == []


def test_monitor_loop_survives_run_checks_exception(monkeypatch):
    mark_checked_calls = []
    monkeypatch.setattr(monitor, "should_check", lambda *a, **k: True)

    def boom(list_records):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(monitor, "run_checks", boom)
    monkeypatch.setattr(monitor, "mark_checked", lambda: mark_checked_calls.append(1))
    monkeypatch.setattr(monitor, "_resolve_list_records", lambda: (lambda _: []))

    thread, stop_event = monitor.start_background_monitor(poll_seconds=0.01)
    try:
        deadline = time.monotonic() + 2
        while not mark_checked_calls and time.monotonic() < deadline:
            time.sleep(0.01)
        assert mark_checked_calls  # finally-block still ran despite run_checks() raising
        assert thread.is_alive()  # loop did not die from the exception
    finally:
        stop_event.set()
        thread.join(timeout=2)


def test_resolve_list_records_falls_back_when_app_db_unavailable(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "app.db":
            raise ImportError("no app.db here")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    fn = monitor._resolve_list_records()
    assert fn("leads") == []
