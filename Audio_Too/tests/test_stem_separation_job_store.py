"""Durability, leasing, and recovery tests for stem-separation jobs.

Mirrors tests/test_audiogen_job_store.py's structure/coverage, adapted to
this subsystem's simpler schema (source file + model instead of
emotion/bars/style_prefs).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server" / "app"))

import stem_separation_job_store as store  # noqa: E402
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
    return store.create(source_filename="mix.wav", model="htdemucs", project_id="project-1")


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
    assert [event["status"] for event in _events(created["id"])] == ["queued", "running"]
    assert [
        event["event_type"]
        for event in event_store.list_for_correlation(f"stem-separation-job:{created['id']}")
    ] == ["stem_separation.job.queued", "stem_separation.job.running"]


def _events(job_id: str) -> list[dict]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM stem_separation_job_events WHERE job_id = ? ORDER BY created_at, rowid",
            (job_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def test_only_lease_owner_can_heartbeat_or_finish(job_store) -> None:
    created = queued_job()
    store.claim_next("worker-1")

    assert store.heartbeat(created["id"], "worker-2", progress=80) is False
    assert store.finish(
        created["id"], "worker-2", status="completed", message="Wrong owner.", result={"ok": True},
    )["status"] == "running"

    assert store.heartbeat(created["id"], "worker-1", progress=65) is True
    finished = store.finish(
        created["id"], "worker-1", status="completed", message="Complete.",
        result={"stems": {"drums": "/tmp/drums.wav"}},
    )
    assert finished["status"] == "completed"
    assert finished["progress"] == 100
    assert finished["result"]["stems"]["drums"] == "/tmp/drums.wav"


def test_expired_lease_is_requeued_for_restart_recovery(job_store) -> None:
    created = queued_job()
    store.claim_next("dead-worker", lease_seconds=1)
    with db.connect() as conn:
        conn.execute(
            "UPDATE stem_separation_jobs SET lease_expiry_at = '2000-01-01T00:00:00Z' WHERE id = ?",
            (created["id"],),
        )
        conn.commit()

    recovered = store.recover_expired()
    job = store.get(created["id"])

    assert recovered == 1
    assert job["status"] == "queued"
    assert job["worker_id"] == ""


def test_source_path_can_be_set_after_create(job_store) -> None:
    created = queued_job()
    store.set_source_path(created["id"], "/data/stem_separation_jobs/abc/source.wav")
    assert store.get(created["id"])["source_path"] == "/data/stem_separation_jobs/abc/source.wav"


def test_finish_rejects_non_terminal_status(job_store) -> None:
    created = queued_job()
    store.claim_next("worker-1")
    with pytest.raises(ValueError):
        store.finish(created["id"], "worker-1", status="running", message="nope")


def test_trim_removes_oldest_terminal_jobs_first(job_store) -> None:
    ids = []
    for _ in range(5):
        job = queued_job()
        store.claim_next("worker-1")
        store.finish(job["id"], "worker-1", status="completed", message="done", result={"stems": {}})
        ids.append(job["id"])

    removed = store.trim(max_history=2)

    assert removed == 3
    remaining_ids = {job["id"] for job in store.recent(limit=10)}
    assert remaining_ids == set(ids[-2:])


def test_get_latest_completed_for_project_returns_none_when_nothing_completed(job_store) -> None:
    # G3 (docs/KENN_IMPROVEMENT_PLAN.md): a queued-but-not-yet-completed
    # job must not be returned -- there's no stem set to resolve yet.
    queued_job()
    assert store.get_latest_completed_for_project("project-1") is None


def test_get_latest_completed_for_project_returns_the_newest(job_store) -> None:
    job1 = queued_job()
    store.claim_next("worker-1")
    store.finish(job1["id"], "worker-1", status="completed", message="done", result={"stems": {"drums": "/tmp/a.wav"}})

    job2 = queued_job()
    store.claim_next("worker-1")
    store.finish(job2["id"], "worker-1", status="completed", message="done", result={"stems": {"drums": "/tmp/b.wav"}})

    latest = store.get_latest_completed_for_project("project-1")
    assert latest["id"] == job2["id"]


def test_get_latest_completed_for_project_ignores_other_projects(job_store) -> None:
    other = store.create(source_filename="mix.wav", model="htdemucs", project_id="project-other")
    store.claim_next("worker-1")
    store.finish(other["id"], "worker-1", status="completed", message="done", result={"stems": {"drums": "/tmp/a.wav"}})

    assert store.get_latest_completed_for_project("project-1") is None


def test_get_latest_completed_for_project_noops_on_empty_project_id(job_store) -> None:
    assert store.get_latest_completed_for_project("") is None
