"""Typed status-transition service for admin CRM records.

Extracts POST /api/admin/status out of the route handler so the mutation is a
single transaction that (a) enforces an optimistic-version contract where the
record supports it, (b) updates the status, and (c) appends a
`record.status_changed` domain event — the same shape as
`stem_uploads.store_upload` (BEGIN IMMEDIATE → state change → event → commit).

Allowlist: any table that has a `status` column EXCEPT worker/lifecycle-managed
tables (e.g. `automix_jobs`), which own their own status state machines and must
not be transitioned from the dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass

import event_store
from db import TABLES, connect, now, retry_on_db_lock

# Worker/lifecycle-managed tables own their own transitions (the automix worker
# enforces VALID_TRANSITIONS); the dashboard must not poke their status directly.
_WORKER_MANAGED = frozenset({"automix_jobs", "automix_job_events"})
ALLOWED_TABLES = frozenset(
    table for table, cols in TABLES.items()
    if "status" in cols and table not in _WORKER_MANAGED
)
MAX_STATUS_LEN = 40


class StatusTransitionError(Exception):
    """Carries the HTTP status code the route should return."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


@dataclass(frozen=True)
class StatusTransitionRequest:
    table: str
    record_id: str
    status: str
    expected_version: int | None = None

    @classmethod
    def from_payload(cls, payload: dict) -> "StatusTransitionRequest":
        table = str(payload.get("table", "")).strip()
        record_id = str(payload.get("id", "")).strip()
        status = str(payload.get("status", "")).strip()
        if table not in ALLOWED_TABLES:
            raise StatusTransitionError(400, "Unsupported table for status change.")
        if not record_id:
            raise StatusTransitionError(400, "id is required.")
        if not status or len(status) > MAX_STATUS_LEN or not status.isprintable():
            raise StatusTransitionError(400, "A valid status is required.")
        expected: int | None = None
        raw_version = payload.get("expected_version")
        if raw_version is not None:
            try:
                expected = int(raw_version)
            except (TypeError, ValueError):
                raise StatusTransitionError(400, "expected_version must be an integer.") from None
        return cls(table=table, record_id=record_id, status=status, expected_version=expected)


@retry_on_db_lock()
def transition_status(request: StatusTransitionRequest, *, actor_id: str = "dashboard") -> dict:
    """Apply the status change in one transaction; returns the updated record."""
    cols = TABLES[request.table]
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            f"SELECT * FROM {request.table} WHERE id = ?", (request.record_id,)
        ).fetchone()
        if not row:
            raise StatusTransitionError(404, "Record not found.")
        target = dict(row)

        has_version = "optimistic_version" in cols
        stored_version = int(target.get("optimistic_version") or 1) if has_version else None
        if request.expected_version is not None:
            if not has_version:
                raise StatusTransitionError(400, "This record type does not support version checks.")
            if request.expected_version != stored_version:
                raise StatusTransitionError(
                    409, "Concurrency conflict: record was modified by another process."
                )

        from_status = str(target.get("status", ""))
        updated_at = now()
        assignments = ["status = ?"]
        params: list = [request.status]
        if "updated_at" in cols:
            assignments.append("updated_at = ?")
            params.append(updated_at)
        new_version = None
        if has_version:
            new_version = stored_version + 1
            assignments.append("optimistic_version = ?")
            params.append(new_version)
        params.append(request.record_id)
        conn.execute(
            f"UPDATE {request.table} SET {', '.join(assignments)} WHERE id = ?", params
        )

        payload = {"table": request.table, "from": from_status, "to": request.status}
        if new_version is not None:
            payload["version"] = new_version
        event_store.append_in_transaction(
            conn,
            event_type="record.status_changed",
            aggregate_type=request.table,
            aggregate_id=request.record_id,
            project_id=str(target.get("project_id", "")),
            actor_id=actor_id,
            payload=payload,
        )

        conn.commit()
        updated = dict(target)
        updated["status"] = request.status
        if "updated_at" in cols:
            updated["updated_at"] = updated_at
        if new_version is not None:
            updated["optimistic_version"] = new_version
        return updated
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
