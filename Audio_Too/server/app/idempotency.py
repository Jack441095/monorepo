"""Transactional helpers for retry-safe API mutations."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3

IDEMPOTENCY_KEY_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")


class IdempotencyConflict(ValueError):
    pass


def header_value(headers) -> str:
    value = str(headers.get("Idempotency-Key", "")).strip()
    if value and not IDEMPOTENCY_KEY_RE.fullmatch(value):
        raise ValueError(
            "Idempotency-Key must contain 1-128 letters, numbers, dots, underscores, colons, or hyphens."
        )
    return value


def payload_hash(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def replay(
    conn: sqlite3.Connection,
    *,
    operation: str,
    key: str,
    request_hash: str,
) -> tuple[int, dict] | None:
    if not key:
        return None
    row = conn.execute(
        """SELECT request_hash, response_json, status_code
           FROM api_idempotency WHERE operation = ? AND idempotency_key = ?""",
        (operation, key),
    ).fetchone()
    if not row:
        return None
    if row["request_hash"] != request_hash:
        raise IdempotencyConflict("Idempotency-Key was already used with a different request.")
    return int(row["status_code"]), json.loads(row["response_json"])


def record(
    conn: sqlite3.Connection,
    *,
    operation: str,
    key: str,
    request_hash: str,
    status_code: int,
    response: dict,
    created_at: str,
) -> None:
    if not key:
        return
    conn.execute(
        """INSERT INTO api_idempotency
           (operation, idempotency_key, request_hash, response_json, status_code, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            operation,
            key,
            request_hash,
            json.dumps(response, sort_keys=True, separators=(",", ":")),
            status_code,
            created_at,
        ),
    )
