"""Backup, restore, integrity, and rollback tests."""

from __future__ import annotations

import io
import sqlite3
import tarfile
from pathlib import Path

import pytest

from nite_core.recovery import RecoveryError, create_archive, restore_archive, verify_archive


def _fixture_repo(root: Path) -> None:
    (root / "audio_too").mkdir(parents=True)
    (root / "audio_too/service.py").write_text("VERSION = 'good'\n", encoding="utf-8")
    (root / "studio/kenn/kenn/Training_Data_Notes").mkdir(parents=True)
    (root / "studio/kenn/kenn/Training_Data_Notes/gain.md").write_text(
        "Keep headroom.\n", encoding="utf-8"
    )
    (root / "studio/kenn/kenn/data/index/versions/v1").mkdir(parents=True)
    (root / "studio/kenn/kenn/data/index/CURRENT").write_text("v1\n", encoding="utf-8")
    (root / "studio/kenn/kenn/data/index/versions/v1/manifest.json").write_text(
        '{"version":"v1"}\n', encoding="utf-8"
    )
    (root / "data").mkdir()
    with sqlite3.connect(root / "data/audio_too.db") as conn:
        conn.execute("CREATE TABLE records (value TEXT)")
        conn.execute("INSERT INTO records VALUES ('original')")


def test_complete_restore_and_second_restore_rollback(tmp_path: Path) -> None:
    source = tmp_path / "source"
    restored = tmp_path / "restored"
    archive = tmp_path / "recovery.tar.gz"
    _fixture_repo(source)

    created = create_archive(source, archive)
    verified = verify_archive(archive)
    first = restore_archive(archive, restored)
    assert created["file_count"] == verified["file_count"] == first["file_count"]
    assert first["index_version"] == "v1"
    assert (restored / "audio_too/service.py").read_text() == "VERSION = 'good'\n"
    with sqlite3.connect(restored / "data/audio_too.db") as conn:
        assert conn.execute("SELECT value FROM records").fetchone()[0] == "original"

    (restored / "audio_too/service.py").write_text("VERSION = 'broken'\n", encoding="utf-8")
    with sqlite3.connect(restored / "data/audio_too.db") as conn:
        conn.execute("UPDATE records SET value = 'corrupt'")
    restore_archive(archive, restored)

    assert (restored / "audio_too/service.py").read_text() == "VERSION = 'good'\n"
    with sqlite3.connect(restored / "data/audio_too.db") as conn:
        assert conn.execute("SELECT value FROM records").fetchone()[0] == "original"


def test_tampered_archive_is_rejected_before_restore(tmp_path: Path) -> None:
    source = tmp_path / "source"
    archive = tmp_path / "recovery.tar.gz"
    tampered = tmp_path / "tampered.tar.gz"
    _fixture_repo(source)
    create_archive(source, archive)

    with tarfile.open(archive, "r:gz") as original, tarfile.open(tampered, "w:gz") as changed:
        for member in original.getmembers():
            if member.name == "audio_too/service.py":
                body = b"VERSION = 'tampered'\n"
                member.size = len(body)
                changed.addfile(member, io.BytesIO(body))
            else:
                handle = original.extractfile(member) if member.isfile() else None
                changed.addfile(member, handle)

    with pytest.raises(RecoveryError, match="checksum"):
        verify_archive(tampered)

