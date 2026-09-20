"""Tests for stem upload tokens and storage."""

from __future__ import annotations

import sys
import io
import struct
import zipfile
from pathlib import Path

WEBSITE = Path(__file__).resolve().parent.parent / "server" / "app"
sys.path.insert(0, str(WEBSITE))

from upload_tokens import make_upload_token, project_id_from_token, verify_upload_token  # noqa: E402


def _wav_bytes(n_samples: int = 64) -> bytes:
    data = (b"\x01\x00") * n_samples
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(data), b"WAVE", b"fmt ", 16, 1, 1, 44100, 88200, 2, 16, b"data", len(data),
    )
    return header + data


def test_upload_token_roundtrip() -> None:
    token = make_upload_token("abc12345", ttl_seconds=3600)
    assert verify_upload_token("abc12345", token)
    assert project_id_from_token(token) == "abc12345"
    assert not verify_upload_token("other", token)


def test_save_upload(tmp_path, monkeypatch) -> None:
    import artifact_store
    import db
    import stem_uploads

    monkeypatch.setattr(stem_uploads, "UPLOAD_ROOT", tmp_path / "uploads")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "audio_too.db")
    monkeypatch.setattr(db, "AGENT_DATA", tmp_path / "legacy-json")
    monkeypatch.setattr(db, "_migration_done", False)
    monkeypatch.setattr(artifact_store, "ARTIFACT_ROOT", tmp_path / "artifacts")
    artifact_store.reset_connection_state()
    db.init_db()
    stem_uploads.init_uploads_table()
    monkeypatch.setattr(
        stem_uploads,
        "find_project",
        lambda pid: {"id": pid, "client": "Test Client", "project": "Mix", "service": "Mixing"},
    )

    token = make_upload_token("proj01", ttl_seconds=3600)
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w") as archive:
        archive.writestr("README.txt", "test stems")
        archive.writestr("stem1.wav", _wav_bytes())
    result = stem_uploads.save_upload(
        token,
        file_bytes=archive_buffer.getvalue(),
        filename="stems.zip",
        uploader_name="Alex",
    )
    assert result["ok"] is True
    assert result["artifact"]["kind"] == "audio.source.upload"
    assert (stem_uploads.UPLOAD_ROOT / "proj01").exists()
    stored = next((stem_uploads.UPLOAD_ROOT / "proj01").iterdir())
    assert stored.stat().st_mode & 0o777 == 0o600
    artifact_store.reset_connection_state()
