"""Content-based validation and private storage for uploaded media."""

from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path, PurePosixPath

MAX_AUDIO_DURATION_SECONDS = 6 * 60 * 60
MAX_ARCHIVE_MEMBERS = 1_000
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 4 * 1024 * 1024 * 1024
NESTED_ARCHIVE_SUFFIXES = {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"}


def media_signature_matches(data: bytes, suffix: str) -> bool:
    suffix = suffix.lower()
    if suffix in {".wav", ".wave"}:
        return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE"
    if suffix in {".aif", ".aiff"}:
        return len(data) >= 12 and data[:4] == b"FORM" and data[8:12] in {b"AIFF", b"AIFC"}
    if suffix == ".flac":
        return data.startswith(b"fLaC")
    if suffix == ".mp3":
        return data.startswith(b"ID3") or (len(data) >= 2 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0)
    if suffix == ".m4a":
        return len(data) >= 12 and data[4:8] == b"ftyp"
    if suffix == ".zip":
        return data.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"))
    return False


def validate_audio_duration(data: bytes, *, max_seconds: int = MAX_AUDIO_DURATION_SECONDS) -> float | None:
    try:
        import soundfile

        info = soundfile.info(io.BytesIO(data))
    except Exception:
        return None
    duration = float(info.duration)
    if duration > max_seconds:
        raise ValueError(f"Audio duration exceeds the {max_seconds // 3600}-hour limit.")
    return duration


def validate_zip_payload(data: bytes) -> None:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError("ZIP archive is invalid or truncated.") from exc
    with archive:
        members = archive.infolist()
        if len(members) > MAX_ARCHIVE_MEMBERS:
            raise ValueError(f"ZIP contains more than {MAX_ARCHIVE_MEMBERS} entries.")
        total = sum(max(0, member.file_size) for member in members)
        if total > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
            raise ValueError("ZIP expands beyond the configured size limit.")
        for member in members:
            path = PurePosixPath(member.filename.replace("\\", "/"))
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("ZIP contains an unsafe member path.")
            if Path(path.name).suffix.lower() in NESTED_ARCHIVE_SUFFIXES:
                raise ValueError("Nested archives are not accepted.")


def validate_media_upload(data: bytes, filename: str, *, allow_zip: bool = False) -> str:
    suffix = Path(filename).suffix.lower()
    allowed = {".wav", ".wave", ".aif", ".aiff", ".flac", ".mp3", ".m4a"}
    if allow_zip:
        allowed.add(".zip")
    if suffix not in allowed:
        raise ValueError(f"Unsupported upload type: {suffix or 'missing extension'}.")
    if not media_signature_matches(data, suffix):
        raise ValueError("File content does not match its extension.")
    if suffix == ".zip":
        validate_zip_payload(data)
    else:
        validate_audio_duration(data)
    return suffix


def ensure_private_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)
    return path


def write_private_file(path: Path, data: bytes, *, replace: bool = False) -> Path:
    ensure_private_directory(path.parent)
    flags = os.O_WRONLY | os.O_CREAT | (os.O_TRUNC if replace else os.O_EXCL)
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    os.chmod(path, 0o600)
    return path
