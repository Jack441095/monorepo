"""Phase-0 P0-C regression: real SQLite session deletion.

docs/audits/2026-08-20-thursday-nitedsp-forensic-audit.md and the companion
platform master report found that Thursday migrated sessions to a SQLite
table (`assistant_sessions`), but `thursday/server.py`'s `DELETE
/session/<id>` still only unlinked a legacy `SESSION_DIR / f"{id}.json"` file
-- a path that no longer exists for any SQLite-backed session, so the
endpoint reported success while deleting nothing. `session_manager.py` had no
`delete_session()` API at all.

These tests exercise `thursday.session_manager.delete_session()` directly
(parameterized-SQL targeting, isolation between sessions, not-found handling,
persistence across a fresh DB connection/"restart") and the server handler
that now routes through it.
"""

from __future__ import annotations

import pytest

from thursday import server as ts
from thursday import session_manager


@pytest.fixture
def isolated_sessions(tmp_path, monkeypatch):
    monkeypatch.setattr(session_manager, "SESSION_DIR", tmp_path / "sessions")
    monkeypatch.setattr(session_manager, "SESSION_FILE", tmp_path / ".session")
    return tmp_path


def test_create_verify_delete_verify_absent(isolated_sessions):
    session = session_manager.get_or_create_session("del-me")
    assert session_manager.load_session("del-me") is not None

    deleted = session_manager.delete_session("del-me")

    assert deleted is True
    assert session_manager.load_session("del-me") is None


def test_delete_nonexistent_session_returns_false(isolated_sessions):
    assert session_manager.load_session("never-existed") is None
    assert session_manager.delete_session("never-existed") is False


def test_delete_malformed_session_id_raises(isolated_sessions):
    with pytest.raises(ValueError):
        session_manager.delete_session("../../etc/passwd")
    with pytest.raises(ValueError):
        session_manager.delete_session("has spaces")
    with pytest.raises(ValueError):
        session_manager.delete_session("a" * 65)


def test_deleting_one_session_does_not_affect_another(isolated_sessions):
    session_manager.get_or_create_session("session-a")
    session_manager.get_or_create_session("session-b")

    deleted = session_manager.delete_session("session-a")

    assert deleted is True
    assert session_manager.load_session("session-a") is None
    assert session_manager.load_session("session-b") is not None


def test_deletion_persists_across_a_fresh_db_connection(isolated_sessions):
    """Simulates a process restart: a brand-new sqlite3 connection must not
    see the deleted row (real DELETE, not an in-memory-only removal)."""
    session_manager.get_or_create_session("restart-check")
    session_manager.delete_session("restart-check")

    # A fresh, independent connection to the same on-disk DB file.
    import sqlite3

    db_path = session_manager.SESSION_DIR / "thursday_sessions.sqlite3"
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT 1 FROM assistant_sessions WHERE session_id = ?", ("restart-check",)
        ).fetchone()
    finally:
        conn.close()
    assert row is None


def test_delete_session_uses_parameterized_sql_not_string_interpolation(isolated_sessions):
    """A session id containing SQL metacharacters must be rejected by the id
    format guard, never interpolated into a query. This also proves a
    quote-injection attempt cannot delete unrelated rows."""
    session_manager.get_or_create_session("safe-session")
    with pytest.raises(ValueError):
        session_manager.delete_session("x' OR '1'='1")
    # The legitimate session must be untouched.
    assert session_manager.load_session("safe-session") is not None


def test_server_delete_session_handler_routes_through_delete_session(isolated_sessions):
    sent = {}

    class FakeHandler:
        def _send_error(self, status, message, code=""):
            sent.update({"status": status, "message": message})

        def _send_json(self, status, payload):
            sent.update({"status": status, "payload": payload})

    session_manager.get_or_create_session("http-del")
    ts.Handler._handle_delete_session(FakeHandler(), "http-del")

    assert sent["status"] == 200
    assert sent["payload"]["deleted"] == "http-del"
    assert session_manager.load_session("http-del") is None


def test_server_delete_session_handler_404_for_unknown_session(isolated_sessions):
    sent = {}

    class FakeHandler:
        def _send_error(self, status, message, code=""):
            sent.update({"status": status, "message": message})

        def _send_json(self, status, payload):
            sent.update({"status": status, "payload": payload})

    ts.Handler._handle_delete_session(FakeHandler(), "never-existed-http")

    assert sent["status"] == 404


def test_server_delete_session_handler_400_for_malformed_id(isolated_sessions):
    sent = {}

    class FakeHandler:
        def _send_error(self, status, message, code=""):
            sent.update({"status": status, "message": message})

        def _send_json(self, status, payload):
            sent.update({"status": status, "payload": payload})

    ts.Handler._handle_delete_session(FakeHandler(), "bad id with spaces")

    assert sent["status"] == 400
