"""SQLite data layer for Audio_Too (single source of truth).

Legacy JSON files under agents/Shared/data/ are imported once when a table is empty.
Use export_json_snapshots() for human-readable exports; the app does not write JSON on each change.
"""

from __future__ import annotations

import functools
import json
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent
BUSINESS_ROOT = ROOT.parent
REPO_ROOT = BUSINESS_ROOT.parent
AGENT_DATA = BUSINESS_ROOT / "agents" / "Shared" / "data"
DB_PATH = REPO_ROOT / "data" / "audio_too.db"

TABLES = {
    "clients": ["id", "name", "contact", "status", "notes", "created_at", "updated_at", "optimistic_version"],
    "projects": ["id", "client", "project", "service", "status", "deadline", "waiting_on", "follow_up", "next_action", "source", "created_at", "updated_at", "optimistic_version"],
    "leads": ["id", "lead", "contact", "type", "service_fit", "status", "score", "source", "next_action", "waiting_on", "follow_up", "created_at", "updated_at", "optimistic_version"],
    "campaigns": ["id", "campaign", "audience", "service", "platforms", "status", "source_file", "created_at", "updated_at"],
    "followups": ["id", "owner", "subject", "source", "status", "due", "notes", "created_at", "updated_at"],
    "invoices": ["id", "date", "client", "service", "hours", "rate", "total", "status", "notes", "created_at", "updated_at", "optimistic_version"],
    "drafts": ["id", "type", "recipient", "subject", "body", "status", "source", "created_at", "updated_at", "optimistic_version"],
    "enquiries": [
        "id",
        "name",
        "email",
        "service",
        "message",
        "deadline",
        "status",
        "created_at",
        "updated_at",
        "optimistic_version",
    ],
    "suggested_notes": ["id", "title", "content", "source_cluster_queries", "status", "created_at", "updated_at"],
    "sessions": [
        "id", "client", "project", "service", "date", "time", "duration",
        "location", "status", "rate", "notes", "created_at", "updated_at",
    ],
    "expenses": [
        "id", "date", "category", "amount", "description", "project", "client",
        "recurring", "notes", "created_at", "updated_at",
    ],
    "automix_jobs": [
        "id", "project_id", "status", "genre", "style_prefs", "error_message",
        "result_path", "iteration_count", "created_at", "updated_at",
        "worker_id", "claimed_at", "heartbeat_at", "lease_expiry_at", "progress",
        "cancellation_requested"
    ],
    "automix_job_events": ["id", "job_id", "status", "message", "created_at", "updated_at"],
}

_migration_done = False
_MIGRATION_LOCK = threading.Lock()


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA foreign_keys = ON")
    except sqlite3.OperationalError:
        pass
    return conn


def retry_on_db_lock(max_retries: int = 5, delay: float = 0.1):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            current_delay = delay
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except sqlite3.OperationalError as exc:
                    if "locked" in str(exc).lower():
                        last_exc = exc
                        time.sleep(current_delay)
                        current_delay *= 2
                    else:
                        raise
            if last_exc:
                raise last_exc
        return wrapper
    return decorator


def json_path(name: str) -> Path:
    return AGENT_DATA / f"{name}.json"


def load_json_records(name: str) -> list[dict]:
    path = json_path(name)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save_json_records(name: str, records: list[dict]) -> None:
    path = json_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def normalize_record(table: str, record: dict) -> dict:
    timestamp = now()
    clean = {field: record.get(field, "") for field in TABLES[table]}
    clean["id"] = str(clean.get("id") or uuid4())[:8]
    clean["created_at"] = clean.get("created_at") or timestamp
    clean["updated_at"] = clean.get("updated_at") or timestamp
    if "optimistic_version" in TABLES[table] and not clean.get("optimistic_version"):
        clean["optimistic_version"] = 1
    return clean


@retry_on_db_lock()
def upsert_record(table: str, record: dict) -> dict:
    clean = normalize_record(table, record)
    fields = TABLES[table]
    placeholders = ", ".join("?" for _ in fields)
    updates = ", ".join(f"{field}=excluded.{field}" for field in fields if field != "id")
    sql = f"INSERT INTO {table} ({', '.join(fields)}) VALUES ({placeholders}) ON CONFLICT(id) DO UPDATE SET {updates}"
    with connect() as conn:
        conn.execute(sql, [clean.get(field, "") for field in fields])
        conn.commit()
    return clean


