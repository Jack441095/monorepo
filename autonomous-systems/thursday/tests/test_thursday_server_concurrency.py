"""Regression tests for per-session /ask locking (2026-09-18 audit fix).

The old global _lock serialized every /ask behind one LLM call, so a
90s grounded-specialist request blocked all other sessions. Same-session
calls must still serialize (session state); different sessions must run
in parallel; /health was and stays lock-free.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

from thursday import server as srv


def _reset_locks():
    with srv._session_locks_guard:
        srv._session_locks.clear()


def test_same_session_shares_one_lock():
    _reset_locks()
    assert srv._session_lock("s1") is srv._session_lock("s1")


def test_different_sessions_get_different_locks():
    _reset_locks()
    assert srv._session_lock("s1") is not srv._session_lock("s2")


def test_sessionless_calls_share_default_lock():
    _reset_locks()
    assert srv._session_lock("") is srv._session_lock("")


def test_lock_dict_is_capped():
    _reset_locks()
    for i in range(srv._SESSION_LOCKS_CAP + 10):
        srv._session_lock(f"flood-{i}")
    with srv._session_locks_guard:
        assert len(srv._session_locks) <= srv._SESSION_LOCKS_CAP


def _run_handle_ask(session_id: str, delay: float, record: dict):
    handler = MagicMock()
    body = {"question": "hello", "session_id": session_id}

    def fake_ask(question, session_id=""):
        record.setdefault("enter", []).append((session_id, time.monotonic()))
        time.sleep(delay)
        record.setdefault("exit", []).append((session_id, time.monotonic()))
        return {"status": "succeeded", "answer": "ok"}

    with patch("thursday.bridge.ask", side_effect=fake_ask):
        srv.Handler._handle_ask(handler, body)


def test_different_sessions_run_in_parallel():
    _reset_locks()
    record: dict = {}
    t0 = time.monotonic()
    threads = [
        threading.Thread(target=_run_handle_ask, args=(f"session-{i}", 0.4, record))
        for i in range(2)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.monotonic() - t0
    # Serial would take >= 0.8s; parallel must be well under that.
    assert elapsed < 0.7, f"different sessions serialized (took {elapsed:.2f}s)"
    enters = sorted(t for _, t in record["enter"])
    assert enters[1] - enters[0] < 0.35, "second session waited for the first"


def test_same_session_serializes():
    _reset_locks()
    record = {}
    threads = [
        threading.Thread(target=_run_handle_ask, args=("same-session", 0.3, record))
        for _ in range(2)
    ]
    t0 = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.monotonic() - t0
    assert elapsed >= 0.55, f"same session did not serialize (took {elapsed:.2f}s)"
