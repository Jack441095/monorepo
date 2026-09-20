"""Client stem file uploads linked to projects."""

from __future__ import annotations

import hashlib
import io
import os
import re
import stat
import time
import zipfile
from collections import Counter
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from pathlib import Path
from uuid import uuid4

import artifact_store
import event_store
import idempotency
from db import connect, list_records, now
from path_safety import safe_child, validate_identifier
from upload_tokens import project_id_from_token, verify_upload_token
from audio_analysis.utils.media_safety import (
    ensure_private_directory,
    validate_audio_duration,
    validate_media_upload,
    write_private_file,
)

BUSINESS_ROOT = Path(__file__).resolve().parent.parent
UPLOAD_ROOT = BUSINESS_ROOT / "data" / "stem_uploads"
MAX_UPLOAD_BYTES = 500 * 1024 * 1024
MAX_MULTIPART_FIELDS = 32
MAX_TEXT_FIELD_CHARS = 10_000
ALLOWED_SUFFIXES = {".zip", ".wav", ".aiff", ".aif", ".flac", ".mp3", ".m4a"}
AUTOMIX_AUDIO_SUFFIXES = ALLOWED_SUFFIXES - {".zip"}
MAX_AUTOMIX_STEMS = 32
MAX_AUTOMIX_SOURCE_BYTES = 150 * 1024 * 1024
MAX_AUTOMIX_DURATION_SECONDS = 600

CREATE_SQL = """
    CREATE TABLE IF NOT EXISTS stem_uploads (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        project_label TEXT,
        original_name TEXT,
        stored_name TEXT,
        size_bytes INTEGER,
        uploader_name TEXT,
        uploader_email TEXT,
        notes TEXT,
        created_at TEXT
    )
"""


class UploadValidationError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class SourceNotReady(ValueError):
    """Raised when an AutoMix project has no renderable source upload."""

    code = "automix_source_not_ready"


def _visible_audio_member(member: zipfile.ZipInfo) -> bool:
    path = Path(member.filename.replace("\\", "/"))
    return (
        not member.is_dir()
        and not path.name.startswith(".")
        and not member.filename.startswith("__MACOSX")
        and path.suffix.lower() in AUTOMIX_AUDIO_SUFFIXES
    )


def _validate_audio_payload(data: bytes, filename: str) -> None:
    if len(data) > MAX_AUTOMIX_SOURCE_BYTES:
        raise UploadValidationError(
            f"Audio source exceeds the {MAX_AUTOMIX_SOURCE_BYTES // (1024 * 1024)} MB per-file limit.",
            status_code=413,
        )
    try:
        validate_media_upload(data, filename)
    except ValueError as exc:
        raise UploadValidationError(str(exc)) from exc
    try:
        duration = validate_audio_duration(data, max_seconds=MAX_AUTOMIX_DURATION_SECONDS)
    except ValueError as exc:
        raise UploadValidationError(
            f"Audio source exceeds the {MAX_AUTOMIX_DURATION_SECONDS // 60}-minute duration limit."
        ) from exc
    if duration is None:
        raise UploadValidationError(f"Audio source {Path(filename).name!r} could not be decoded.")


def validate_automix_source(data: bytes, filename: str) -> dict:
    """Validate one direct source or archive against the worker's hard limits."""
    suffix = Path(filename).suffix.lower()
    if len(data) > MAX_AUTOMIX_SOURCE_BYTES:
        raise UploadValidationError(
            f"AutoMix source exceeds the {MAX_AUTOMIX_SOURCE_BYTES // (1024 * 1024)} MB file limit.",
            status_code=413,
        )
    if suffix != ".zip":
        _validate_audio_payload(data, filename)
        return {"stem_count": 1, "total_audio_bytes": len(data)}

    try:
        validate_media_upload(data, filename, allow_zip=True)
        archive = zipfile.ZipFile(io.BytesIO(data))
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        raise UploadValidationError(str(exc)) from exc

    with archive:
        members = [member for member in archive.infolist() if _visible_audio_member(member)]
        if not members:
            raise UploadValidationError("ZIP archive contains no supported audio stems.")
        if len(members) > MAX_AUTOMIX_STEMS:
            raise UploadValidationError(
                f"ZIP archive exceeds the {MAX_AUTOMIX_STEMS}-stem limit (found {len(members)})."
            )
        basenames = [Path(member.filename).name.casefold() for member in members]
        if len(basenames) != len(set(basenames)):
            raise UploadValidationError("ZIP archive contains duplicate audio stem filenames.")
        for member in members:
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise UploadValidationError("ZIP symbolic links are not allowed.")
            if member.file_size > MAX_AUTOMIX_SOURCE_BYTES:
                raise UploadValidationError(
                    f"ZIP audio member exceeds the {MAX_AUTOMIX_SOURCE_BYTES // (1024 * 1024)} MB per-file limit.",
                    status_code=413,
                )
            try:
                member_data = archive.read(member)
            except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                raise UploadValidationError("ZIP audio member could not be read.") from exc
            _validate_audio_payload(member_data, member.filename)
        return {
            "stem_count": len(members),
            "total_audio_bytes": sum(member.file_size for member in members),
        }


