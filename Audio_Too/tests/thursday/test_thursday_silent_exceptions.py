"""Silent-exception observability regression tests (audit fix Stage 4, 2026-07-08).

docs/THURSDAY_ORCHESTRATOR_AUDIT_2026-07-08.md P1: 73 bare `except Exception:` sites
in thursday/*.py, including 8 around `save_session()` -- a swallowed failure there
silently loses conversation state with zero visibility. This tests that the
highest-risk sites (session save/load on the critical path, per the execution
plan's tier a/b classification) now log instead of silently passing, without
changing the graceful-degradation behavior itself.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from thursday import orchestrator, session_manager  # noqa: E402
from thursday.session_manager import get_or_create_session  # noqa: E402


def test_save_session_failure_is_logged_not_silent(monkeypatch, caplog) -> None:
    def broken_save(_session: dict) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(orchestrator, "save_session", broken_save)
    # A fresh, unique ID every run: session state persists in a real DB
    # across pytest invocations, and a fixed literal ID here previously left
    # stale feedback_state (recorded=False, a real turn_id) from an earlier
    # run -- that stale state skipped this function's early-return guard and
    # let the broken save_session() propagate uncaught instead of being
    # exercised as a fresh "no feedback pending" greeting turn (found
    # 2026-07-12: passed in isolation, failed only inside a broader sweep
    # whose collection-order shift finally surfaced the two-day-old
    # leftover state).
    session = get_or_create_session(f"test-silent-exc-save-{uuid.uuid4().hex}")

    import logging
    caplog.set_level(logging.WARNING, logger="thursday.orchestrator")
    # A greeting turn exercises one of the save_session try/except sites directly.
    result = orchestrator.handle("hello", session, list_records=lambda _t: [])

    assert result  # behavior is unchanged -- still returns a graceful response
    assert any("save_session failed" in r.message for r in caplog.records), (
        "save_session failure must be logged, not silently swallowed"
    )


def test_load_session_failure_is_logged_not_silent(monkeypatch, caplog) -> None:
    def broken_get_db():
        raise RuntimeError("db locked")

    monkeypatch.setattr(session_manager, "_get_db", broken_get_db)

    import logging
    caplog.set_level(logging.WARNING, logger="thursday.session_manager")
    result = session_manager.load_session("nonexistent-session-id-format-ok-12345678")

    assert result is None  # behavior unchanged -- still degrades to None
    assert any("load_session failed" in r.message for r in caplog.records)


def test_resolve_request_failure_is_logged_and_falls_back(monkeypatch, caplog) -> None:
    def broken_resolve(_text, _context):
        raise RuntimeError("resolver exploded")

    monkeypatch.setattr(orchestrator, "resolve_request", broken_resolve)

    import logging
    caplog.set_level(logging.WARNING, logger="thursday.orchestrator")
    decision = orchestrator.classify_request(
        "some text", get_or_create_session(f"test-silent-exc-resolve-{uuid.uuid4().hex}")
    )

    assert decision.resolved_text == "some text"  # falls back to raw text, unchanged
    assert any("resolve_request failed" in r.message for r in caplog.records)