@retry_on_db_lock()
def table_count(table: str) -> int:
    with connect() as conn:
        try:
            row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
            return int(row["n"]) if row else 0
        except sqlite3.OperationalError:
            return 0


@retry_on_db_lock()
def _json_migration_done(table: str) -> bool:
    with connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM json_migrations WHERE table_name = ?", (table,)
        ).fetchone()
        return row is not None


@retry_on_db_lock()
def _mark_json_migration_done(table: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO json_migrations (table_name, completed_at) VALUES (?, ?)",
            (table, now()),
        )
        conn.commit()


def migrate_json_to_sqlite_if_needed() -> None:
    # Double-checked locking, matching artifact_store.py/event_store.py/
    # audiogen_job_store.py's ensure_schema()-style pattern: an unlocked
    # check-then-act here left a narrow startup-only race where concurrent
    # early requests could both see _migration_done as False and both run
    # the migration loop.
    #
    # Found 2026-08-11 (staff-review correctness pass): this previously used
    # `table_count(table) > 0` as its "already migrated" check. A crash
    # partway through a table's record loop (process killed, disk full,
    # malformed JSON record) left that table with >0 rows but an incomplete
    # import -- and on the next startup it would be silently skipped
    # forever, since it already had "some" rows. The json_migrations table
    # (created in init_db()) now records a per-table completion marker
    # written only after that table's full loop finishes without raising,
    # so a partial import is retried on next startup instead of silently
    # accepted. upsert_record's INSERT...ON CONFLICT(id) DO UPDATE makes
    # retrying an already-partially-imported table safe (idempotent by id).
    global _migration_done
    if _migration_done:
        return
    with _MIGRATION_LOCK:
        if _migration_done:
            return
        for table in TABLES:
            if _json_migration_done(table):
                continue
            for record in load_json_records(table):
                upsert_record(table, record)
            _mark_json_migration_done(table)
        _migration_done = True


import sys
import os

def is_in_test_process() -> bool:
    if "pytest" in sys.modules:
        return True
    if any("pytest" in arg for arg in sys.argv):
        return True
    if os.environ.get("AUDIO_TOO_TESTING") == "1":
        return True
    return False


def assert_safe_db_for_migration_or_rollback(is_destructive: bool = False) -> None:
    # Target path resolved
    resolved_path = Path(DB_PATH).resolve()
    real_db_path = (REPO_ROOT / "data" / "audio_too.db").resolve()
    
    # 1. Reject if target path is exactly the live business DB
    if resolved_path == real_db_path:
        if is_destructive or is_in_test_process():
            raise PermissionError(f"Database mutation/rollback rejected on production-like path: {resolved_path}")
            
    # 2. Reject if resolved path contains indicators of production/business DB layout
    resolved_str = str(resolved_path)
    if "Audio_Engineering_Company/Audio_Too/data/audio_too.db" in resolved_str:
        if is_destructive or is_in_test_process():
            raise PermissionError(f"Database mutation/rollback rejected on production-like path: {resolved_path}")
            
    if resolved_path.name == "audio_too.db" and "data" in resolved_path.parts:
        if not any(p.startswith("pytest-of-") or "tmp" in p.lower() or "temp" in p.lower() for p in resolved_path.parts):
            if is_destructive or is_in_test_process():
                raise PermissionError(f"Database mutation/rollback rejected on production-like path: {resolved_path}")

    # 3. If running inside a test process or is_destructive, enforce strict temporary test DB properties
    if is_in_test_process() or is_destructive:
        is_temp = False
        temp_prefixes = ["/var/", "/tmp/", "/private/var/", "/private/tmp/"]
        for prefix in temp_prefixes:
            if resolved_str.startswith(prefix):
                is_temp = True
                break
        if "pytest-of-" in resolved_str:
            is_temp = True
        if not is_temp:
            raise PermissionError(f"Database path is not in a temporary test directory: {resolved_path}")
            
        marker_file = resolved_path.with_suffix(".test_marker")
        if is_in_test_process() and not is_destructive:
            if not marker_file.exists():
                create_test_marker(resolved_path)
            
        # Enforce marker only for destructive operations
        if is_destructive:
            has_marker_table = False
            if resolved_path.exists() and resolved_path.stat().st_size > 0:
                try:
                    with sqlite3.connect(resolved_path) as conn:
                        row = conn.execute("SELECT value FROM test_metadata WHERE key = 'test_only'").fetchone()
                        if row and row[0] == 'true':
                            has_marker_table = True
                except Exception:
                    pass
                    
            if not marker_file.exists() and not has_marker_table:
                raise PermissionError(f"Database lacks required test marker: {resolved_path}")
                
            if marker_file.exists():
                try:
                    content = marker_file.read_text().strip()
                    if not content.startswith("TEST_ONLY_"):
                        raise PermissionError(f"Invalid test marker content: {resolved_path}")
                except Exception as exc:
                    raise PermissionError(f"Failed to read test marker: {exc}")


