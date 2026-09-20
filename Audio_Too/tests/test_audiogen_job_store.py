"""Durability, leasing, and recovery tests for AudioGen render jobs."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server" / "app"))

import audiogen_job_store as store  # noqa: E402
import db  # noqa: E402
import event_store  # noqa: E402


@pytest.fixture()
def job_store(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "audio_too.db")
    monkeypatch.setattr(db, "AGENT_DATA", tmp_path / "legacy-json")
    monkeypatch.setattr(db, "_migration_done", False)
    store.reset_connection_state()
    store.ensure_schema()
    yield
    store.reset_connection_state()


def queued_job() -> dict:
    return store.create(
        emotion="joy",
        bars=4,
        candidate_count=2,
        publish=False,
        project_id="project-1",
    )


def test_claim_is_atomic_and_records_lifecycle_events(job_store) -> None:
    created = queued_job()

    claimed = store.claim_next("worker-1")
    second_claim = store.claim_next("worker-2")

    assert claimed is not None
    assert claimed["id"] == created["id"]
    assert claimed["status"] == "running"
    assert claimed["worker_id"] == "worker-1"
    assert claimed["attempt"] == 1
    assert second_claim is None
    assert [event["status"] for event in store.events(created["id"])] == [
        "queued",
        "running",
    ]
    assert [
        event["event_type"]
        for event in event_store.list_for_correlation(f"audiogen-job:{created['id']}")
    ] == ["audiogen.job.queued", "audiogen.job.running"]


def test_only_lease_owner_can_heartbeat_or_finish(job_store) -> None:
    created = queued_job()
    store.claim_next("worker-1")

    assert store.heartbeat(created["id"], "worker-2", progress=80) is False
    assert store.finish(
        created["id"],
        "worker-2",
        status="completed",
        message="Wrong owner.",
        result={"ok": True},
    )["status"] == "running"

    assert store.heartbeat(created["id"], "worker-1", progress=65) is True
    finished = store.finish(
        created["id"],
        "worker-1",
        status="completed",
        message="Complete.",
        result={"ok": True, "src": "/audio/test.wav"},
    )
    assert finished["status"] == "completed"
    assert finished["progress"] == 100
    assert finished["result"]["src"] == "/audio/test.wav"


def test_expired_lease_is_requeued_for_restart_recovery(job_store) -> None:
    created = queued_job()
    store.claim_next("dead-worker", lease_seconds=1)
    with db.connect() as conn:
        conn.execute(
            "UPDATE audiogen_jobs SET lease_expiry_at = ? WHERE id = ?",
            ("2020-01-01T00:00:00Z", created["id"]),
        )
        conn.commit()

    assert store.recover_expired(now_text="2026-07-02T12:00:00Z") == 1
    recovered = store.get(created["id"])
    assert recovered["status"] == "queued"
    assert recovered["worker_id"] == ""
    assert "recovered" in recovered["message"].lower()

    reclaimed = store.claim_next("replacement-worker")
    assert reclaimed["id"] == created["id"]
    assert reclaimed["attempt"] == 2


def test_recovery_fails_job_after_attempt_limit(job_store) -> None:
    created = queued_job()
    store.claim_next("dead-worker")
    with db.connect() as conn:
        conn.execute(
            """UPDATE audiogen_jobs SET attempt = max_attempts, lease_expiry_at = ?
               WHERE id = ?""",
            ("2020-01-01T00:00:00Z", created["id"]),
        )
        conn.commit()

    store.recover_expired(now_text="2026-07-02T12:00:00Z")
    failed = store.get(created["id"])
    assert failed["status"] == "failed"
    assert failed["progress"] == 100
    assert "recovery limit" in failed["message"].lower()


def test_cancel_is_idempotent_for_queued_and_terminal_jobs(job_store) -> None:
    created = queued_job()
    first = store.request_cancel(created["id"])
    second = store.request_cancel(created["id"])

    assert first["status"] == "cancelled"
    assert second["status"] == "cancelled"
    assert len([event for event in store.events(created["id"]) if event["status"] == "cancelled"]) == 1


def test_create_defaults_chain_fields_to_off(job_store) -> None:
    created = queued_job()

    assert created["genre"] == ""
    assert created["style_prefs"] == {}
    assert created["chain_to_automix"] is False
    assert created["automix_job_id"] == ""


def test_create_persists_chain_to_automix_request(job_store) -> None:
    created = store.create(
        emotion="joy",
        bars=4,
        candidate_count=1,
        publish=False,
        project_id="project-1",
        genre="pop",
        style_prefs={"masking_corrections": True},
        chain_to_automix=True,
    )

    assert created["genre"] == "pop"
    assert created["style_prefs"] == {"masking_corrections": True}
    assert created["chain_to_automix"] is True

    reloaded = store.get(created["id"])
    assert reloaded["genre"] == "pop"
    assert reloaded["style_prefs"] == {"masking_corrections": True}
    assert reloaded["chain_to_automix"] is True


def test_set_automix_job_id_links_the_two_jobs(job_store) -> None:
    created = queued_job()

    store.set_automix_job_id(created["id"], "automix-job-abc")

    assert store.get(created["id"])["automix_job_id"] == "automix-job-abc"
