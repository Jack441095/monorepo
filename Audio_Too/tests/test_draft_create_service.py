"""Tests for the typed draft-create service (draft_service.create_draft).

Covers the properties the raw `add_record("drafts", ...)` handler lacked:
a typed/validated schema, idempotent replay, and a `draft.created` domain event.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BUSINESS_APP = Path(__file__).resolve().parent.parent / "server" / "app"
if str(BUSINESS_APP) not in sys.path:
    sys.path.insert(0, str(BUSINESS_APP))

import db  # noqa: E402
import draft_service  # noqa: E402
from api_schemas import DraftCreateRequest, SchemaValidationError  # noqa: E402


@pytest.fixture()
def temp_db(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "audio_too.db")
    monkeypatch.setattr(db, "AGENT_DATA", tmp_path / "legacy-json")
    db.init_db()
    return db


def _events(aggregate_id: str) -> list[dict]:
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT * FROM domain_events WHERE aggregate_type = 'drafts' AND aggregate_id = ?",
            (aggregate_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _req(**over) -> DraftCreateRequest:
    payload = {"type": "email", "recipient": "a@b.com", "subject": "Hi", "body": "Body", "source": "admin"}
    payload.update(over)
    return DraftCreateRequest.from_payload(payload)


def test_create_draft_persists_pending_and_emits_event(temp_db):
    status, result = draft_service.create_draft(_req())
    assert status == 201
    draft = result["draft"]
    assert draft["status"] == "Pending"
    assert draft["recipient"] == "a@b.com"
    assert draft["optimistic_version"] == 1
    events = _events(draft["id"])
    assert len(events) == 1 and events[0]["event_type"] == "draft.created"

    stored = [d for d in db.list_records("drafts") if d["id"] == draft["id"]]
    assert len(stored) == 1


def test_idempotent_replay_does_not_duplicate(temp_db):
    status1, r1 = draft_service.create_draft(_req(), idempotency_key="k-1")
    status2, r2 = draft_service.create_draft(_req(), idempotency_key="k-1")
    assert status1 == 201
    # Replayed: same draft returned, only one row + one event.
    assert r2["draft"]["id"] == r1["draft"]["id"]
    assert len(db.list_records("drafts")) == 1
    assert len(_events(r1["draft"]["id"])) == 1


def test_oversized_subject_rejected_by_schema():
    with pytest.raises(SchemaValidationError):
        DraftCreateRequest.from_payload({"subject": "x" * 301})


def test_defaults_applied():
    req = DraftCreateRequest.from_payload({})
    assert req.type == "message"
    assert req.source == "admin"
    assert req.recipient == ""