def create_test_marker(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    marker_file = path.with_suffix(".test_marker")
    marker_file.write_text(f"TEST_ONLY_{uuid4()}")


@retry_on_db_lock()
def init_db() -> None:
    assert_safe_db_for_migration_or_rollback(is_destructive=False)
    # Fast path: migrations are append-only within a process; once this
    # process has verified/applied them, repeated init_db() calls (one per
    # data read) can skip the whole scan. rollback_db() clears the marker.
    current_path = Path(DB_PATH).resolve()
    if getattr(init_db, "_completed_path", None) == current_path:
        return

    # Ensure migrations schema table exists
    with connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
        """)
        # Completion marker for the legacy JSON->SQLite import (see
        # migrate_json_to_sqlite_if_needed) -- distinct from schema_migrations,
        # which tracks the *.sql schema files, not this one-time data import.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS json_migrations (
                table_name TEXT PRIMARY KEY,
                completed_at TEXT NOT NULL
            )
        """)
        conn.commit()

    migrations_dir = Path(__file__).resolve().parent / "migrations"
    migration_files = sorted(list(migrations_dir.glob("*.sql")))

    for migration_file in migration_files:
        version_str = migration_file.name.split("_")[0]
        try:
            version = int(version_str)
        except ValueError:
            continue

        with connect() as conn:
            row = conn.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (version,)).fetchone()
            if row:
                continue

            print(f"[db] Applying migration {migration_file.name}...", flush=True)
            sql_content = migration_file.read_text(encoding="utf-8")
            try:
                conn.executescript(sql_content)
                conn.execute(
                    "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                    (version, migration_file.name, now())
                )
                conn.commit()
            except Exception as exc:
                conn.rollback()
                print(f"[db] ERROR: Migration {migration_file.name} failed: {exc}", flush=True)
                raise

    migrate_json_to_sqlite_if_needed()
    init_db._completed_path = Path(DB_PATH).resolve()


@retry_on_db_lock()
def rollback_db(target_version: int) -> None:
    """Roll back migrations down to (and including) target_version."""
    assert_safe_db_for_migration_or_rollback(is_destructive=True)
    # Schema changes invalidate this process's fast-path marker.
    init_db._completed_path = None
    with connect() as conn:
        applied = conn.execute("SELECT version, name FROM schema_migrations ORDER BY version DESC").fetchall()

    for row in applied:
        version = row["version"]
        if version < target_version:
            break

        # Match either name-based or version-based rollback file
        rollback_file = Path(__file__).resolve().parent / "migrations" / "rollback" / f"{version:03d}_rollback.sql"
        if not rollback_file.exists():
            continue

        print(f"[db] Rolling back migration {version} ({row['name']})...", flush=True)
        sql_content = rollback_file.read_text(encoding="utf-8")
        with connect() as conn:
            try:
                conn.executescript(sql_content)
                conn.execute("DELETE FROM schema_migrations WHERE version = ?", (version,))
                conn.commit()
            except Exception as exc:
                conn.rollback()
                print(f"[db] ERROR: Rollback of version {version} failed: {exc}", flush=True)
                raise


@retry_on_db_lock()
def list_records(table: str) -> list[dict]:
    if table not in TABLES:
        raise KeyError(f"Unknown table: {table}")
    with connect() as conn:
        rows = conn.execute(f"SELECT * FROM {table} ORDER BY created_at DESC").fetchall()
    return [dict(row) for row in rows]


def export_json_snapshots() -> list[Path]:
    """Write current SQLite tables to agents/Shared/data/*.json for backup/export only."""
    written: list[Path] = []
    for table in TABLES:
        save_json_records(table, list_records(table))
        written.append(json_path(table))
    return written


