"""Append-only, versioned domain events for workflows and project timelines."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import db
from nite_core import DomainEvent

MAX_EVENT_PAYLOAD_BYTES = 64 * 1024
FORBIDDEN_PAYLOAD_KEYS = {
    "authorization",
    "cookie",
    "file_path",
    "local_path",
    "password",
    "raw_exception",
    "result_path",
    "secret",
    "session_token",
    "token",
    "wav_path",
}
_READY_DB: Path | None = None
_SCHEMA_LOCK = threading.Lock()


class EventStoreError(ValueError):
    pass


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
    global _READY_DB
    _READY_DB = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _payload(value: dict | None) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise EventStoreError("Event payload must be a JSON object.")

    def inspect(item: object) -> None:
        if isinstance(item, dict):
            for key, nested in item.items():
                normalized = str(key).strip().lower()
                if normalized in FORBIDDEN_PAYLOAD_KEYS or any(
                    marker in normalized
                    for marker in ("password", "secret", "authorization", "cookie")
                ):
                    raise EventStoreError(
                        f"Event payload field '{key}' is restricted; store a safe reference instead."
                    )
                inspect(nested)
        elif isinstance(item, (list, tuple)):
            for nested in item:
                inspect(nested)

    inspect(value)
    try:
        encoded = json.dumps(value, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise EventStoreError("Event payload must contain finite JSON values.") from exc
    if len(encoded.encode("utf-8")) > MAX_EVENT_PAYLOAD_BYTES:
        raise EventStoreError("Event payload exceeds the 64 KiB limit.")
    return json.loads(encoded)


def append_in_transaction(
    conn,
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    actor_id: str,
    payload: dict | None = None,
    project_id: str = "",
    correlation_id: str = "",
    causation_id: str = "",
) -> dict:
    event_id = f"evt_{uuid4().hex[:24]}"
    occurred_at = _now()
    contract = DomainEvent(
        event_id=event_id,
        event_type=event_type,
        aggregate_id=aggregate_id,
        correlation_id=correlation_id or event_id,
        actor_id=actor_id,
        payload=_payload(payload),
        occurred_at=occurred_at,
    )
    clean_aggregate_type = str(aggregate_type or "").strip()
    if not clean_aggregate_type:
        raise EventStoreError("aggregate_type is required.")
    conn.execute(
        """INSERT INTO domain_events
           (id, event_type, aggregate_type, aggregate_id, project_id, correlation_id,
            causation_id, actor_id, payload_json, schema_version, occurred_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            contract.event_id,
            contract.event_type,
            clean_aggregate_type,
            contract.aggregate_id,
            str(project_id or ""),
            contract.correlation_id,
            str(causation_id or ""),
            contract.actor_id,
            json.dumps(contract.payload, ensure_ascii=True, separators=(",", ":")),
            contract.schema_version,
            contract.occurred_at,
        ),
    )
    return {
        **contract.to_dict(),
        "id": contract.event_id,
        "aggregate_type": clean_aggregate_type,
        "project_id": str(project_id or ""),
        "causation_id": str(causation_id or ""),
    }


def append(**kwargs) -> dict:
    ensure_schema()
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        event = append_in_transaction(conn, **kwargs)
        conn.commit()
    return event


def _decode(row) -> dict:
    item = dict(row)
    try:
        payload = json.loads(item.pop("payload_json") or "{}")
    except json.JSONDecodeError:
        payload = {}
    item["payload"] = payload if isinstance(payload, dict) else {}
    return item


def list_for_project(project_id: str, *, limit: int = 200) -> list[dict]:
    ensure_schema()
    safe_limit = max(1, min(1000, int(limit or 200)))
    with db.connect() as conn:
        rows = conn.execute(
            """SELECT * FROM domain_events WHERE project_id = ?
               ORDER BY occurred_at DESC, rowid DESC LIMIT ?""",
            (str(project_id), safe_limit),
        ).fetchall()
    return [_decode(row) for row in rows]


def list_for_correlation(correlation_id: str, *, limit: int = 500) -> list[dict]:
    ensure_schema()
    safe_limit = max(1, min(1000, int(limit or 500)))
    with db.connect() as conn:
        rows = conn.execute(
            """SELECT * FROM domain_events WHERE correlation_id = ?
               ORDER BY occurred_at, rowid LIMIT ?""",
            (str(correlation_id), safe_limit),
        ).fetchall()
    return [_decode(row) for row in rows]