def source_readiness(project_id: str, *, upload_root: Path | None = None) -> dict:
    """Inspect managed source files without decoding or mutating them."""
    try:
        safe_project_id = validate_identifier(project_id, label="project ID")
        project_dir = safe_child(upload_root or UPLOAD_ROOT, safe_project_id)
    except ValueError as exc:
        return {"ready": False, "code": "invalid_project_id", "message": str(exc), "file_count": 0}

    files: list[Path] = []
    has_extracted_tree = False
    if project_dir.is_dir():
        for path in project_dir.iterdir():
            if (
                path.is_file()
                and not path.is_symlink()
                and not path.name.startswith(".")
                and path.suffix.lower() in ALLOWED_SUFFIXES
            ):
                files.append(path)
        extracted = project_dir / "extracted"
        if extracted.is_dir():
            has_extracted_tree = True
            for path in extracted.rglob("*"):
                if (
                    path.is_file()
                    and not path.is_symlink()
                    and not path.name.startswith(".")
                    and path.suffix.lower() in ALLOWED_SUFFIXES - {".zip"}
                ):
                    files.append(path)
    files = sorted(set(files))
    if not files:
        return {
            "ready": False,
            "code": SourceNotReady.code,
            "message": (
                f"No uploaded stems are ready for project {safe_project_id}. "
                "Upload a ZIP or supported audio stem before starting AutoMix."
            ),
            "project_id": safe_project_id,
            "file_count": 0,
        }
    zip_files = [path for path in files if path.suffix.lower() == ".zip"]
    if zip_files:
        # This mirrors the worker: ZIPs are extracted and the extracted tree is
        # used instead of direct files in the project directory.
        stem_count = 0
        total_bytes = 0
        file_types: Counter = Counter()
        try:
            for path in zip_files:
                if path.stat().st_size > MAX_AUTOMIX_SOURCE_BYTES:
                    raise ValueError(
                        f"An AutoMix ZIP exceeds the {MAX_AUTOMIX_SOURCE_BYTES // (1024 * 1024)} MB limit."
                    )
                with zipfile.ZipFile(path) as archive:
                    members = [member for member in archive.infolist() if _visible_audio_member(member)]
                    stem_count += len(members)
                    total_bytes += sum(member.file_size for member in members)
                    file_types.update(Path(member.filename).suffix.lower() for member in members)
                    if any(member.file_size > MAX_AUTOMIX_SOURCE_BYTES for member in members):
                        raise ValueError("An archived audio stem exceeds the per-file size limit.")
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            return {
                "ready": False,
                "code": SourceNotReady.code,
                "message": str(exc),
                "project_id": safe_project_id,
                "file_count": 0,
            }
    else:
        extracted_files = [
            path for path in files if path.is_relative_to(project_dir / "extracted")
        ]
        selected = (
            extracted_files
            if has_extracted_tree
            else [path for path in files if path.suffix.lower() != ".zip"]
        )
        stem_count = len(selected)
        total_bytes = sum(path.stat().st_size for path in selected)
        file_types = Counter(path.suffix.lower() for path in selected)
        if any(path.stat().st_size > MAX_AUTOMIX_SOURCE_BYTES for path in selected):
            return {
                "ready": False,
                "code": SourceNotReady.code,
                "message": "An audio stem exceeds the per-file size limit.",
                "project_id": safe_project_id,
                "file_count": stem_count,
            }
    if not stem_count:
        return {
            "ready": False,
            "code": SourceNotReady.code,
            "message": "No supported audio stems were found in the uploaded source.",
            "project_id": safe_project_id,
            "file_count": 0,
        }
    if stem_count > MAX_AUTOMIX_STEMS:
        return {
            "ready": False,
            "code": SourceNotReady.code,
            "message": f"Project exceeds the {MAX_AUTOMIX_STEMS}-stem limit (found {stem_count}).",
            "project_id": safe_project_id,
            "file_count": stem_count,
        }
    return {
        "ready": True,
        "code": "ready",
        "message": f"{stem_count} audio stem(s) ready.",
        "project_id": safe_project_id,
        "file_count": stem_count,
        "file_types": dict(file_types),
        "total_bytes": total_bytes,
    }


