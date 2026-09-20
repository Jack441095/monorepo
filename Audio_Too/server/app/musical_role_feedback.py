"""Durable, retry-safe evidence for user-reviewed MusicalRole corrections."""

from __future__ import annotations

import hashlib
import json
from uuid import uuid4

import automix_jobs
import db
import event_store


class MusicalRoleFeedbackError(ValueError):
    """Raised when correction lineage is incomplete or conflicts on retry."""


def _correction_hash(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def record_applied_corrections(
    *,
    job_id: str,
    project_id: str,
    source_plan_revision: str,
    inferred_roles: list,
    applied_roles: list,
    actor_id: str = "user",
) -> list[dict]:
    """Persist only corrections that were actually applied to a lineaged plan."""
    if not job_id or not source_plan_revision:
        raise MusicalRoleFeedbackError("job_id and source_plan_revision are required")
    inferred_by_name = {role.stem_name: role for role in inferred_roles}
    corrections = [role for role in applied_roles if role.user_corrected]
    if not corrections:
        return []
    timestamp = db.now()
    clean_actor = str(actor_id or "user")[:120] or "user"
    recorded: list[dict] = []
    db.init_db()
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        for corrected in corrections:
            inferred = inferred_by_name.get(corrected.stem_name)
            if inferred is None:
                raise MusicalRoleFeedbackError(
                    f"Correction lacks inferred-role lineage: {corrected.stem_name!r}"
                )
            payload = {
                "job_id": job_id,
                "source_plan_revision": source_plan_revision,
                "stem_name": corrected.stem_name,
                "inferred_role": inferred.role,
                "inferred_priority": inferred.priority,
                "inferred_confidence": inferred.confidence,
                "inferred_ambiguous": inferred.ambiguous,
                "corrected_role": corrected.role,
                "corrected_priority": corrected.priority,
            }
            digest = _correction_hash(payload)
            existing = conn.execute(
                "SELECT * FROM automix_musical_role_corrections WHERE job_id = ? AND stem_name = ?",
                (job_id, corrected.stem_name),
            ).fetchone()
            if existing is not None:
                if existing["correction_hash"] != digest:
                    raise MusicalRoleFeedbackError(
                        f"Conflicting correction retry for {corrected.stem_name!r}"
                    )
                recorded.append(dict(existing))
                continue
            feedback_id = f"mrc_{uuid4().hex[:24]}"
            conn.execute(
                """INSERT INTO automix_musical_role_corrections
                   (id, job_id, project_id, source_plan_revision, stem_name,
                    inferred_role, inferred_priority, inferred_confidence,
                    inferred_ambiguous, corrected_role, corrected_priority,
                    correction_hash, actor_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    feedback_id, job_id, project_id, source_plan_revision,
                    corrected.stem_name, inferred.role, inferred.priority,
                    inferred.confidence, int(inferred.ambiguous), corrected.role,
                    corrected.priority, digest, clean_actor, timestamp, timestamp,
                ),
            )
            event_store.append_in_transaction(
                conn,
                event_type="automix.musical_role_corrected",
                aggregate_type="automix_musical_role_correction",
                aggregate_id=feedback_id,
                actor_id=clean_actor,
                project_id=project_id,
                correlation_id=automix_jobs.job_correlation_id(conn, job_id),
                payload={
                    "source_plan_revision": source_plan_revision,
                    "inferred_role": inferred.role,
                    "corrected_role": corrected.role,
                },
            )
            recorded.append(dict(conn.execute(
                "SELECT * FROM automix_musical_role_corrections WHERE id = ?",
                (feedback_id,),
            ).fetchone()))
        conn.commit()
    return recorded


def list_corrections(*, project_id: str | None = None) -> list[dict]:
    db.init_db()
    with db.connect() as conn:
        if project_id is None:
            rows = conn.execute(
                "SELECT * FROM automix_musical_role_corrections ORDER BY created_at, id"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM automix_musical_role_corrections WHERE project_id = ? "
                "ORDER BY created_at, id",
                (project_id,),
            ).fetchall()
    return [dict(row) for row in rows]


def delete_corrections_for_project(project_id: str, *, actor_id: str = "user") -> int:
    """Delete project correction evidence and emit one metadata-only privacy receipt."""
    db.init_db()
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            "SELECT id, job_id FROM automix_musical_role_corrections WHERE project_id = ?",
            (project_id,),
        ).fetchall()
        conn.execute(
            "DELETE FROM automix_musical_role_corrections WHERE project_id = ?", (project_id,)
        )
        if rows:
            event_store.append_in_transaction(
                conn,
                event_type="automix.musical_role_corrections_deleted",
                aggregate_type="project",
                aggregate_id=project_id,
                actor_id=str(actor_id or "user")[:120],
                project_id=project_id,
                correlation_id=f"privacy-delete:{project_id}",
                payload={"deleted_count": len(rows)},
            )
        conn.commit()
    return len(rows)
