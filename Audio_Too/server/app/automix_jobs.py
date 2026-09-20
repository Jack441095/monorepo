"""Transactional Automix job creation service."""

from __future__ import annotations

import json
from uuid import uuid4

import idempotency
import stem_uploads
from app.api_schemas import AutomixRevisionRequest, AutomixStartRequest
from nite_core import JobSnapshot, JobStatus
from db import connect, now
from audio_analysis.mixdown.musical_roles import validate_role_correction_payload
from audio_analysis.mixdown.arrangement import validate_arrangement_correction_payload


class NoCompletedMix(ValueError):
    pass


class InvalidMusicalRoleCorrection(ValueError):
    code = "invalid_musical_role_correction"


class InvalidArrangementCorrection(ValueError):
    code = "invalid_arrangement_correction"


def job_correlation_id(conn, job_id: str) -> str:
    """Read a job's own correlation id so downstream events join the same trace.

    Shared by advisor_feedback.py and musical_role_feedback.py so their domain
    events correlate with the job's HTTP/Thursday-supplied trace id instead of
    each independently reconstructing the legacy job-derived id. Falls back to
    that legacy derivation for jobs created before the ``automix_jobs
    .correlation_id`` column existed (empty string default) or an unknown id.
    """
    row = conn.execute(
        "SELECT correlation_id FROM automix_jobs WHERE id = ?", (job_id,)
    ).fetchone()
    stored = str(row["correlation_id"] or "") if row else ""
    return stored or f"automix-job:{job_id}"


