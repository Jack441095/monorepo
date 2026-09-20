"""Staged, retry-safe Automix upload persistence tests."""

from __future__ import annotations

import io
import os
import wave
import zipfile
from pathlib import Path

import pytest

from app.routes.automix_routes import handle_automix_post

import db
import artifact_store
import event_store
import idempotency
import stem_uploads


@pytest.fixture()
def upload_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "uploads.db"
    upload_root = tmp_path / "stem_uploads"
    monkeypatch.setattr(db, "DB_PATH", db_path)
    monkeypatch.setattr(db, "AGENT_DATA", tmp_path / "empty-agent-data")
    monkeypatch.setattr(db, "_migration_done", False)
    monkeypatch.setattr(stem_uploads, "UPLOAD_ROOT", upload_root)
    monkeypatch.setattr(artifact_store, "ARTIFACT_ROOT", tmp_path / "artifacts")
    artifact_store.reset_connection_state()
    db.init_db()
    yield upload_root
    artifact_store.reset_connection_state()


def wav_bytes(*, seconds: float = 0.05, sample_rate: int = 8_000, marker: bytes = b"") -> bytes:
    output = io.BytesIO()
    frame_count = max(1, int(seconds * sample_rate))
    frames = (marker[:1] or b"\0") * frame_count * 2
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(frames)
    return output.getvalue()


def zip_bytes(text: str = "test stems") -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        stem = zipfile.ZipInfo("audio/vocal.wav", date_time=(2026, 1, 1, 0, 0, 0))
        stem.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(stem, wav_bytes(marker=text.encode()))
        entry = zipfile.ZipInfo("README.txt", date_time=(2026, 1, 1, 0, 0, 0))
        entry.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(entry, text)
    return output.getvalue()


def request(data: bytes | None = None) -> stem_uploads.StemUploadRequest:
    return stem_uploads.StemUploadRequest(
        project_id="project1",
        file_bytes=data or zip_bytes(),
        filename="stems.zip",
        project_label="Project project1",
        uploader_name="Automix",
        uploader_email="artist@example.com",
        notes="Automix Upload",
    )


def managed_files(root: Path) -> list[Path]:
    return [
        path
        for path in root.rglob("*")
        if path.is_file() and ".staging" not in path.parts
    ]


def test_source_readiness_requires_supported_managed_source(upload_env: Path) -> None:
    missing = stem_uploads.source_readiness("missing")
    assert missing["ready"] is False
    assert missing["code"] == "automix_source_not_ready"

    project = upload_env / "project1"
    (project / "reference").mkdir(parents=True)
    (project / "reference" / "reference.wav").write_bytes(b"not-a-stem")
    (project / ".hidden.wav").write_bytes(b"hidden")
    assert stem_uploads.source_readiness("project1")["ready"] is False

    (project / "stems.zip").write_bytes(zip_bytes())
    ready = stem_uploads.source_readiness("project1")
    assert ready["ready"] is True
    assert ready["file_count"] == 1
    assert ready["file_types"] == {".wav": 1}


def test_upload_rejects_archive_without_audio(upload_env: Path) -> None:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("README.txt", "no stems")

    with pytest.raises(stem_uploads.UploadValidationError, match="no supported audio"):
        stem_uploads.store_upload(request(output.getvalue()))


def test_upload_rejects_more_than_worker_stem_limit(upload_env: Path) -> None:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        audio = wav_bytes()
        for index in range(stem_uploads.MAX_AUTOMIX_STEMS + 1):
            archive.writestr(f"stem-{index:02d}.wav", audio)

    with pytest.raises(stem_uploads.UploadValidationError, match="32-stem limit"):
        stem_uploads.store_upload(request(output.getvalue()))


def test_upload_rejects_member_above_worker_size_limit(
    upload_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = wav_bytes()
    monkeypatch.setattr(stem_uploads, "MAX_AUTOMIX_SOURCE_BYTES", len(audio) - 1)

    with pytest.raises(stem_uploads.UploadValidationError, match="file limit|per-file limit"):
        stem_uploads.store_upload(request(zip_bytes()))


def test_upload_rejects_audio_above_worker_duration_limit(upload_env: Path) -> None:
    long_audio = wav_bytes(seconds=stem_uploads.MAX_AUTOMIX_DURATION_SECONDS + 1)
    direct = stem_uploads.StemUploadRequest(
        project_id="project1",
        file_bytes=long_audio,
        filename="long.wav",
        project_label="Long source",
    )

    with pytest.raises(stem_uploads.UploadValidationError, match="10-minute"):
        stem_uploads.store_upload(direct)


def test_upload_rejects_mislabeled_audio_member(upload_env: Path) -> None:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("vocal.wav", b"this is not wave audio")

    with pytest.raises(stem_uploads.UploadValidationError, match="does not match"):
        stem_uploads.store_upload(request(output.getvalue()))


def test_source_readiness_accepts_prior_safe_extraction(upload_env: Path) -> None:
    extracted = upload_env / "project2" / "extracted" / "nested"
    extracted.mkdir(parents=True)
    (extracted / "vocal.wav").write_bytes(b"decoded-earlier")

    readiness = stem_uploads.require_source_ready("project2")

    assert readiness["ready"] is True
    assert readiness["file_types"] == {".wav": 1}


def test_store_upload_finalizes_private_file_and_metadata(upload_env: Path) -> None:
    status, response = stem_uploads.store_upload(request())

    assert status == 200
    assert response["ok"] is True
    assert response["artifact"]["kind"] == "audio.source.upload"
    assert response["artifact"]["project_id"] == "project1"
    assert artifact_store.verify(response["artifact"]["artifact_id"])["ok"] is True
    assert {event["event_type"] for event in event_store.list_for_project("project1")} == {
        "artifact.registered",
        "source.uploaded",
    }
    files = managed_files(upload_env)
    assert len(files) == 1
    assert files[0].name.startswith(response["upload_id"] + "_")
    assert files[0].stat().st_mode & 0o777 == 0o600
    assert list((upload_env / "project1" / ".staging").glob("*.part")) == []
    with db.connect() as conn:
        row = conn.execute(
            "SELECT * FROM stem_uploads WHERE id = ?", (response["upload_id"],)
        ).fetchone()
    assert row["stored_name"] == files[0].name
    assert row["size_bytes"] == len(zip_bytes())


def test_keyed_retry_replays_without_duplicate_file_or_row(upload_env: Path) -> None:
    first = stem_uploads.store_upload(request(), idempotency_key="upload-request-1")
    replay = stem_uploads.store_upload(request(), idempotency_key="upload-request-1")

    assert replay == first
    assert len(managed_files(upload_env)) == 1
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM stem_uploads").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM artifact_blobs").fetchone()[0] == 1


