"""Transactional storage for durable stem-separation (Demucs) jobs.

Mirrors audiogen_job_store.py's shape (schema/claim/heartbeat/finish/recover)
adapted to this subsystem's simpler fields (no emotion/bars/style_prefs --
just a source file, a model choice, and a result stem-path map).
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import db
import event_store

TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
_SCHEMA_LOCK = threading.Lock()
_READY_DB: Path | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _lease_after(seconds: float) -> str:
    value = datetime.now(timezone.utc) + timedelta(seconds=max(1.0, seconds))
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def ensure_schema() -> None:
    global _READY_DB
    current = Path(db.DB_PATH)
    if _READY_DB == current:
        return
    with _SCHEMA_LOCK:
        if _READY_DB == current:
            return
        db.init_db()
        _READY_DB = current


def reset_connection_state() -> None:
    """Forget the initialized path; intended for tests that replace ``db.DB_PATH``."""
    global _READY_DB
    _READY_DB = None


def _event(conn, job_id: str, status: str, message: str, progress: int, worker_id: str = "", project_id: str = "") -> None:
    conn.execute(
        """INSERT INTO stem_separation_job_events
           (id, job_id, status, message, progress, worker_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (uuid4().hex, job_id, status, message, progress, worker_id, _now()),
    )
    event_store.append_in_transaction(
        conn,
        event_type=f"stem_separation.job.{status}",
        aggregate_type="job",
        aggregate_id=job_id,
        project_id=project_id,
        correlation_id=f"stem-separation-job:{job_id}",
        actor_id=worker_id or "stem_separation",
        payload={"status": status, "progress": progress, "message": message},
    )


def _decode(row) -> dict | None:
    if row is None:
        return None
    item = dict(row)
    raw_result = item.pop("result_json", None)
    try:
        result = json.loads(raw_result) if raw_result else None
    except json.JSONDecodeError:
        result = None
    raw_style_prefs = item.get("style_prefs") or ""
    try:
        style_prefs = json.loads(raw_style_prefs) if raw_style_prefs else {}
    except json.JSONDecodeError:
        style_prefs = {}
    return {
        "id": item["id"],
        "status": item["status"],
        "source_filename": item["source_filename"],
        "source_path": item["source_path"],
        "model": item["model"],
        "project_id": item["project_id"],
        "progress": item["progress"],
        "message": item["message"],
        "created_at": item["created_at"],
        "started_at": item.get("started_at") or "",
        "finished_at": item.get("finished_at") or "",
        "result": result,
        "error": item["error"],
        "worker_id": item.get("worker_id") or "",
        "attempt": item["attempt"],
        "max_attempts": item["max_attempts"],
        "heartbeat_at": item.get("heartbeat_at") or "",
        "lease_expiry_at": item.get("lease_expiry_at") or "",
        "updated_at": item["updated_at"],
        "genre": item.get("genre") or "",
        "style_prefs": style_prefs,
        "chain_to_automix": bool(item.get("chain_to_automix", 0)),
        "automix_job_id": item.get("automix_job_id") or "",
    }


def create(
    *,
    source_filename: str,
    model: str = "htdemucs",
    project_id: str = "",
    genre: str = "",
    style_prefs: dict | None = None,
    chain_to_automix: bool = False,
) -> dict:
    ensure_schema()
    job_id = uuid4().hex[:12]
    timestamp = _now()
    message = "Queued for separation."
    style_prefs_json = json.dumps(style_prefs, ensure_ascii=True) if style_prefs else ""
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """INSERT INTO stem_separation_jobs
               (id, status, source_filename, source_path, model, project_id,
                progress, message, result_json, error, worker_id, attempt,
                max_attempts, created_at, started_at, finished_at, heartbeat_at,
                lease_expiry_at, updated_at, genre, style_prefs, chain_to_automix,
                automix_job_id)
               VALUES (?, 'queued', ?, '', ?, ?, 0, ?, NULL, '', NULL,
                       0, 3, ?, NULL, NULL, NULL, NULL, ?, ?, ?, ?, '')""",
            (
                job_id, source_filename, model, project_id, message, timestamp, timestamp,
                genre, style_prefs_json, int(bool(chain_to_automix)),
            ),
        )
        _event(conn, job_id, "queued", message, 0, project_id=project_id)
        conn.commit()
    return get(job_id)  # type: ignore[return-value]


def set_automix_job_id(job_id: str, automix_job_id: str) -> None:
    ensure_schema()
    with db.connect() as conn:
        conn.execute(
            "UPDATE stem_separation_jobs SET automix_job_id = ?, updated_at = ? WHERE id = ?",
            (automix_job_id, _now(), job_id),
        )
        conn.commit()


def set_source_path(job_id: str, source_path: str) -> None:
    ensure_schema()
    with db.connect() as conn:
        conn.execute(
            "UPDATE stem_separation_jobs SET source_path = ?, updated_at = ? WHERE id = ?",
            (source_path, _now(), job_id),
        )
        conn.commit()


def get(job_id: str) -> dict | None:
    ensure_schema()
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM stem_separation_jobs WHERE id = ?", (job_id,)).fetchone()
    return _decode(row)


def get_latest_completed_for_project(project_id: str) -> dict | None:
    """The most recent completed separation job for a project (G3,
    docs/KENN_IMPROVEMENT_PLAN.md) -- lets a text-only "run automix on
    this" chat trigger resolve a stem set from a completed separation,
    without needing the user to re-attach a file."""
    if not project_id:
        return None
    ensure_schema()
    with db.connect() as conn:
        row = conn.execute(
            """SELECT * FROM stem_separation_jobs
               WHERE project_id = ? AND status = 'completed'
               ORDER BY created_at DESC, rowid DESC LIMIT 1""",
            (project_id,),
        ).fetchone()
    return _decode(row)


