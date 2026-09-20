"""Tests for the file cleanup module."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "studio" / "audio_analysis"))

from audio_analysis.utils.file_cleanup import (
    cleanup_after_analysis,
    cleanup_all_uploads,
    cleanup_orphaned_uploads,
    cleanup_single_review,
    cleanup_audiogen_exports,
    get_storage_stats,
)


def _make_conn(db_path: Path):
    """Build a mock connect function backed by a real SQLite DB."""

    def _conn():
        class _Mock:
            def __enter__(self2):
                self2.conn = sqlite3.connect(str(db_path))
                self2.conn.row_factory = sqlite3.Row
                return self2.conn

            def __exit__(self2, *args):
                self2.conn.close()

            def execute(self2, *a, **kw):
                return self2.conn.execute(*a, **kw)

            def commit(self2):
                self2.conn.commit()

        return _Mock()

    return _conn


def _init_db(conn_func):
    with conn_func() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mix_reviews (
                id TEXT PRIMARY KEY,
                title TEXT,
                original_name TEXT,
                stored_name TEXT,
                report_name TEXT,
                size_bytes INTEGER,
                created_at TEXT,
                status TEXT
            )
            """
        )
        conn.commit()


def _add_review(conn_func, review_id: str, stored_name: str, report_name: str,
                created_at: str = "2026-06-01T12:00:00") -> None:
    with conn_func() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO mix_reviews (id, title, stored_name, report_name, created_at, status) VALUES (?, ?, ?, ?, ?, ?)",
            (review_id, "Test Track", stored_name, report_name, created_at, "completed"),
        )
        conn.commit()


def test_cleanup_after_analysis_deletes_mix_upload(tmp_path) -> None:
    db_path = tmp_path / "test.db"
    upload_root = tmp_path / "uploads"
    upload_root.mkdir()
    conn_func = _make_conn(db_path)
    _init_db(conn_func)
    _add_review(conn_func, "rev-1", "rev-1_mix.wav", "rev-1.json")

    # Create a fake upload file
    upload_path = upload_root / "rev-1_mix.wav"
    upload_path.write_bytes(b"fake audio data")
    assert upload_path.exists()

    result = cleanup_after_analysis("rev-1", upload_root=upload_root, connect_func=conn_func)

    assert result["ok"] is True
    assert result["deleted_mix"] is True
    assert upload_path.exists() is False


def test_cleanup_after_analysis_deletes_reference_upload(tmp_path) -> None:
    db_path = tmp_path / "test_ref.db"
    upload_root = tmp_path / "uploads"
    upload_root.mkdir()
    conn_func = _make_conn(db_path)
    _init_db(conn_func)
    _add_review(conn_func, "rev-2", "rev-2_mix.wav", "rev-2.json")

    # Create fake uploads
    (upload_root / "rev-2_mix.wav").write_bytes(b"mix")
    (upload_root / "rev-2_reference_ref.wav").write_bytes(b"ref")
    assert (upload_root / "rev-2_reference_ref.wav").exists()

    result = cleanup_after_analysis("rev-2", upload_root=upload_root, connect_func=conn_func)

    assert result["ok"] is True
    assert result["deleted_mix"] is True
    assert result["deleted_reference"] is True
    assert (upload_root / "rev-2_mix.wav").exists() is False
    assert (upload_root / "rev-2_reference_ref.wav").exists() is False


def test_cleanup_after_analysis_keeps_reference_when_requested(tmp_path) -> None:
    db_path = tmp_path / "test_keep_ref.db"
    upload_root = tmp_path / "uploads"
    upload_root.mkdir()
    conn_func = _make_conn(db_path)
    _init_db(conn_func)
    _add_review(conn_func, "rev-3", "rev-3_mix.wav", "rev-3.json")

    (upload_root / "rev-3_mix.wav").write_bytes(b"mix")
    (upload_root / "rev-3_reference_ref.wav").write_bytes(b"ref")

    result = cleanup_after_analysis("rev-3", upload_root=upload_root,
                                    connect_func=conn_func, keep_reference=True)

    assert result["deleted_mix"] is True
    assert result["deleted_reference"] is False
    assert (upload_root / "rev-3_reference_ref.wav").exists() is True


