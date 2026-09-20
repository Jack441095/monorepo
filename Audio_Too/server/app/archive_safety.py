"""Bounded ZIP extraction for client-supplied Automix archives."""

from __future__ import annotations

import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath

from path_safety import safe_child

MAX_ZIP_MEMBERS = 1_000
MAX_ZIP_UNCOMPRESSED_BYTES = 4 * 1024 * 1024 * 1024
MAX_ZIP_COMPRESSION_RATIO = 1_000


def _member_path(name: str) -> PurePosixPath:
    normalized = name.replace("\\", "/")
    member_path = PurePosixPath(normalized)
    if member_path.is_absolute() or ".." in member_path.parts:
        raise ValueError(f"Unsafe ZIP member path: {name!r}")
    if member_path.parts and ":" in member_path.parts[0]:
        raise ValueError(f"Unsafe ZIP member path: {name!r}")
    return member_path


def _is_symlink(member: zipfile.ZipInfo) -> bool:
    mode = member.external_attr >> 16
    return stat.S_ISLNK(mode)


def extract_zip_safely(archive: zipfile.ZipFile, destination: str | Path) -> list[Path]:
    """Extract regular ZIP members within bounded count, size, and ratio limits."""
    members = archive.infolist()
    if len(members) > MAX_ZIP_MEMBERS:
        raise ValueError(f"ZIP contains more than {MAX_ZIP_MEMBERS} entries.")

    total_size = sum(max(0, member.file_size) for member in members)
    if total_size > MAX_ZIP_UNCOMPRESSED_BYTES:
        raise ValueError("ZIP expands beyond the configured uncompressed-size limit.")

    destination_path = Path(destination)
    destination_path.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    seen_targets: set[Path] = set()

    for member in members:
        if member.filename.startswith("__MACOSX") or member.filename.endswith(".DS_Store"):
            continue
        if _is_symlink(member):
            raise ValueError(f"ZIP symbolic links are not allowed: {member.filename!r}")

        member_path = _member_path(member.filename)
        if not member_path.parts:
            continue

        if member.file_size and member.compress_size == 0:
            raise ValueError(f"Invalid ZIP compression metadata: {member.filename!r}")
        if member.compress_size:
            ratio = member.file_size / member.compress_size
            if ratio > MAX_ZIP_COMPRESSION_RATIO:
                raise ValueError(f"ZIP member compression ratio is too high: {member.filename!r}")

        target = safe_child(destination_path, *member_path.parts)
        target_key = Path(str(target).casefold())
        if target_key in seen_targets:
            raise ValueError(f"ZIP contains a duplicate output path: {member.filename!r}")
        seen_targets.add(target_key)
        if member.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member, "r") as source, target.open("wb") as output:
            shutil.copyfileobj(source, output, length=1024 * 1024)
        extracted.append(target)

    return extracted