@retry_on_db_lock()
def replace_records(table: str, records: list[dict]) -> None:
    if table not in TABLES:
        raise KeyError(f"Unknown table: {table}")
    with connect() as conn:
        conn.execute(f"DELETE FROM {table}")
        conn.commit()
    for record in records:
        upsert_record(table, record)


def add_record(table: str, record: dict) -> dict:
    return upsert_record(table, {"id": str(uuid4())[:8], "created_at": now(), "updated_at": now(), **record})


@retry_on_db_lock()
def update_record(table: str, record_id: str, updates: dict, search_fields: list[str] | None = None) -> dict | None:
    if table not in TABLES:
        raise KeyError(f"Unknown table: {table}")
    search_fields = search_fields or []
    invalid_search_fields = set(search_fields) - set(TABLES[table])
    if invalid_search_fields:
        raise KeyError(f"Unknown search field(s) for {table}: {', '.join(sorted(invalid_search_fields))}")
    needle = record_id.strip()

    where_clauses = ["LOWER(id) = LOWER(?)"]
    params = [needle]
    for field in search_fields:
        where_clauses.append(f"LOWER({field}) = LOWER(?)")
        params.append(needle)

    sql = f"SELECT * FROM {table} WHERE " + " OR ".join(where_clauses) + " LIMIT 1"
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(sql, params).fetchone()
        if not row:
            return None

        target = dict(row)
        immutable_fields = {"id", "created_at", "optimistic_version"}
        allowed_updates = {
            key: value
            for key, value in updates.items()
            if key in TABLES[table] and key not in immutable_fields
        }
        target.update(allowed_updates)
        target["updated_at"] = now()

        if "optimistic_version" in target:
            stored_version = int(target["optimistic_version"] or 1)
            client_version = updates.get("optimistic_version")
            if client_version is not None and int(client_version) != stored_version:
                raise ValueError(
                    f"Concurrency conflict: Record {record_id} has been modified by another process."
                )
            target["optimistic_version"] = stored_version + 1

        fields = TABLES[table]
        assignments = ", ".join(f"{field} = ?" for field in fields if field != "id")
        conn.execute(
            f"UPDATE {table} SET {assignments} WHERE id = ?",
            [target.get(field, "") for field in fields if field != "id"] + [target["id"]],
        )
        conn.commit()
        return target


@retry_on_db_lock()
def update_status(table: str, record_id: str, status: str) -> dict | None:
    if table not in TABLES:
        raise KeyError(f"Unknown table: {table}")
    with connect() as conn:
        row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (record_id,)).fetchone()
        if not row:
            return None
        target = dict(row)
        if "optimistic_version" in target:
            target["optimistic_version"] = int(target["optimistic_version"]) + 1
        target["status"] = status
        target["updated_at"] = now()

        fields = TABLES[table]
        placeholders = ", ".join("?" for _ in fields)
        updates = ", ".join(f"{field}=excluded.{field}" for field in fields if field != "id")
        sql = f"INSERT INTO {table} ({', '.join(fields)}) VALUES ({placeholders}) ON CONFLICT(id) DO UPDATE SET {updates}"
        conn.execute(sql, [target.get(field, "") for field in fields])
        conn.commit()
    return target


def summary() -> dict:
    clients = list_records("clients")
    projects = list_records("projects")
    invoices = list_records("invoices")
    leads = list_records("leads")
    campaigns = list_records("campaigns")
    drafts = list_records("drafts")
    draft_invoices = [item for item in invoices if item.get("status") == "Draft"]
    active_projects = [item for item in projects if item.get("status", "Open") not in {"Closed", "Complete", "Completed"}]
    active_leads = [item for item in leads if item.get("status", "New") not in {"Closed", "Not interested"}]
    enquiries = list_records("enquiries")
    new_enquiries = [item for item in enquiries if item.get("status", "New") == "New"]
    return {
        "clients": len(clients),
        "active_projects": len(active_projects),
        "draft_invoices": len(draft_invoices),
        "draft_invoice_value": sum(float(item.get("total") or 0) for item in draft_invoices),
        "active_leads": len(active_leads),
        "campaigns": len(campaigns),
        "pending_drafts": len([item for item in drafts if item.get("status") == "Pending"]),
        "new_enquiries": len(new_enquiries),
    }