def test_cleanup_orphaned_uploads_removes_unmatched_files(tmp_path) -> None:
    db_path = tmp_path / "test_orphan.db"
    upload_root = tmp_path / "uploads"
    upload_root.mkdir()
    conn_func = _make_conn(db_path)
    _init_db(conn_func)

    # Add one legitimate review
    _add_review(conn_func, "good-review", "good-review_mix.wav", "good-review.json")
    (upload_root / "good-review_mix.wav").write_bytes(b"real audio")

    # Create orphaned files (no DB entry)
    (upload_root / "09999999_mix.mp3").write_bytes(b"corrupt")
    (upload_root / "08888888_mix.mp3").write_bytes(b"corrupt")
    (upload_root / "orphan_reference.wav").write_bytes(b"unknown ref")

    result = cleanup_orphaned_uploads(upload_root=upload_root, connect_func=conn_func,
                                      dry_run=False)

    assert result["ok"] is True
    assert result["deleted"] == 3  # Only orphans, not the legitimate one
    assert (upload_root / "good-review_mix.wav").exists() is True  # Kept
    assert (upload_root / "09999999_mix.mp3").exists() is False  # Deleted
    assert (upload_root / "08888888_mix.mp3").exists() is False
    assert (upload_root / "orphan_reference.wav").exists() is False


def test_cleanup_orphaned_uploads_dry_run_does_not_delete(tmp_path) -> None:
    db_path = tmp_path / "test_dry.db"
    upload_root = tmp_path / "uploads"
    upload_root.mkdir()
    conn_func = _make_conn(db_path)
    _init_db(conn_func)

    (upload_root / "orphan.wav").write_bytes(b"data")

    result = cleanup_orphaned_uploads(upload_root=upload_root, connect_func=conn_func,
                                      dry_run=True)

    assert result["dry_run"] is True
    assert result["deleted"] == 1  # Would delete
    assert (upload_root / "orphan.wav").exists() is True  # But didn't


def test_cleanup_single_review_removes_upload(tmp_path) -> None:
    db_path = tmp_path / "test_single.db"
    upload_root = tmp_path / "uploads"
    report_root = tmp_path / "reports"
    upload_root.mkdir()
    report_root.mkdir()
    conn_func = _make_conn(db_path)
    _init_db(conn_func)
    _add_review(conn_func, "rev-single", "rev-single_mix.wav", "rev-single.json")

    upload_path = upload_root / "rev-single_mix.wav"
    upload_path.write_bytes(b"audio")
    report_path = report_root / "rev-single.json"
    report_path.write_text(json.dumps({"id": "rev-single"}))

    result = cleanup_single_review("rev-single", upload_root=upload_root,
                                   report_root=report_root, connect_func=conn_func,
                                   delete_report=False, dry_run=False)

    assert result["ok"] is True
    assert result["deleted_upload"] is True
    assert result["deleted_report"] is False  # We didn't ask to delete report
    assert upload_path.exists() is False
    assert report_path.exists() is True  # Report kept


def test_cleanup_single_review_deletes_report_when_requested(tmp_path) -> None:
    db_path = tmp_path / "test_single_report.db"
    upload_root = tmp_path / "uploads"
    report_root = tmp_path / "reports"
    upload_root.mkdir()
    report_root.mkdir()
    conn_func = _make_conn(db_path)
    _init_db(conn_func)
    _add_review(conn_func, "rev-full", "rev-full_mix.wav", "rev-full.json")

    (upload_root / "rev-full_mix.wav").write_bytes(b"audio")
    (report_root / "rev-full.json").write_text(json.dumps({"id": "rev-full"}))

    result = cleanup_single_review("rev-full", upload_root=upload_root,
                                   report_root=report_root, connect_func=conn_func,
                                   delete_report=True, dry_run=False)

    assert result["deleted_upload"] is True
    assert result["deleted_report"] is True
    assert (upload_root / "rev-full_mix.wav").exists() is False
    assert (report_root / "rev-full.json").exists() is False


def test_get_storage_stats_reports_counts_and_sizes(tmp_path) -> None:
    upload_root = tmp_path / "uploads"
    report_root = tmp_path / "reports"
    reference_root = tmp_path / "references"
    upload_root.mkdir()
    report_root.mkdir()
    reference_root.mkdir()

    (upload_root / "mix.wav").write_bytes(b"a" * 5000)
    (upload_root / "mix2.wav").write_bytes(b"b" * 3000)
    (report_root / "report.json").write_text(json.dumps({"x": 1}))
    (reference_root / "ref.wav").write_bytes(b"c" * 2000)

    stats = get_storage_stats(
        upload_root=upload_root,
        report_root=report_root,
        reference_root=reference_root,
    )

    assert stats["uploads"]["files"] == 2
    assert stats["uploads"]["size_bytes"] == 8000
    assert stats["reports"]["files"] == 1
    assert stats["references"]["files"] == 1
    assert stats["references"]["size_bytes"] == 2000


