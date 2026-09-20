"""Append-only domain event and correlation tests."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server" / "app"))

import db  # noqa: E402
import event_store  # noqa: E402


@pytest.fixture()
def events(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "audio_too.db")
    monkeypatch.setattr(db, "AGENT_DATA", tmp_path / "legacy-json")
    monkeypatch.setattr(db, "_migration_done", False)
    event_store.reset_connection_state()
    event_store.ensure_schema()
    yield
    event_store.reset_connection_state()


def test_events_are_versioned_ordered_and_correlated(events) -> None:
    first = event_store.append(
        event_type="render.queued",
        aggregate_type="job",
        aggregate_id="job-1",
        project_id="project-1",
        correlation_id="render:job-1",
        actor_id="audiogen",
        payload={"status": "queued"},
    )
    second = event_store.append(
        event_type="render.completed",
        aggregate_type="job",
        aggregate_id="job-1",
        project_id="project-1",
        correlation_id="render:job-1",
        causation_id=first["id"],
        actor_id="audiogen",
        payload={"status": "completed"},
    )

    correlated = event_store.list_for_correlation("render:job-1")
    assert [item["id"] for item in correlated] == [first["id"], second["id"]]
    assert correlated[1]["causation_id"] == first["id"]
    assert correlated[1]["schema_version"] == 1
    assert event_store.list_for_project("project-1")[0]["event_type"] == "render.completed"


def test_event_write_rolls_back_with_callers_transaction(events) -> None:
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        event_store.append_in_transaction(
            conn,
            event_type="artifact.registered",
            aggregate_type="artifact",
            aggregate_id="artifact-1",
            actor_id="test",
            project_id="project-1",
        )
        conn.rollback()
    assert event_store.list_for_project("project-1") == []


def test_event_rows_are_append_only(events) -> None:
    event = event_store.append(
        event_type="artifact.registered",
        aggregate_type="artifact",
        aggregate_id="artifact-1",
        actor_id="test",
    )
    with db.connect() as conn:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute("UPDATE domain_events SET event_type = 'changed' WHERE id = ?", (event["id"],))
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute("DELETE FROM domain_events WHERE id = ?", (event["id"],))


def test_event_payload_rejects_non_json_and_unbounded_content(events) -> None:
    with pytest.raises(event_store.EventStoreError, match="finite JSON"):
        event_store.append(
            event_type="test.event",
            aggregate_type="test",
            aggregate_id="test-1",
            actor_id="test",
            payload={"bad": float("nan")},
        )
    with pytest.raises(event_store.EventStoreError, match="64 KiB"):
        event_store.append(
            event_type="test.event",
            aggregate_type="test",
            aggregate_id="test-1",
            actor_id="test",
            payload={"large": "x" * (65 * 1024)},
        )


def test_event_payload_rejects_secrets_and_private_paths(events) -> None:
    for payload in (
        {"password": "do-not-store"},
        {"nested": {"session_token": "do-not-store"}},
        {"wav_path": "/private/client.wav"},
    ):
        with pytest.raises(event_store.EventStoreError, match="restricted"):
            event_store.append(
                event_type="test.event",
                aggregate_type="test",
                aggregate_id="test-1",
                actor_id="test",
                payload=payload,
            )
