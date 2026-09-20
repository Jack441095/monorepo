"""Database migration and concurrency contract tests."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server" / "app"))

import db  # noqa: E402


@pytest.fixture()
def migrated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "audio_too.db"
    monkeypatch.setattr(db, "DB_PATH", db_path)
    monkeypatch.setattr(db, "_migration_done", False)
    monkeypatch.setattr(db, "AGENT_DATA", tmp_path / "legacy-json")
    db.init_db()
    return db_path


def test_all_migrations_are_recorded_and_repeatable(migrated_db: Path) -> None:
    db.init_db()
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version"
        ).fetchall()
    assert [tuple(row) for row in rows] == [
        (1, "001_initial_schema.sql"),
        (2, "002_foreign_keys_and_indexes.sql"),
        (3, "003_optimistic_locking_and_jobs.sql"),
        (4, "004_api_idempotency.sql"),
        (5, "005_delivery_outbox.sql"),
        (6, "006_reference_profiles.sql"),
        (7, "007_audiogen_jobs.sql"),
        (8, "008_artifact_registry.sql"),
        (9, "009_domain_events.sql"),
        (10, "010_scheduled_tasks_and_jobs.sql"),
        (11, "011_automix_advisor_feedback.sql"),
        (12, "012_musical_role_corrections.sql"),
        (13, "013_automix_job_correlation_id.sql"),
        (14, "014_audiogen_job_automix_chain.sql"),
        (15, "015_listening_benchmark_ratings.sql"),
        (16, "016_podcast_reports.sql"),
        (17, "017_stem_separation_jobs.sql"),
        (18, "018_song_projects.sql"),
        (19, "019_song_projects_reference_track.sql"),
        (20, "020_project_revision_history.sql"),
        (21, "021_stem_separation_automix_chain.sql"),
        (22, "022_project_revision_outcome.sql"),
    ]


def test_legacy_rows_survive_upgrade(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE projects (
                   id TEXT PRIMARY KEY, client TEXT, project TEXT, service TEXT, status TEXT,
                   deadline TEXT, waiting_on TEXT, follow_up TEXT, next_action TEXT, source TEXT,
                   created_at TEXT, updated_at TEXT
               )"""
        )
        conn.execute(
            """INSERT INTO projects
               VALUES ('project-1', 'Client', 'Legacy project', 'Mixing', 'Open', '', '', '',
                       'Continue', 'legacy', '2026-01-01', '2026-01-01')"""
        )
        conn.commit()

    monkeypatch.setattr(db, "DB_PATH", db_path)
    monkeypatch.setattr(db, "_migration_done", False)
    monkeypatch.setattr(db, "AGENT_DATA", tmp_path / "legacy-json")
    db.init_db()

    with db.connect() as conn:
        project = conn.execute(
            "SELECT project, optimistic_version FROM projects WHERE id = 'project-1'"
        ).fetchone()
    assert tuple(project) == ("Legacy project", 1)


def test_foreign_keys_are_enforced_during_tests(migrated_db: Path) -> None:
    with db.connect() as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO automix_job_events
                   (id, job_id, status, message, created_at, updated_at)
                   VALUES ('event-1', 'missing-job', 'queued', '', '', '')"""
            )


def test_automix_workspace_does_not_require_crm_project(migrated_db: Path) -> None:
    with db.connect() as conn:
        conn.execute(
            """INSERT INTO automix_jobs
               (id, project_id, status, genre, style_prefs, error_message, result_path,
                iteration_count, created_at, updated_at)
               VALUES ('job-1', 'standalone-workspace', 'queued', 'pop', '{}', '', '', 0, '', '')"""
        )
        conn.commit()


def test_song_projects_table_and_optional_crm_link(migrated_db: Path) -> None:
    """song_projects is a separate entity from the CRM `projects` table
    (docs/KENN_HUB_UNIFICATION_PLAN_2026-08-05.md Phase 2) -- crm_project_id
    is optional, most KENN sessions have no CRM project at all."""
    with db.connect() as conn:
        conn.execute(
            """INSERT INTO song_projects (id, title, crm_project_id, created_at, updated_at)
               VALUES ('kenn-standalone', 'Untitled session', NULL, '2026-08-05', '2026-08-05')"""
        )
        conn.execute(
            """INSERT INTO projects
               (id, client, project, service, status, deadline, waiting_on, follow_up,
                next_action, source, created_at, updated_at)
               VALUES ('crm-1', 'Jordan', 'EP mix', 'Mixing', 'Open', '', '', '', '',
                       'test', '2026-08-05', '2026-08-05')"""
        )
        conn.execute(
            """INSERT INTO song_projects (id, title, crm_project_id, created_at, updated_at)
               VALUES ('kenn-linked', 'Neon Skies', 'crm-1', '2026-08-05', '2026-08-05')"""
        )
        conn.commit()
        rows = conn.execute(
            "SELECT id, crm_project_id FROM song_projects ORDER BY id"
        ).fetchall()
    assert [tuple(row) for row in rows] == [
        ("kenn-linked", "crm-1"),
        ("kenn-standalone", None),
    ]


def test_song_projects_crm_link_is_enforced_and_nullified_on_delete(migrated_db: Path) -> None:
    with db.connect() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO song_projects (id, title, crm_project_id, created_at, updated_at)
                   VALUES ('kenn-orphan', '', 'missing-crm-project', '2026-08-05', '2026-08-05')"""
            )

        conn.execute(
            """INSERT INTO projects
               (id, client, project, service, status, deadline, waiting_on, follow_up,
                next_action, source, created_at, updated_at)
               VALUES ('crm-2', 'Alex', 'Single', 'Mastering', 'Open', '', '', '', '',
                       'test', '2026-08-05', '2026-08-05')"""
        )
        conn.execute(
            """INSERT INTO song_projects (id, title, crm_project_id, created_at, updated_at)
               VALUES ('kenn-2', '', 'crm-2', '2026-08-05', '2026-08-05')"""
        )
        conn.commit()
        conn.execute("DELETE FROM projects WHERE id = 'crm-2'")
        conn.commit()
        row = conn.execute(
            "SELECT crm_project_id FROM song_projects WHERE id = 'kenn-2'"
        ).fetchone()
    assert row[0] is None