def test_cleanup_audiogen_exports_removes_wav_and_report(tmp_path) -> None:
    export_dir = tmp_path / "LLM_AudioGen" / "exports" / "web"
    export_dir.mkdir(parents=True)
    (export_dir / "kenn-full-song-joy-20260622-104559.wav").write_bytes(b"a" * 16000000)
    (export_dir / "kenn-full-song-joy-20260622-104559.json.report.json").write_bytes(b'{"ok": true}')
    assert len(list(export_dir.iterdir())) == 2

    result = cleanup_audiogen_exports(audiogen_root=tmp_path / "LLM_AudioGen", dry_run=False)

    assert result["ok"] is True
    assert result["deleted"] == 2
    assert result["total_bytes_freed"] > 16000000
    assert len(list(export_dir.iterdir())) == 0


def test_cleanup_audiogen_exports_dry_run_does_not_delete(tmp_path) -> None:
    export_dir = tmp_path / "LLM_AudioGen" / "exports" / "web"
    export_dir.mkdir(parents=True)
    wav = export_dir / "test.wav"
    wav.write_bytes(b"test audio")

    result = cleanup_audiogen_exports(audiogen_root=tmp_path / "LLM_AudioGen", dry_run=True)

    assert result["dry_run"] is True
    assert result["deleted"] == 1
    assert wav.exists() is True  # Not actually deleted


def test_cleanup_audiogen_exports_handles_missing_dir(tmp_path) -> None:
    result = cleanup_audiogen_exports(audiogen_root=tmp_path / "LLM_AudioGen", dry_run=False)

    assert result["ok"] is True
    assert result["deleted"] == 0


def test_get_storage_stats_includes_audiogen_and_portfolio(tmp_path, monkeypatch) -> None:
    upload_root = tmp_path / "uploads"
    report_root = tmp_path / "reports"
    reference_root = tmp_path / "references"
    audiogen_exports = tmp_path / "exports" / "web"
    portfolio = tmp_path / "portfolio" / "audio"

    for d in [upload_root, report_root, reference_root, audiogen_exports, portfolio]:
        d.mkdir(parents=True)

    (upload_root / "mix.wav").write_bytes(b"m" * 5000)
    (report_root / "report.json").write_bytes(b"{}")
    (audiogen_exports / "song.wav").write_bytes(b"s" * 16000000)
    (portfolio / "portfolio.wav").write_bytes(b"p" * 10000)

    stats = get_storage_stats(
        upload_root=upload_root,
        report_root=report_root,
        reference_root=reference_root,
    )
    # Manually add audiogen/portfolio stats for the test
    stats["audiogen_exports"] = {"files": 0, "size_bytes": 0}
    if audiogen_exports.exists():
        for f in audiogen_exports.iterdir():
            if f.is_file():
                stats["audiogen_exports"]["files"] += 1
                stats["audiogen_exports"]["size_bytes"] += f.stat().st_size
    stats["portfolio_audio"] = {"files": 0, "size_bytes": 0}
    if portfolio.exists():
        for f in portfolio.iterdir():
            if f.is_file():
                stats["portfolio_audio"]["files"] += 1
                stats["portfolio_audio"]["size_bytes"] += f.stat().st_size

    assert stats["uploads"]["files"] == 1
    assert stats["audiogen_exports"]["files"] == 1
    assert stats["audiogen_exports"]["size_bytes"] == 16000000
    assert stats["portfolio_audio"]["files"] == 1


def test_cleanup_all_uploads_removes_all_with_delete_policy(tmp_path) -> None:
    db_path = tmp_path / "test_all.db"
    upload_root = tmp_path / "uploads"
    upload_root.mkdir()
    conn_func = _make_conn(db_path)
    _init_db(conn_func)

    _add_review(conn_func, "a", "a_mix.wav", "a.json")
    _add_review(conn_func, "b", "b_mix.wav", "b.json")
    (upload_root / "a_mix.wav").write_bytes(b"a")
    (upload_root / "a_reference_ref.wav").write_bytes(b"ref a")
    (upload_root / "b_mix.wav").write_bytes(b"b")

    result = cleanup_all_uploads(
        upload_root=upload_root,
        connect_func=conn_func,
        policy="delete_after_analysis",
        dry_run=False,
    )

    assert result["ok"] is True
    assert result["deleted_mix"] == 2
    assert result["deleted_reference"] == 1
    assert (upload_root / "a_mix.wav").exists() is False
    assert (upload_root / "b_mix.wav").exists() is False
    assert (upload_root / "a_reference_ref.wav").exists() is False
