"""Tests for resolving a project's already-uploaded single-file source
audio (Phase 3 of docs/KENN_HUB_UNIFICATION_PLAN_2026-08-05.md)."""

from __future__ import annotations

import sys
from pathlib import Path

WEBSITE = Path(__file__).resolve().parent.parent.parent / "business" / "app"
sys.path.insert(0, str(WEBSITE))

from kenn.core.project_source import resolve_project_source_audio


def _init_db(tmp_path, monkeypatch):
    import db

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "audio_too.db")
    monkeypatch.setattr(db, "AGENT_DATA", tmp_path / "legacy-json")
    monkeypatch.setattr(db, "_migration_done", False)
    db.init_db()
    return db


def test_resolves_most_recent_mix_review_for_project(tmp_path, monkeypatch) -> None:
    db = _init_db(tmp_path, monkeypatch)

    upload_root = tmp_path / "uploads"
    upload_root.mkdir()
    (upload_root / "old_track.wav").write_bytes(b"OLD")
    (upload_root / "new_track.wav").write_bytes(b"NEW")

    monkeypatch.setattr(
        "audio_analysis.mix_review.mix_review_config.UPLOAD_ROOT", upload_root, raising=False
    )

    with db.connect() as conn:
        conn.execute(
            """INSERT INTO mix_reviews (id, title, original_name, stored_name, project_id, created_at, status)
               VALUES ('r1', 'Old', 'old.wav', 'old_track.wav', 'kenn-abc', '2026-08-01 00:00:00', 'completed')"""
        )
        conn.execute(
            """INSERT INTO mix_reviews (id, title, original_name, stored_name, project_id, created_at, status)
               VALUES ('r2', 'New', 'new.wav', 'new_track.wav', 'kenn-abc', '2026-08-05 00:00:00', 'completed')"""
        )
        conn.commit()

    result = resolve_project_source_audio("kenn-abc")
    assert result == (b"NEW", "new.wav")


def test_returns_none_for_unknown_project(tmp_path, monkeypatch) -> None:
    _init_db(tmp_path, monkeypatch)
    assert resolve_project_source_audio("kenn-does-not-exist") is None


def test_returns_none_for_empty_project_id(tmp_path, monkeypatch) -> None:
    _init_db(tmp_path, monkeypatch)
    assert resolve_project_source_audio("") is None


def test_returns_none_if_file_missing_on_disk(tmp_path, monkeypatch) -> None:
    db = _init_db(tmp_path, monkeypatch)
    upload_root = tmp_path / "uploads"
    upload_root.mkdir()
    monkeypatch.setattr(
        "audio_analysis.mix_review.mix_review_config.UPLOAD_ROOT", upload_root, raising=False
    )

    with db.connect() as conn:
        conn.execute(
            """INSERT INTO mix_reviews (id, title, original_name, stored_name, project_id, created_at, status)
               VALUES ('r1', 'Gone', 'gone.wav', 'missing.wav', 'kenn-abc', '2026-08-05 00:00:00', 'completed')"""
        )
        conn.commit()

    assert resolve_project_source_audio("kenn-abc") is None


def test_falls_back_to_stem_separation_source_when_no_mix_review(tmp_path, monkeypatch) -> None:
    """Real constraint found live: mix_reviews' source WAV is deliberately
    deleted after analysis, so a stem-separation-sourced project (whose
    source_path persists -- no cleanup call anywhere in
    stem_separation_job_store.py) is often the only resolvable source."""
    db = _init_db(tmp_path, monkeypatch)
    source_path = tmp_path / "source.wav"
    source_path.write_bytes(b"STEM-SOURCE")

    with db.connect() as conn:
        conn.execute(
            """INSERT INTO stem_separation_jobs
               (id, status, source_filename, source_path, project_id, created_at, updated_at)
               VALUES ('job-1', 'completed', 'track.wav', ?, 'kenn-abc', '2026-08-05 00:00:00', '2026-08-05 00:00:00')""",
            (str(source_path),),
        )
        conn.commit()

    assert resolve_project_source_audio("kenn-abc") == (b"STEM-SOURCE", "track.wav")


def test_prefers_mix_review_source_when_both_exist(tmp_path, monkeypatch) -> None:
    db = _init_db(tmp_path, monkeypatch)
    upload_root = tmp_path / "uploads"
    upload_root.mkdir()
    (upload_root / "review_track.wav").write_bytes(b"REVIEW")
    monkeypatch.setattr(
        "audio_analysis.mix_review.mix_review_config.UPLOAD_ROOT", upload_root, raising=False
    )
    source_path = tmp_path / "source.wav"
    source_path.write_bytes(b"STEM-SOURCE")

    with db.connect() as conn:
        conn.execute(
            """INSERT INTO mix_reviews (id, title, original_name, stored_name, project_id, created_at, status)
               VALUES ('r1', 'Review', 'review.wav', 'review_track.wav', 'kenn-abc', '2026-08-05 00:00:00', 'completed')"""
        )
        conn.execute(
            """INSERT INTO stem_separation_jobs
               (id, status, source_filename, source_path, project_id, created_at, updated_at)
               VALUES ('job-1', 'completed', 'track.wav', ?, 'kenn-abc', '2026-08-05 00:00:00', '2026-08-05 00:00:00')""",
            (str(source_path),),
        )
        conn.commit()

    assert resolve_project_source_audio("kenn-abc") == (b"REVIEW", "review.wav")