def test_mix_reviews_gains_project_id_column(migrated_db: Path) -> None:
    with db.connect() as conn:
        conn.execute(
            """INSERT INTO mix_reviews (id, title, project_id, created_at, status)
               VALUES ('review-1', 'Test Tone', 'kenn-standalone', '2026-08-05', 'completed')"""
        )
        conn.commit()
        row = conn.execute(
            "SELECT project_id FROM mix_reviews WHERE id = 'review-1'"
        ).fetchone()
    assert row[0] == "kenn-standalone"


def test_mix_reviews_migration_is_safe_against_pre_existing_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """018_song_projects.sql must not crash if mix_reviews already exists
    without a project_id column (the real-world case: mix_review.py's own
    init_reviews_table() creates it, independent of this migrations system)
    -- see the migration file's own comment for why."""
    db_path = tmp_path / "audio_too.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE mix_reviews (
                   id TEXT PRIMARY KEY, title TEXT, original_name TEXT, stored_name TEXT,
                   report_name TEXT, size_bytes INTEGER, created_at TEXT,
                   status TEXT DEFAULT 'completed', error TEXT
               )"""
        )
        conn.execute(
            "INSERT INTO mix_reviews (id, title, created_at) VALUES ('pre-existing', 'Old Review', '2026-01-01')"
        )
        conn.commit()

    monkeypatch.setattr(db, "DB_PATH", db_path)
    monkeypatch.setattr(db, "_migration_done", False)
    monkeypatch.setattr(db, "AGENT_DATA", tmp_path / "legacy-json")
    db.init_db()

    with db.connect() as conn:
        row = conn.execute(
            "SELECT title, project_id FROM mix_reviews WHERE id = 'pre-existing'"
        ).fetchone()
    assert tuple(row) == ("Old Review", "")


def test_update_record_increments_and_rejects_stale_versions(migrated_db: Path) -> None:
    record = db.add_record("clients", {"name": "Initial"})
    updated = db.update_record(
        "clients",
        record["id"],
        {"name": "Updated", "optimistic_version": 1},
    )
    assert updated is not None
    assert updated["name"] == "Updated"
    assert updated["optimistic_version"] == 2

    with pytest.raises(ValueError, match="Concurrency conflict"):
        db.update_record(
            "clients",
            record["id"],
            {"name": "Stale write", "optimistic_version": 1},
        )

    stored = db.list_records("clients")[0]
    assert stored["name"] == "Updated"
    assert stored["optimistic_version"] == 2


def test_update_record_rejects_unknown_search_field(migrated_db: Path) -> None:
    with pytest.raises(KeyError, match="Unknown search field"):
        db.update_record("clients", "anything", {}, search_fields=["not_a_column"])


def test_database_rollback_and_forward_replay(migrated_db: Path) -> None:
    # Verify migration 9 is initially applied
    with db.connect() as conn:
        row = conn.execute("SELECT 1 FROM schema_migrations WHERE version = 9").fetchone()
        assert row is not None

    # Rollback version 9
    db.rollback_db(9)
    with db.connect() as conn:
        row = conn.execute("SELECT 1 FROM schema_migrations WHERE version = 9").fetchone()
        assert row is None
        # Check trigger is dropped
        trigger_row = conn.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name='domain_events_no_update'").fetchone()
        assert trigger_row is None

    # Rollback down to 7 (8 and 7)
    db.rollback_db(7)
    with db.connect() as conn:
        row7 = conn.execute("SELECT 1 FROM schema_migrations WHERE version = 7").fetchone()
        row8 = conn.execute("SELECT 1 FROM schema_migrations WHERE version = 8").fetchone()
        assert row7 is None
        assert row8 is None
        
        # Verify audiogen_jobs table is dropped
        table_row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audiogen_jobs'").fetchone()
        assert table_row is None

    # Re-apply migrations using init_db
    db.init_db()
    with db.connect() as conn:
        for v in range(1, 10):
            row = conn.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (v,)).fetchone()
            assert row is not None
        
        # Verify table and trigger exist again
        table_row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audiogen_jobs'").fetchone()
        assert table_row is not None
        trigger_row = conn.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name='domain_events_no_update'").fetchone()
        assert trigger_row is not None



def test_migration_is_idempotent_under_concurrent_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """migrate_json_to_sqlite_if_needed() must run its migration body at most
    once even when called concurrently from multiple threads (P4 fix,
    2026-07-13 -- was an unlocked check-then-act, unlike the equivalent
    double-checked-locked pattern in artifact_store.py/event_store.py/
    audiogen_job_store.py)."""
    import threading

    db_path = tmp_path / "audio_too.db"
    monkeypatch.setattr(db, "DB_PATH", db_path)
    monkeypatch.setattr(db, "_migration_done", False)
    monkeypatch.setattr(db, "AGENT_DATA", tmp_path / "legacy-json")
    db.init_db()

    # init_db() above already ran migrate_json_to_sqlite_if_needed() once
    # (with _migration_done seeded False at line above), and since 2026-08-11
    # that run persists a completion marker per table in json_migrations --
    # unlike the old table_count(table) > 0 check, that marker survives
    # resetting the in-process _migration_done flag below (by design: it's
    # what makes a crash-then-restart retry an incomplete import instead of
    # silently re-skipping it, while NOT redundantly re-importing tables that
    # already completed). Clear it here so the concurrency race below
    # exercises a genuinely first-time migration, matching what resetting
    # _migration_done is meant to simulate.
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM json_migrations")
        conn.commit()

    call_count = 0
    real_load_json_records = db.load_json_records

    def counting_load_json_records(table):
        nonlocal call_count
        call_count += 1
        return real_load_json_records(table)

    monkeypatch.setattr(db, "load_json_records", counting_load_json_records)
    monkeypatch.setattr(db, "_migration_done", False)

    barrier = threading.Barrier(8)

    def run():
        barrier.wait()
        db.migrate_json_to_sqlite_if_needed()

    threads = [threading.Thread(target=run) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert db._migration_done is True
    # One full migration pass calls load_json_records once per table; a
    # second concurrent pass sneaking through the race would double this.
    assert call_count == len(db.TABLES)


def test_crash_mid_table_import_is_retried_not_silently_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A crash partway through one table's JSON import must not be treated
    as "already migrated" on the next startup just because the table ended
    up with >0 rows (the old table_count(table) > 0 check). The
    json_migrations completion marker is only written after a table's
    import loop finishes without raising, so a partial import is retried."""
    db_path = tmp_path / "audio_too.db"
    legacy_dir = tmp_path / "legacy-json"
    legacy_dir.mkdir()
    (legacy_dir / "clients.json").write_text(
        json.dumps([
            {"id": "c1", "name": "Client One"},
            {"id": "c2", "name": "Client Two"},
        ]),
        encoding="utf-8",
    )

    monkeypatch.setattr(db, "DB_PATH", db_path)
    monkeypatch.setattr(db, "_migration_done", False)
    monkeypatch.setattr(db, "AGENT_DATA", legacy_dir)
    db.init_db()

    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM json_migrations")
        conn.commit()
    monkeypatch.setattr(db, "_migration_done", False)

    real_upsert_record = db.upsert_record
    calls = {"n": 0}

    def flaky_upsert_record(table, record):
        if table == "clients":
            calls["n"] += 1
            if calls["n"] == 1:
                raise sqlite3.OperationalError("simulated crash mid-import")
        return real_upsert_record(table, record)

    monkeypatch.setattr(db, "upsert_record", flaky_upsert_record)

    with pytest.raises(sqlite3.OperationalError):
        db.migrate_json_to_sqlite_if_needed()

    # The crash must not have been silently swallowed into a "done" state.
    assert db._migration_done is False
    assert db._json_migration_done("clients") is False

    # Retry (e.g. next process startup): must actually reprocess the table,
    # not skip it just because it has 0 rows from the failed attempt --
    # and must not fail again now that upsert_record works normally.
    monkeypatch.setattr(db, "upsert_record", real_upsert_record)
    db.migrate_json_to_sqlite_if_needed()

    assert db._migration_done is True
    assert db._json_migration_done("clients") is True
    assert db.table_count("clients") == 2
