"""Reviewed feedback for non-applying AutoMix advisor shadow operations."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from uuid import uuid4

import artifact_store
import automix_jobs
import db
import event_store

DECISIONS = frozenset({"accepted", "rejected", "needs_work"})
SHADOW_KIND = "audio.automix.advisor-shadow"
PREVIEW_KIND = "audio.automix.advisor-preview"
SHADOW_SCHEMA = "audio-too.kenn-advisor-shadow/v1"


class AdvisorFeedbackError(ValueError):
    """Raised when feedback lacks lineage or claims unsupported evidence."""


def _rating(value: object, field: str, *, required: bool) -> int | None:
    if value is None and not required:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
        suffix = "" if required else " or null"
        raise AdvisorFeedbackError(f"{field} must be an integer from 1 to 5{suffix}")
    return value


def _load_artifact(artifact_id: str, expected_kind: str) -> dict:
    artifact = artifact_store.get(str(artifact_id or "").strip())
    if artifact is None or artifact.get("status") != "active":
        raise AdvisorFeedbackError(f"Artifact is missing or inactive: {artifact_id}")
    if artifact.get("kind") != expected_kind:
        raise AdvisorFeedbackError(f"Artifact {artifact_id} is not {expected_kind}")
    return artifact


def _load_json_artifact(artifact_id: str, expected_kind: str) -> tuple[dict, dict]:
    artifact = _load_artifact(artifact_id, expected_kind)
    try:
        payload = json.loads(artifact_store.resolve_path(artifact["id"]).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AdvisorFeedbackError(f"Artifact {artifact_id} is not readable JSON") from exc
    if not isinstance(payload, dict):
        raise AdvisorFeedbackError(f"Artifact {artifact_id} must contain a JSON object")
    return artifact, payload


def record_feedback(
    *,
    job_id: str,
    shadow_artifact_id: str,
    operation_index: int,
    decision: str,
    usefulness_rating: int,
    explanation_quality_rating: int,
    audible_improvement_rating: int | None = None,
    preview_artifact_id: str = "",
    reason: str = "",
    actor_id: str = "user",
) -> dict:
    """Record one lineage-complete review; never infer an audible score."""
    clean_job_id = str(job_id or "").strip()
    clean_decision = str(decision or "").strip().lower()
    if not clean_job_id:
        raise AdvisorFeedbackError("job_id is required")
    if clean_decision not in DECISIONS:
        raise AdvisorFeedbackError(f"decision must be one of {sorted(DECISIONS)}")
    if isinstance(operation_index, bool) or not isinstance(operation_index, int) or operation_index < 0:
        raise AdvisorFeedbackError("operation_index must be a non-negative integer")
    usefulness = _rating(usefulness_rating, "usefulness_rating", required=True)
    explanation = _rating(
        explanation_quality_rating,
        "explanation_quality_rating",
        required=True,
    )
    audible = _rating(
        audible_improvement_rating,
        "audible_improvement_rating",
        required=False,
    )

    shadow, receipt = _load_json_artifact(shadow_artifact_id, SHADOW_KIND)
    if receipt.get("schema") != SHADOW_SCHEMA or receipt.get("status") != "valid":
        raise AdvisorFeedbackError("Feedback requires a valid v1 shadow receipt")
    db.init_db()
    with db.connect() as conn:
        expected_correlation_id = automix_jobs.job_correlation_id(conn, clean_job_id)
    if receipt.get("correlation_id") != expected_correlation_id:
        raise AdvisorFeedbackError("Shadow receipt does not belong to this job")
    proposal = receipt.get("proposal")
    operations = proposal.get("operations") if isinstance(proposal, dict) else None
    if not isinstance(operations, list) or operation_index >= len(operations):
        raise AdvisorFeedbackError("operation_index does not exist in the shadow proposal")
    operation = operations[operation_index]
    source_plan_revision = str(receipt.get("source_plan_revision", ""))
    if not source_plan_revision or proposal.get("source_plan_revision") != source_plan_revision:
        raise AdvisorFeedbackError("Shadow receipt has inconsistent plan revision lineage")

    clean_preview_id = str(preview_artifact_id or "").strip()
    if audible is not None and not clean_preview_id:
        raise AdvisorFeedbackError(
            "audible_improvement_rating requires an A/B preview artifact"
        )
    if clean_preview_id:
        preview = _load_artifact(clean_preview_id, PREVIEW_KIND)
        if preview.get("project_id") != shadow.get("project_id"):
            raise AdvisorFeedbackError("Preview and shadow artifacts belong to different projects")
        metadata = preview.get("metadata") or {}
        if (
            metadata.get("job_id") != clean_job_id
            or metadata.get("shadow_artifact_id") != shadow["id"]
            or metadata.get("source_plan_revision") != source_plan_revision
            or metadata.get("operation_index") != operation_index
            or shadow["id"] not in preview.get("parent_ids", [])
        ):
            raise AdvisorFeedbackError(
                "Preview does not match this job, shadow receipt, plan revision, and operation"
            )
    elif audible is None:
        clean_preview_id = ""

    feedback_id = f"aaf_{uuid4().hex[:24]}"
    timestamp = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    clean_actor = str(actor_id or "user").strip()[:120] or "user"
    clean_reason = str(reason or "").strip()[:1000]
    project_id = str(shadow.get("project_id", ""))
    db.init_db()
    try:
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """INSERT INTO automix_advisor_feedback
                   (id, job_id, project_id, shadow_artifact_id, source_plan_revision,
                    operation_index, decision, usefulness_rating,
                    explanation_quality_rating, audible_improvement_rating,
                    preview_artifact_id, reason, actor_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    feedback_id,
                    clean_job_id,
                    project_id,
                    shadow["id"],
                    source_plan_revision,
                    operation_index,
                    clean_decision,
                    usefulness,
                    explanation,
                    audible,
                    clean_preview_id or None,
                    clean_reason,
                    clean_actor,
                    timestamp,
                    timestamp,
                ),
            )
            event_store.append_in_transaction(
                conn,
                event_type="automix.advisor_feedback_recorded",
                aggregate_type="automix_advisor_feedback",
                aggregate_id=feedback_id,
                actor_id=clean_actor,
                project_id=project_id,
                correlation_id=automix_jobs.job_correlation_id(conn, clean_job_id),
                payload={
                    "decision": clean_decision,
                    "operation_index": operation_index,
                    "shadow_artifact_id": shadow["id"],
                    "has_audible_evidence": audible is not None,
                    "plan_revision": source_plan_revision,
                    "model_version": proposal.get("model_version") if isinstance(proposal, dict) else None,
                    "prompt_version": proposal.get("prompt_version") if isinstance(proposal, dict) else None,
                    "recommendation": {
                        "stem_id": operation.get("stem_id") if isinstance(operation, dict) else None,
                        "operation": operation.get("operation") if isinstance(operation, dict) else None,
                        "value": operation.get("value") if isinstance(operation, dict) else None,
                        "unit": operation.get("unit") if isinstance(operation, dict) else None,
                        "confidence": operation.get("confidence") if isinstance(operation, dict) else None,
                    },
                    "preview_artifact_id": clean_preview_id or None,
                    "metrics": {
                        "target_lufs": receipt.get("source_plan", {}).get("target_lufs") if isinstance(receipt, dict) else None,
                        "genre": receipt.get("source_plan", {}).get("genre") if isinstance(receipt, dict) else None,
                        "would_change": receipt.get("would_change", []) if isinstance(receipt, dict) else [],
                    },
                    "has_optional_reason": bool(clean_reason),
                },
            )
            conn.commit()
    except sqlite3.IntegrityError as exc:
        raise AdvisorFeedbackError("This shadow operation already has feedback") from exc
    return get_feedback(feedback_id)  # type: ignore[return-value]


def get_feedback(feedback_id: str) -> dict | None:
    db.init_db()
    with db.connect() as conn:
        row = conn.execute(
            "SELECT * FROM automix_advisor_feedback WHERE id = ?",
            (str(feedback_id or "").strip(),),
        ).fetchone()
    return dict(row) if row else None


def delete_feedback(feedback_id: str, *, actor_id: str = "user") -> bool:
    """Delete one review and emit a metadata-only privacy receipt."""
    clean_id = str(feedback_id or "").strip()
    db.init_db()
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT job_id, project_id FROM automix_advisor_feedback WHERE id = ?",
            (clean_id,),
        ).fetchone()
        if row is None:
            conn.rollback()
            return False
        conn.execute("DELETE FROM automix_advisor_feedback WHERE id = ?", (clean_id,))
        event_store.append_in_transaction(
            conn,
            event_type="automix.advisor_feedback_deleted",
            aggregate_type="automix_advisor_feedback",
            aggregate_id=clean_id,
            actor_id=str(actor_id or "user")[:120],
            project_id=row["project_id"],
            correlation_id=automix_jobs.job_correlation_id(conn, row["job_id"]),
            payload={"deleted": True},
        )
        conn.commit()
    return True