def get_job_status(job_id: str) -> dict | None:
    """Fetch one AutoMix job plus its status-history events, or None if not found.

    Shared read path for the HTTP /api/automix/status route and Thursday's
    registry service (registry_studio.py) so both surfaces stay in sync.
    """
    with connect() as conn:
        row = conn.execute("SELECT * FROM automix_jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            return None
        payload = dict(row)
        events = conn.execute(
            "SELECT status, message, created_at FROM automix_job_events "
            "WHERE job_id = ? ORDER BY created_at, rowid",
            (job_id,),
        ).fetchall()
    payload["history"] = [dict(event) for event in events]
    return payload


def list_recent_jobs(*, project_id: str | None = None, limit: int = 10) -> list[dict]:
    """List recent AutoMix jobs, newest first, optionally filtered to one project."""
    limit = max(1, min(50, limit))
    with connect() as conn:
        if project_id:
            rows = conn.execute(
                "SELECT * FROM automix_jobs WHERE project_id = ? "
                "ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (project_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM automix_jobs ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [dict(row) for row in rows]


def queue_job(request: AutomixStartRequest, *, idempotency_key: str = "") -> tuple[int, dict]:
    operation = "automix.job.create"
    # Merge target_lufs into style_prefs for storage (avoids schema change)
    merged_prefs = dict(request.style_prefs)
    if request.target_lufs is not None:
        merged_prefs["_target_lufs"] = request.target_lufs
    if "musical_role_corrections" in merged_prefs:
        try:
            validate_role_correction_payload(merged_prefs["musical_role_corrections"])
        except ValueError as exc:
            raise InvalidMusicalRoleCorrection(str(exc)) from exc
    if "arrangement_corrections" in merged_prefs:
        try:
            merged_prefs["arrangement_corrections"] = validate_arrangement_correction_payload(
                merged_prefs["arrangement_corrections"]
            )
        except ValueError as exc:
            raise InvalidArrangementCorrection(str(exc)) from exc
    request_payload = {
        "project_id": request.project_id,
        "genre": request.genre,
        "style_prefs": merged_prefs,
    }
    request_hash = idempotency.payload_hash(request_payload)
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        replay = idempotency.replay(
            conn,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if replay:
            return replay

        readiness = stem_uploads.require_source_ready(request.project_id)

        job_id = str(uuid4())[:8]
        timestamp = now()
        correlation_id = str(request.correlation_id or "").strip() or f"automix-job:{job_id}"
        conn.execute(
            """INSERT INTO automix_jobs
               (id, project_id, status, genre, style_prefs, error_message, result_path,
                correlation_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job_id,
                request.project_id,
                "queued",
                request.genre,
                json.dumps(merged_prefs),
                "",
                "",
                correlation_id,
                timestamp,
                timestamp,
            ),
        )
        conn.execute(
            """INSERT INTO automix_job_events
               (id, job_id, status, message, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (str(uuid4()), job_id, "queued", "", timestamp, timestamp),
        )
        job = JobSnapshot(
            job_id=job_id,
            capability="automix.render",
            status=JobStatus.QUEUED,
            stage="queued",
            project_id=request.project_id,
        )
        response = {
            "ok": True,
            "job_id": job.job_id,
            "status": job.status.value,
            "source_readiness": {
                "file_count": readiness["file_count"],
                "total_bytes": readiness["total_bytes"],
            },
        }
        idempotency.record(
            conn,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            status_code=200,
            response=response,
            created_at=timestamp,
        )
        conn.commit()
    return 200, response


def queue_revision(
    request: AutomixRevisionRequest,
    *,
    idempotency_key: str = "",
) -> tuple[int, dict]:
    operation = "automix.revision.create"
    request_payload = {"project_id": request.project_id, "feedback": request.feedback}
    request_hash = idempotency.payload_hash(request_payload)
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        replay = idempotency.replay(
            conn,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if replay:
            return replay

        row = conn.execute(
            # created_at has 1-second resolution (db.now()) -- two jobs for
            # the same project can share a timestamp, at which point
            # ORDER BY created_at DESC alone doesn't reliably pick the
            # actually-most-recent one. rowid DESC breaks the tie by real
            # insertion order (same idiom already used for
            # automix_job_events above).
            """SELECT * FROM automix_jobs
               WHERE project_id = ? AND status = 'complete'
               ORDER BY created_at DESC, rowid DESC LIMIT 1""",
            (request.project_id,),
        ).fetchone()
        if not row:
            raise NoCompletedMix(
                "No previous completed mix found to revise. Please submit a mix first."
            )

        readiness = stem_uploads.require_source_ready(request.project_id)

        previous = dict(row)
        try:
            preferences = json.loads(previous.get("style_prefs", "{}"))
        except (TypeError, json.JSONDecodeError):
            preferences = {}
        if not isinstance(preferences, dict):
            preferences = {}
        # Accumulate across revisions rather than overwrite -- a second
        # "more reverb" revision shouldn't discard an earlier "brighter"
        # one (every revision still regenerates the plan from scratch, so
        # without this the first request's feedback would simply vanish).
        # "feedback" itself is kept too, as the latest single value, for
        # any older reader that only expects that key.
        feedback_history = list(preferences.get("feedback_history") or [])
        if request.feedback:
            feedback_history.append(request.feedback)
        preferences["feedback_history"] = feedback_history
        preferences["feedback"] = request.feedback

        job_id = str(uuid4())[:8]
        timestamp = now()
        conn.execute(
            """INSERT INTO automix_jobs
               (id, project_id, status, genre, style_prefs, error_message, result_path,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job_id,
                request.project_id,
                "queued",
                previous.get("genre"),
                json.dumps(preferences),
                "",
                "",
                timestamp,
                timestamp,
            ),
        )
        conn.execute(
            """INSERT INTO automix_job_events
               (id, job_id, status, message, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                str(uuid4()),
                job_id,
                "queued",
                f"Revision requested: {request.feedback}",
                timestamp,
                timestamp,
            ),
        )
        job = JobSnapshot(
            job_id=job_id,
            capability="automix.render",
            status=JobStatus.QUEUED,
            stage="queued",
            project_id=request.project_id,
        )
        response = {
            "ok": True,
            "job_id": job.job_id,
            "status": job.status.value,
            "source_readiness": {
                "file_count": readiness["file_count"],
                "total_bytes": readiness["total_bytes"],
            },
        }
        idempotency.record(
            conn,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            status_code=200,
            response=response,
            created_at=timestamp,
        )
        conn.commit()
    return 200, response


def queue_health() -> dict:
    """Read-only queue audit; never mutates or deletes historical jobs."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, project_id, status, created_at FROM automix_jobs "
            "WHERE status IN ('queued', 'claimed', 'preparing', 'classifying', 'analysing', "
            "'deciding', 'processing', 'packaging') ORDER BY created_at"
        ).fetchall()
    jobs = []
    for row in rows:
        item = dict(row)
        item["source_readiness"] = stem_uploads.source_readiness(item["project_id"])
        jobs.append(item)
    blocked = [item for item in jobs if not item["source_readiness"]["ready"]]
    return {
        "active_jobs": len(jobs),
        "ready_jobs": len(jobs) - len(blocked),
        "blocked_jobs": len(blocked),
        "jobs": jobs,
    }