def test_key_reuse_with_changed_file_is_rejected(upload_env: Path) -> None:
    stem_uploads.store_upload(request(), idempotency_key="upload-request-1")
    with pytest.raises(idempotency.IdempotencyConflict):
        stem_uploads.store_upload(
            request(zip_bytes("different stems")),
            idempotency_key="upload-request-1",
        )


def test_finalize_failure_rolls_back_metadata_and_removes_files(
    upload_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_replace = os.replace

    def replace_then_fail(source, destination) -> None:
        real_replace(source, destination)
        raise OSError("simulated finalization failure")

    monkeypatch.setattr(stem_uploads.os, "replace", replace_then_fail)
    with pytest.raises(OSError, match="finalization failure"):
        stem_uploads.store_upload(request())

    assert managed_files(upload_env) == []
    assert list(upload_env.rglob("*.part")) == []
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM stem_uploads").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM artifact_blobs").fetchone()[0] == 0
    assert list(artifact_store.ARTIFACT_ROOT.rglob("*")) == [] or not any(
        path.is_file() for path in artifact_store.ARTIFACT_ROOT.rglob("*")
    )


def test_orphan_cleanup_is_dry_run_first_and_preserves_unmanaged_files(
    upload_env: Path,
) -> None:
    stem_uploads.store_upload(request())
    project_dir = upload_env / "project1"
    staging = project_dir / ".staging" / "deadbeef.part"
    staging.parent.mkdir()
    staging.write_bytes(b"staged")
    orphan = project_dir / "deadbeef_orphan.zip"
    orphan.write_bytes(b"orphan")
    manual = project_dir / "manual.wav"
    manual.write_bytes(b"manual")
    old = 1_600_000_000
    os.utime(staging, (old, old))
    os.utime(orphan, (old, old))
    os.utime(manual, (old, old))

    report = stem_uploads.cleanup_orphan_upload_files(
        dry_run=True, min_age_seconds=0
    )
    assert {item["kind"] for item in report["candidates"]} == {
        "staging",
        "unreferenced",
    }
    assert staging.exists() and orphan.exists() and manual.exists()

    deleted = stem_uploads.cleanup_orphan_upload_files(
        dry_run=False, min_age_seconds=0
    )
    assert deleted["deleted"] == 2
    assert not staging.exists() and not orphan.exists()
    assert manual.exists()
    assert len(managed_files(upload_env)) == 2  # referenced upload plus manual file


def multipart_body(project_id: str, data: bytes) -> tuple[str, bytes]:
    boundary = "----AudioTooUploadBoundary"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="project_id"\r\n\r\n'
        f"{project_id}\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="stems.zip"\r\n'
        "Content-Type: application/zip\r\n\r\n"
    ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
    return f"multipart/form-data; boundary={boundary}", body


class Handler:
    def __init__(self, content_type: str, body: bytes, key: str) -> None:
        self.headers = {"Content-Type": content_type, "Idempotency-Key": key}
        self.body = body
        self.status = 0
        self.payload: dict = {}

    def read_body_bytes(self) -> bytes:
        return self.body

    def send_json(self, status: int, payload: dict) -> None:
        self.status = status
        self.payload = payload


def test_versioned_multipart_route_uses_retry_safe_service(upload_env: Path) -> None:
    content_type, body = multipart_body("project1", zip_bytes())
    first = Handler(content_type, body, "route-upload-1")
    replay = Handler(content_type, body, "route-upload-1")

    assert handle_automix_post(first, "/api/automix/upload", str(upload_env.parent))
    assert handle_automix_post(replay, "/api/automix/upload", str(upload_env.parent))

    assert first.status == replay.status == 200
    assert first.payload == replay.payload
    assert len(managed_files(upload_env)) == 1
