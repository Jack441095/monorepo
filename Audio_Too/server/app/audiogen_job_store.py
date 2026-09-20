"""Transactional storage for durable AudioGen render jobs."""

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


def _event(
    conn,
    job_id: str,
    status: str,
    message: str,
    progress: int,
    worker_id: str = "",
    project_id: str = "",
) -> None:
    conn.execute(
        """INSERT INTO audiogen_job_events
           (id, job_id, status, message, progress, worker_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (uuid4().hex, job_id, status, message, progress, worker_id, _now()),
    )
    event_store.append_in_transaction(
        conn,
        event_type=f"audiogen.job.{status}",
        aggregate_type="job",
        aggregate_id=job_id,
        project_id=project_id,
        correlation_id=f"audiogen-job:{job_id}",
        actor_id=worker_id or "audiogen",
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
        "type": item["job_type"],
        "status": item["status"],
        "emotion": item["emotion"],
        "bars": item["bars"],
        "k": item["candidate_count"],
        "publish": bool(item["publish"]),
        "project_id": item["project_id"],
        "progress": item["progress"],
        "message": item["message"],
        "created_at": item["created_at"],
        "started_at": item.get("started_at") or "",
        "finished_at": item.get("finished_at") or "",
        "cancel_requested": bool(item["cancellation_requested"]),
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
    emotion: str,
    bars: int,
    candidate_count: int,
    publish: bool,
    project_id: str,
    genre: str = "",
    style_prefs: dict | None = None,
    chain_to_automix: bool = False,
) -> dict:
    ensure_schema()
    job_id = uuid4().hex[:12]
    timestamp = _now()
    message = "Queued for rendering."
    style_prefs_json = json.dumps(style_prefs, ensure_ascii=True) if style_prefs else ""
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """INSERT INTO audiogen_jobs
               (id, job_type, status, emotion, bars, candidate_count, publish, project_id,
                progress, message, result_json, error, cancellation_requested, worker_id,
                attempt, max_attempts, created_at, started_at, finished_at, heartbeat_at,
                lease_expiry_at, updated_at, genre, style_prefs, chain_to_automix, automix_job_id)
               VALUES (?, 'full_song', 'queued', ?, ?, ?, ?, ?, 0, ?, NULL, '', 0, NULL,
                       0, 3, ?, NULL, NULL, NULL, NULL, ?, ?, ?, ?, '')""",
            (
                job_id,
                emotion,
                bars,
                candidate_count,
                int(publish),
                project_id,
                message,
                timestamp,
                timestamp,
                genre,
                style_prefs_json,
                int(bool(chain_to_automix)),
            ),
        )
        _event(conn, job_id, "queued", message, 0, project_id=project_id)
        conn.commit()
    return get(job_id)  # type: ignore[return-value]


def set_automix_job_id(job_id: str, automix_job_id: str) -> None:
    """Link a finished AudioGen render to the AutoMix job its stems were
    chained into, so status polling can surface both ids together."""
    ensure_schema()
    with db.connect() as conn:
        conn.execute(
            "UPDATE audiogen_jobs SET automix_job_id = ?, updated_at = ? WHERE id = ?",
            (automix_job_id, _now(), job_id),
        )
        conn.commit()


def get(job_id: str) -> dict | None:
    ensure_schema()
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM audiogen_jobs WHERE id = ?", (job_id,)).fetchone()
    return _decode(row)


def recent(limit: int = 12) -> list[dict]:
    ensure_schema()
    safe_limit = max(1, min(200, int(limit or 12)))
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM audiogen_jobs ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (safe_limit,),
        ).fetchall()
    return [item for row in rows if (item := _decode(row)) is not None]


def events(job_id: str) -> list[dict]:
    ensure_schema()
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM audiogen_job_events WHERE job_id = ? ORDER BY created_at, rowid",
            (job_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def claim_next(worker_id: str, *, lease_seconds: float = 30.0) -> dict | None:
    ensure_schema()
    timestamp = _now()
    lease_expiry = _lease_after(lease_seconds)
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """UPDATE audiogen_jobs
               SET status = 'cancelled', progress = 100,
                   message = 'Cancelled before rendering started.', finished_at = ?, updated_at = ?
               WHERE status = 'queued' AND cancellation_requested = 1""",
            (timestamp, timestamp),
        )
        row = conn.execute(
            """SELECT id, project_id FROM audiogen_jobs
               WHERE status = 'queued' AND cancellation_requested = 0
               ORDER BY created_at, rowid LIMIT 1"""
        ).fetchone()
        if row is None:
            conn.commit()
            return None
        job_id = row["id"]
        message = "Rendering full song in LLM_AudioGen."
        cursor = conn.execute(
            """UPDATE audiogen_jobs
               SET status = 'running', progress = 10, message = ?, worker_id = ?,
                   attempt = attempt + 1, started_at = COALESCE(started_at, ?),
                   heartbeat_at = ?, lease_expiry_at = ?, updated_at = ?
               WHERE id = ? AND status = 'queued'""",
            (message, worker_id, timestamp, timestamp, lease_expiry, timestamp, job_id),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return None
        _event(conn, job_id, "running", message, 10, worker_id, row["project_id"])
        conn.commit()
    return get(job_id)


def heartbeat(
    job_id: str,
    worker_id: str,
    *,
    lease_seconds: float = 30.0,
    progress: int | None = None,
    message: str = "",
) -> bool:
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
            f"UPDATE audiogen_jobs SET {', '.join(assignments)} "
            "WHERE id = ? AND status = 'running' AND worker_id = ?",
            values,
        )
        conn.commit()
    return cursor.rowcount == 1


def cancellation_requested(job_id: str) -> bool:
    job = get(job_id)
    return bool(job and job["cancel_requested"])


def request_cancel(job_id: str) -> dict | None:
    ensure_schema()
    timestamp = _now()
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM audiogen_jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            conn.rollback()
            return None
        job = _decode(row)
        if job and job["status"] == "queued":
            message = "Cancelled before rendering started."
            conn.execute(
                """UPDATE audiogen_jobs SET status = 'cancelled', progress = 100, message = ?,
                   cancellation_requested = 1, finished_at = ?, updated_at = ? WHERE id = ?""",
                (message, timestamp, timestamp, job_id),
            )
            _event(conn, job_id, "cancelled", message, 100, project_id=job["project_id"])
        elif job and job["status"] == "running":
            message = "Cancel requested; this render will stop after the current AudioGen process returns."
            conn.execute(
                """UPDATE audiogen_jobs SET cancellation_requested = 1, message = ?, updated_at = ?
                   WHERE id = ? AND status = 'running'""",
                (message, timestamp, job_id),
            )
            _event(
                conn,
                job_id,
                "running",
                message,
                job["progress"],
                job["worker_id"],
                job["project_id"],
            )
        conn.commit()
    return get(job_id)


def finish(
    job_id: str,
    worker_id: str,
    *,
    status: str,
    message: str,
    result: dict | None = None,
    error: str = "",
) -> dict | None:
    if status not in TERMINAL_STATUSES:
        raise ValueError(f"Invalid terminal AudioGen status: {status}")
    ensure_schema()
    timestamp = _now()
    result_json = json.dumps(result, ensure_ascii=True, allow_nan=False) if result is not None else None
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        job_row = conn.execute(
            "SELECT project_id FROM audiogen_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        cursor = conn.execute(
            """UPDATE audiogen_jobs
               SET status = ?, progress = 100, message = ?, result_json = ?, error = ?,
                   finished_at = ?, heartbeat_at = ?, lease_expiry_at = NULL, updated_at = ?
               WHERE id = ? AND status = 'running' AND worker_id = ?""",
            (status, message, result_json, error, timestamp, timestamp, timestamp, job_id, worker_id),
        )
        if cursor.rowcount == 1:
            _event(
                conn,
                job_id,
                status,
                message,
                100,
                worker_id,
                job_row["project_id"] if job_row else "",
            )
        conn.commit()
    return get(job_id)


def recover_expired(*, now_text: str | None = None) -> int:
    ensure_schema()
    timestamp = now_text or _now()
    recovered = 0
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            """SELECT * FROM audiogen_jobs
               WHERE status = 'running' AND lease_expiry_at IS NOT NULL AND lease_expiry_at <= ?""",
            (timestamp,),
        ).fetchall()
        for row in rows:
            job = _decode(row)
            if not job:
                continue
            if job["attempt"] >= job["max_attempts"]:
                status = "failed"
                progress = 100
                message = "Render failed after exceeding the restart recovery limit."
                finished_at = timestamp
            else:
                status = "queued"
                progress = 0
                message = "Recovered after an interrupted worker; queued to resume."
                finished_at = None
            conn.execute(
                """UPDATE audiogen_jobs SET status = ?, progress = ?, message = ?, worker_id = NULL,
                   heartbeat_at = NULL, lease_expiry_at = NULL, finished_at = ?, updated_at = ?
                   WHERE id = ? AND status = 'running'""",
                (status, progress, message, finished_at, timestamp, job["id"]),
            )
            _event(
                conn,
                job["id"],
                status,
                message,
                progress,
                project_id=job["project_id"],
            )
            recovered += 1
        conn.commit()
    return recovered


def trim(max_history: int = 40) -> int:
    ensure_schema()
    keep = max(1, int(max_history))
    with db.connect() as conn:
        terminal_count = conn.execute(
            "SELECT COUNT(*) AS count FROM audiogen_jobs WHERE status IN ('completed','failed','cancelled')"
        ).fetchone()["count"]
        remove_count = max(0, int(terminal_count) - keep)
        if not remove_count:
            return 0
        ids = [
            row["id"]
            for row in conn.execute(
                """SELECT id FROM audiogen_jobs WHERE status IN ('completed','failed','cancelled')
                   ORDER BY created_at, rowid LIMIT ?""",
                (remove_count,),
            ).fetchall()
        ]
        conn.executemany("DELETE FROM audiogen_jobs WHERE id = ?", ((job_id,) for job_id in ids))
        conn.commit()
    return len(ids)


def import_legacy_json(path: Path) -> int:
    """Import the previous JSON queue once when the durable queue is empty."""
    ensure_schema()
    if not path.exists():
        return 0
    with db.connect() as conn:
        if conn.execute("SELECT 1 FROM audiogen_jobs LIMIT 1").fetchone():
            return 0
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    jobs = payload.get("jobs") if isinstance(payload, dict) else None
    order = payload.get("order") if isinstance(payload, dict) else None
    if not isinstance(jobs, dict) or not isinstance(order, list):
        return 0
    imported = 0
    timestamp = _now()
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        for raw_id in order:
            raw = jobs.get(str(raw_id))
            if not isinstance(raw, dict):
                continue
            status = str(raw.get("status", "queued"))
            if status not in {"queued", "running", "completed", "failed", "cancelled"}:
                status = "queued"
            message = str(raw.get("message", ""))
            error = str(raw.get("error", ""))
            progress = max(0, min(100, int(raw.get("progress", 0) or 0)))
            finished_at = raw.get("finished_at") or None
            if status == "running":
                status = "failed"
                progress = 100
                message = "Interrupted by server restart."
                error = "The previous AudioGen process ended when the server restarted."
                finished_at = timestamp
            job_id = str(raw.get("id") or raw_id or uuid4().hex[:12])
            conn.execute(
                """INSERT OR IGNORE INTO audiogen_jobs
                   (id, job_type, status, emotion, bars, candidate_count, publish, project_id,
                    progress, message, result_json, error, cancellation_requested, worker_id,
                    attempt, max_attempts, created_at, started_at, finished_at, heartbeat_at,
                    lease_expiry_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 0, 3, ?, ?, ?, NULL, NULL, ?)""",
                (
                    job_id, str(raw.get("type") or "full_song"), status,
                    str(raw.get("emotion") or "joy"), int(raw.get("bars", 4) or 4),
                    int(raw.get("k", 1) or 1), int(bool(raw.get("publish", True))),
                    str(raw.get("project_id") or ""), progress, message,
                    json.dumps(raw.get("result")) if isinstance(raw.get("result"), dict) else None,
                    error, int(bool(raw.get("cancel_requested", False))),
                    str(raw.get("created_at") or timestamp), raw.get("started_at") or None,
                    finished_at, timestamp,
                ),
            )
            _event(
                conn,
                job_id,
                status,
                message,
                progress,
                project_id=str(raw.get("project_id") or ""),
            )
            imported += 1
        conn.commit()
    return imported


def clear_all() -> None:
    ensure_schema()
    with db.connect() as conn:
        conn.execute("DELETE FROM audiogen_job_events")
        conn.execute("DELETE FROM audiogen_jobs")
        conn.commit()