def recent(limit: int = 12) -> list[dict]:
    ensure_schema()
    safe_limit = max(1, min(200, int(limit or 12)))
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM stem_separation_jobs ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (safe_limit,),
        ).fetchall()
    return [item for row in rows if (item := _decode(row)) is not None]


def claim_next(worker_id: str, *, lease_seconds: float = 60.0) -> dict | None:
    ensure_schema()
    timestamp = _now()
    lease_expiry = _lease_after(lease_seconds)
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """SELECT id, project_id FROM stem_separation_jobs
               WHERE status = 'queued' ORDER BY created_at, rowid LIMIT 1"""
        ).fetchone()
        if row is None:
            conn.commit()
            return None
        job_id = row["id"]
        message = "Separating stems with Demucs."
        cursor = conn.execute(
            """UPDATE stem_separation_jobs
               SET status = 'running', progress = 5, message = ?, worker_id = ?,
                   attempt = attempt + 1, started_at = COALESCE(started_at, ?),
                   heartbeat_at = ?, lease_expiry_at = ?, updated_at = ?
               WHERE id = ? AND status = 'queued'""",
            (message, worker_id, timestamp, timestamp, lease_expiry, timestamp, job_id),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return None
        _event(conn, job_id, "running", message, 5, worker_id, row["project_id"])
        conn.commit()
    return get(job_id)


def heartbeat(job_id: str, worker_id: str, *, lease_seconds: float = 60.0, progress: int | None = None, message: str = "") -> bool:
    ensure_schema()
    timestamp = _now()
    lease_expiry = _lease_after(lease_seconds)
    assignments = ["heartbeat_at = ?", "lease_expiry_at = ?", "updated_at = ?"]
    values: list[object] = [timestamp, lease_expiry, timestamp]
    if progress is not None:
        assignments.append("progress = MAX(progress, ?)")
        values.append(max(0, min(95, int(progress))))
    if message:
        assignments.append("message = ?")
        values.append(message)
    values.extend((job_id, worker_id))
    with db.connect() as conn:
        cursor = conn.execute(
            f"UPDATE stem_separation_jobs SET {', '.join(assignments)} WHERE id = ? AND status = 'running' AND worker_id = ?",
            values,
        )
        conn.commit()
    return cursor.rowcount == 1


def finish(job_id: str, worker_id: str, *, status: str, message: str, result: dict | None = None, error: str = "") -> dict | None:
    if status not in TERMINAL_STATUSES:
        raise ValueError(f"Invalid terminal stem-separation status: {status}")
    ensure_schema()
    timestamp = _now()
    result_json = json.dumps(result, ensure_ascii=True, allow_nan=False) if result is not None else None
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        job_row = conn.execute("SELECT project_id FROM stem_separation_jobs WHERE id = ?", (job_id,)).fetchone()
        cursor = conn.execute(
            """UPDATE stem_separation_jobs
               SET status = ?, progress = 100, message = ?, result_json = ?, error = ?,
                   finished_at = ?, heartbeat_at = ?, lease_expiry_at = NULL, updated_at = ?
               WHERE id = ? AND status = 'running' AND worker_id = ?""",
            (status, message, result_json, error, timestamp, timestamp, timestamp, job_id, worker_id),
        )
        if cursor.rowcount == 1:
            _event(conn, job_id, status, message, 100, worker_id, job_row["project_id"] if job_row else "")
        conn.commit()
    return get(job_id)


def recover_expired(*, now_text: str | None = None) -> int:
    ensure_schema()
    timestamp = now_text or _now()
    recovered = 0
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            """SELECT * FROM stem_separation_jobs
               WHERE status = 'running' AND lease_expiry_at IS NOT NULL AND lease_expiry_at <= ?""",
            (timestamp,),
        ).fetchall()
        for row in rows:
            job = _decode(row)
            if not job:
                continue
            if job["attempt"] >= job["max_attempts"]:
                status, progress, message, finished_at = "failed", 100, "Separation failed after exceeding the restart recovery limit.", timestamp
            else:
                status, progress, message, finished_at = "queued", 0, "Recovered after an interrupted worker; queued to resume.", None
            conn.execute(
                """UPDATE stem_separation_jobs SET status = ?, progress = ?, message = ?, worker_id = NULL,
                   heartbeat_at = NULL, lease_expiry_at = NULL, finished_at = ?, updated_at = ?
                   WHERE id = ? AND status = 'running'""",
                (status, progress, message, finished_at, timestamp, job["id"]),
            )
            _event(conn, job["id"], status, message, progress, project_id=job["project_id"])
            recovered += 1
        conn.commit()
    return recovered


def trim(max_history: int = 100) -> int:
    ensure_schema()
    keep = max(1, int(max_history))
    with db.connect() as conn:
        terminal_count = conn.execute(
            "SELECT COUNT(*) AS count FROM stem_separation_jobs WHERE status IN ('completed','failed','cancelled')"
        ).fetchone()["count"]
        remove_count = max(0, int(terminal_count) - keep)
        if not remove_count:
            return 0
        ids = [
            row["id"]
            for row in conn.execute(
                """SELECT id FROM stem_separation_jobs WHERE status IN ('completed','failed','cancelled')
                   ORDER BY created_at, rowid LIMIT ?""",
                (remove_count,),
            ).fetchall()
        ]
        conn.executemany("DELETE FROM stem_separation_jobs WHERE id = ?", ((job_id,) for job_id in ids))
        conn.commit()
    return len(ids)


def clear_all() -> None:
    ensure_schema()
    with db.connect() as conn:
        conn.execute("DELETE FROM stem_separation_job_events")
        conn.execute("DELETE FROM stem_separation_jobs")
        conn.commit()