def require_source_ready(project_id: str, *, upload_root: Path | None = None) -> dict:
    readiness = source_readiness(project_id, upload_root=upload_root)
    if not readiness["ready"]:
        raise SourceNotReady(readiness["message"])
    return readiness


@dataclass(frozen=True)
class StemUploadRequest:
    project_id: str
    file_bytes: bytes
    filename: str
    project_label: str
    uploader_name: str = ""
    uploader_email: str = ""
    notes: str = ""


def _validated_upload(request: StemUploadRequest) -> tuple[str, str]:
    try:
        project_id = validate_identifier(request.project_id, label="project ID")
    except ValueError as exc:
        raise UploadValidationError(str(exc)) from exc
    if not request.file_bytes:
        raise UploadValidationError("Uploaded file is empty.")
    if len(request.file_bytes) > MAX_UPLOAD_BYTES:
        raise UploadValidationError(
            f"Upload exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB file limit.",
            status_code=413,
        )
    safe_name = sanitize_filename(request.filename)
    if Path(safe_name).suffix.lower() not in ALLOWED_SUFFIXES:
        raise UploadValidationError("Unsupported upload type.")
    validate_automix_source(request.file_bytes, safe_name)
    return project_id, safe_name


def store_upload(
    request: StemUploadRequest,
    *,
    idempotency_key: str = "",
) -> tuple[int, dict]:
    """Stage, record, and atomically finalize one managed stem upload."""
    project_id, safe_name = _validated_upload(request)
    request_payload = {
        "project_id": project_id,
        "filename": safe_name,
        "content_sha256": hashlib.sha256(request.file_bytes).hexdigest(),
        "size_bytes": len(request.file_bytes),
        "uploader_name": request.uploader_name[:100],
        "uploader_email": request.uploader_email[:254],
        "notes": request.notes[:2000],
    }
    request_hash = idempotency.payload_hash(request_payload)
    operation = "automix.upload.create"
    init_uploads_table()

    if idempotency_key:
        with connect() as conn:
            replay = idempotency.replay(
                conn,
                operation=operation,
                key=idempotency_key,
                request_hash=request_hash,
            )
        if replay:
            return replay

    upload_id = str(uuid4())[:8]
    project_dir = safe_child(UPLOAD_ROOT, project_id)
    staging_dir = safe_child(project_dir, ".staging")
    ensure_private_directory(staging_dir)
    stored_name = f"{upload_id}_{safe_name}"
    staged_path = safe_child(staging_dir, f"{upload_id}.part")
    final_path = safe_child(project_dir, stored_name)
    write_private_file(staged_path, request.file_bytes)
    try:
        prepared_blob = artifact_store.prepare_blob(staged_path)
    except Exception:
        staged_path.unlink(missing_ok=True)
        try:
            staging_dir.rmdir()
        except OSError:
            pass
        raise

    timestamp = now()
    row = {
        "id": upload_id,
        "project_id": project_id,
        "project_label": request.project_label[:240],
        "original_name": safe_name,
        "stored_name": stored_name,
        "size_bytes": len(request.file_bytes),
        "uploader_name": request.uploader_name[:100],
        "uploader_email": request.uploader_email[:254],
        "notes": request.notes[:2000],
        "created_at": timestamp,
    }
    response = {
        "ok": True,
        "upload_id": upload_id,
        "project_id": project_id,
        "filename": safe_name,
        "size_bytes": len(request.file_bytes),
        "message": "File uploaded successfully.",
    }

    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        replay = idempotency.replay(
            conn,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if replay:
            conn.rollback()
            staged_path.unlink(missing_ok=True)
            artifact_store.discard_unreferenced_blob(prepared_blob)
            return replay
        conn.execute(
            """INSERT INTO stem_uploads
               (id, project_id, project_label, original_name, stored_name,
                size_bytes, uploader_name, uploader_email, notes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            tuple(row.values()),
        )
        artifact = artifact_store.register_prepared(
            conn,
            prepared_blob,
            kind="audio.source.upload",
            media_type={
                ".zip": "application/zip",
                ".wav": "audio/wav",
                ".aiff": "audio/aiff",
                ".aif": "audio/aiff",
                ".flac": "audio/flac",
                ".mp3": "audio/mpeg",
                ".m4a": "audio/mp4",
            }.get(Path(safe_name).suffix.lower(), "application/octet-stream"),
            producer="stem-upload",
            producer_version="1.0.0",
            project_id=project_id,
            external_key=f"stem-upload:{upload_id}",
            source_uri=f"upload://{upload_id}",
            metadata={
                "original_name": safe_name,
                "size_bytes": len(request.file_bytes),
            },
        )
        response["artifact"] = artifact_store.public_record(artifact)
        event_store.append_in_transaction(
            conn,
            event_type="source.uploaded",
            aggregate_type="upload",
            aggregate_id=upload_id,
            project_id=project_id,
            correlation_id=f"stem-upload:{upload_id}",
            actor_id="stem-upload",
            payload={
                "artifact_id": artifact["id"],
                "media_type": artifact["media_type"],
                "size_bytes": len(request.file_bytes),
            },
        )
        idempotency.record(
            conn,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            status_code=200,
            response=response,
            created_at=timestamp,
        )
        os.replace(staged_path, final_path)
        conn.commit()
    except Exception:
        conn.rollback()
        final_path.unlink(missing_ok=True)
        artifact_store.discard_unreferenced_blob(prepared_blob)
        raise
    finally:
        conn.close()
        staged_path.unlink(missing_ok=True)
        try:
            staging_dir.rmdir()
        except OSError:
            pass

    return 200, response


REFERENCE_MEDIA_TYPES = {
    ".wav": "audio/wav",
    ".aiff": "audio/aiff",
    ".aif": "audio/aiff",
    ".flac": "audio/flac",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
}
REFERENCE_ALLOWED_SUFFIXES = frozenset(REFERENCE_MEDIA_TYPES)


def store_reference(
    project_id: str,
    file_bytes: bytes,
    filename: str,
    *,
    idempotency_key: str = "",
) -> tuple[int, dict]:
    """Stage, register, and atomically finalize a project's reference track.

    A project has a single reference file on disk (a new upload replaces the old
    one), but every upload is registered as a distinct source artifact and emits a
    `reference.uploaded` event in one transaction — mirroring `store_upload`. The
    canonical file is promoted with os.replace so a crash never leaves the project
    with no reference file.
    """
    project_id = validate_identifier(project_id, label="project ID")
    safe_name = sanitize_filename(filename or "reference.wav")
    if not file_bytes:
        raise ValueError("Uploaded reference is empty.")
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise ValueError(
            f"Reference upload exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB file limit."
        )
    if Path(safe_name).suffix.lower() not in REFERENCE_ALLOWED_SUFFIXES:
        raise ValueError("Unsupported reference audio type.")
    suffix = validate_media_upload(bytes(file_bytes), safe_name)
    media_type = REFERENCE_MEDIA_TYPES.get(suffix, "application/octet-stream")

    content_sha = hashlib.sha256(bytes(file_bytes)).hexdigest()
    external_key = f"reference:{project_id}:{content_sha[:16]}"
    request_hash = idempotency.payload_hash({
        "project_id": project_id,
        "content_sha256": content_sha,
        "size_bytes": len(file_bytes),
    })
    operation = "automix.reference.upload"

    if idempotency_key:
        with connect() as conn:
            replay = idempotency.replay(
                conn, operation=operation, key=idempotency_key, request_hash=request_hash
            )
        if replay:
            return replay

    ref_dir = safe_child(UPLOAD_ROOT, project_id, "reference")
    ensure_private_directory(ref_dir)
    final_path = ref_dir / f"reference{suffix}"
    staged_path = ref_dir / f".reference{suffix}.part"
    write_private_file(staged_path, bytes(file_bytes))
    try:
        prepared_blob = artifact_store.prepare_blob(staged_path)
    except Exception:
        staged_path.unlink(missing_ok=True)
        raise

    timestamp = now()
    response = {
        "ok": True,
        "project_id": project_id,
        "filename": safe_name,
        "size_bytes": len(file_bytes),
        "message": "Reference track uploaded successfully.",
    }
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        replay = idempotency.replay(
            conn, operation=operation, key=idempotency_key, request_hash=request_hash
        )
        if replay:
            conn.rollback()
            staged_path.unlink(missing_ok=True)
            artifact_store.discard_unreferenced_blob(prepared_blob)
            return replay
        artifact = artifact_store.register_prepared(
            conn,
            prepared_blob,
            kind="audio.source.reference",
            media_type=media_type,
            producer="reference-upload",
            producer_version="1.0.0",
            project_id=project_id,
            external_key=external_key,
            source_uri=f"reference://{project_id}",
            metadata={"original_name": safe_name, "size_bytes": len(file_bytes)},
        )
        response["artifact"] = artifact_store.public_record(artifact)
        event_store.append_in_transaction(
            conn,
            event_type="reference.uploaded",
            aggregate_type="project_reference",
            aggregate_id=project_id,
            project_id=project_id,
            correlation_id=external_key,
            actor_id="reference-upload",
            payload={
                "artifact_id": artifact["id"],
                "media_type": media_type,
                "size_bytes": len(file_bytes),
            },
        )
        idempotency.record(
            conn,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            status_code=200,
            response=response,
            created_at=timestamp,
        )
        os.replace(staged_path, final_path)
        for old_reference in ref_dir.glob("reference.*"):
            if old_reference.resolve() != final_path.resolve():
                old_reference.unlink(missing_ok=True)
        conn.commit()
    except Exception:
        conn.rollback()
        artifact_store.discard_unreferenced_blob(prepared_blob)
        raise
    finally:
        conn.close()
        staged_path.unlink(missing_ok=True)

    return 200, response


def cleanup_orphan_upload_files(
    *,
    dry_run: bool = True,
    min_age_seconds: int = 3600,
) -> dict:
    """Report or remove stale service-owned staging/final files without touching manual stems."""
    init_uploads_table()
    with connect() as conn:
        referenced = {
            (str(row["project_id"]), str(row["stored_name"]))
            for row in conn.execute("SELECT project_id, stored_name FROM stem_uploads")
        }
    cutoff = time.time() - max(0, min_age_seconds)
    candidates: list[dict] = []
    if UPLOAD_ROOT.exists():
        for project_dir in UPLOAD_ROOT.iterdir():
            if not project_dir.is_dir():
                continue
            staging_dir = project_dir / ".staging"
            if staging_dir.is_dir():
                for path in staging_dir.glob("*.part"):
                    if path.is_file() and path.stat().st_mtime <= cutoff:
                        candidates.append({"path": path, "kind": "staging"})
            for path in project_dir.iterdir():
                if not path.is_file() or not re.match(r"^[0-9a-f]{8}_", path.name):
                    continue
                if (project_dir.name, path.name) not in referenced and path.stat().st_mtime <= cutoff:
                    candidates.append({"path": path, "kind": "unreferenced"})

    items = [
        {
            "path": str(item["path"].relative_to(UPLOAD_ROOT)),
            "kind": item["kind"],
            "size_bytes": item["path"].stat().st_size,
        }
        for item in candidates
    ]
    if not dry_run:
        for item in candidates:
            item["path"].unlink(missing_ok=True)
    return {
        "ok": True,
        "dry_run": dry_run,
        "candidates": items,
        "deleted": 0 if dry_run else len(items),
    }


def init_uploads_table() -> None:
    ensure_private_directory(UPLOAD_ROOT)
    with connect() as conn:
        conn.execute(CREATE_SQL)
        conn.commit()


def sanitize_filename(name: str) -> str:
    base = Path(name).name
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", base).strip("-")
    return cleaned[:180] or "upload.bin"


def find_project(project_id: str) -> dict | None:
    try:
        project_id = validate_identifier(project_id, label="project ID")
    except ValueError:
        return None
    for record in list_records("projects"):
        if str(record.get("id", "")) == project_id:
            return record
    return None


def project_label(project: dict) -> str:
    client = str(project.get("client", "")).strip()
    project_name = str(project.get("project", "")).strip()
    if client and project_name:
        return f"{client} — {project_name}"
    return project_name or client or f"Project {project.get('id', '')}"


def upload_info(token: str) -> dict:
    project_id = project_id_from_token(token)
    try:
        project_id = validate_identifier(project_id, label="project ID")
    except ValueError:
        return {"ok": False, "error": "Invalid or expired upload link."}
    project = find_project(project_id)
    if not project:
        return {"ok": False, "error": "Project not found."}
    return {
        "ok": True,
        "project_id": project_id,
        "project": project_label(project),
        "service": str(project.get("service", "")),
        "allowed_types": sorted(ALLOWED_SUFFIXES),
        "max_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
        "hints": [
            "WAV or AIFF stems, or one ZIP containing labeled files",
            "Include BPM, key, and sample rate in a README.txt inside the ZIP",
            "Export all stems from the same start point so they line up",
        ],
    }


def parse_multipart_form(content_type: str, body: bytes) -> dict[str, str | bytes]:
    if "multipart/form-data" not in content_type.lower():
        raise ValueError("Expected multipart form upload.")
    message = BytesParser(policy=policy.default).parsebytes(
        b"Content-Type: " + content_type.encode("utf-8", errors="replace") + b"\r\n\r\n" + body
    )
    fields: dict[str, str | bytes] = {}
    part_count = 0
    for part in message.iter_parts():
        if part.is_multipart():
            continue
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        part_count += 1
        if part_count > MAX_MULTIPART_FIELDS:
            raise ValueError("Multipart form contains too many fields.")
        filename = part.get_filename()
        payload = part.get_payload(decode=True) or b""
        if filename:
            fields[name] = payload
            fields[f"{name}__filename"] = filename
        else:
            value = (part.get_content() or "").strip()
            if len(value) > MAX_TEXT_FIELD_CHARS:
                raise ValueError("Multipart text field exceeds the configured limit.")
            fields[name] = value
    return fields


def save_upload(
    token: str,
    *,
    file_bytes: bytes,
    filename: str,
    uploader_name: str = "",
    uploader_email: str = "",
    notes: str = "",
) -> dict:
    project_id = project_id_from_token(token)
    try:
        project_id = validate_identifier(project_id, label="project ID")
    except ValueError:
        return {"ok": False, "error": "Invalid or expired upload link."}
    if not verify_upload_token(project_id, token):
        return {"ok": False, "error": "Invalid or expired upload link."}
    project = find_project(project_id)
    if not project:
        return {"ok": False, "error": "Project not found."}

    try:
        _status, result = store_upload(
            StemUploadRequest(
                project_id=project_id,
                file_bytes=file_bytes,
                filename=filename,
                project_label=project_label(project),
                uploader_name=uploader_name,
                uploader_email=uploader_email,
                notes=notes,
            )
        )
    except UploadValidationError as exc:
        return {"ok": False, "error": str(exc)}
    result["message"] = "Upload received. Your engineer will confirm by email."
    return result


def handle_multipart_upload(content_type: str, body: bytes) -> dict:
    fields = parse_multipart_form(content_type, body)
    token = str(fields.get("token", "")).strip()
    if not token:
        return {"ok": False, "error": "Missing upload token."}
    file_bytes = fields.get("file")
    if not isinstance(file_bytes, (bytes, bytearray)):
        return {"ok": False, "error": "Missing file field."}
    filename = str(fields.get("file__filename", "stems.zip"))
    return save_upload(
        token,
        file_bytes=bytes(file_bytes),
        filename=filename,
        uploader_name=str(fields.get("name", "")),
        uploader_email=str(fields.get("email", "")),
        notes=str(fields.get("notes", "")),
    )


def list_uploads(*, project_id: str = "", limit: int = 100) -> list[dict]:
    init_uploads_table()
    with connect() as conn:
        if project_id:
            rows = conn.execute(
                """
                SELECT * FROM stem_uploads WHERE project_id = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (project_id, max(1, min(500, limit))),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM stem_uploads ORDER BY created_at DESC LIMIT ?",
                (max(1, min(500, limit)),),
            ).fetchall()
    return [dict(row) for row in rows]
