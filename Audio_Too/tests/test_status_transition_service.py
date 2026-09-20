"""Tests for the typed admin status-transition service.

Covers the optimistic-version contract, the allowlist (worker-managed tables
rejected), and that every transition appends a `record.status_changed` event —
the properties the raw `update_status` route handler lacked.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BUSINESS_APP = Path(__file__).resolve().parent.parent / "server" / "app"
if str(BUSINESS_APP) not in sys.path:
    sys.path.insert(0, str(BUSINESS_APP))

import db  # noqa: E402
import status_transition_service as sts  # noqa: E402


@pytest.fixture()
def temp_db(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "audio_too.db")
    monkeypatch.setattr(db, "AGENT_DATA", tmp_path / "legacy-json")
    db.init_db()
    return db


def _make(table: str, **fields) -> dict:
    return db.add_record(table, fields)


def _events(conn_table: str, aggregate_id: str) -> list[dict]:
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT * FROM domain_events WHERE aggregate_type = ? AND aggregate_id = ?",
            (conn_table, aggregate_id),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def test_transition_updates_status_bumps_version_and_emits_event(temp_db):
    rec = _make("leads", name="Ada", status="New")
    req = sts.StatusTransitionRequest.from_payload({"table": "leads", "id": rec["id"], "status": "Warm"})
    out = sts.transition_status(req)

    assert out["status"] == "Warm"
    assert out["optimistic_version"] == int(rec["optimistic_version"]) + 1
    events = _events("leads", rec["id"])
    assert len(events) == 1
    assert events[0]["event_type"] == "record.status_changed"


def test_optimistic_version_conflict_raises_409(temp_db):
    rec = _make("projects", name="LP", status="open")
    stored = int(rec["optimistic_version"])
    req = sts.StatusTransitionRequest.from_payload(
        {"table": "projects", "id": rec["id"], "status": "Closed", "expected_version": stored + 5}
    )
    with pytest.raises(sts.StatusTransitionError) as exc:
        sts.transition_status(req)
    assert exc.value.status_code == 409
    # unchanged on conflict (transaction rolled back)
    conn = db.connect()
    try:
        row = conn.execute("SELECT status FROM projects WHERE id = ?", (rec["id"],)).fetchone()
    finally:
        conn.close()
    assert row["status"] == "open"
    assert not _events("projects", rec["id"])  # no event on a rejected transition


def test_matching_expected_version_succeeds(temp_db):
    rec = _make("projects", name="EP", status="open")
    req = sts.StatusTransitionRequest.from_payload(
        {"table": "projects", "id": rec["id"], "status": "Closed",
         "expected_version": int(rec["optimistic_version"])}
    )
    out = sts.transition_status(req)
    assert out["status"] == "Closed"


def test_worker_managed_table_is_rejected(temp_db):
    with pytest.raises(sts.StatusTransitionError) as exc:
        sts.StatusTransitionRequest.from_payload({"table": "automix_jobs", "id": "j1", "status": "complete"})
    assert exc.value.status_code == 400
    assert "automix_jobs" not in sts.ALLOWED_TABLES


def test_unknown_record_raises_404(temp_db):
    req = sts.StatusTransitionRequest.from_payload({"table": "clients", "id": "nope", "status": "Active"})
    with pytest.raises(sts.StatusTransitionError) as exc:
        sts.transition_status(req)
    assert exc.value.status_code == 404


def test_non_versioned_table_transitions_without_version(temp_db):
    # campaigns has a status but no optimistic_version — must still work + emit event.
    rec = _make("campaigns", name="Spring", status="Planned")
    req = sts.StatusTransitionRequest.from_payload({"table": "campaigns", "id": rec["id"], "status": "Active"})
    out = sts.transition_status(req)
    assert out["status"] == "Active"
    assert len(_events("campaigns", rec["id"])) == 1


def test_invalid_status_rejected(temp_db):
    for bad in ("", "x" * 41):
        with pytest.raises(sts.StatusTransitionError) as exc:
            sts.StatusTransitionRequest.from_payload({"table": "clients", "id": "c1", "status": bad})
        assert exc.value.status_code == 400
