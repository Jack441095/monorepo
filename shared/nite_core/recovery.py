"""Versioned, checksummed backup and restore support for release recovery."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = "audio_too.recovery.v1"
MANIFEST_NAME = "recovery-manifest.json"

# Each root is restored as one unit. Large reproducible model artifacts and raw
# source PDFs are intentionally excluded; the promoted KENN index and its
# provenance-bearing notes are included.
RECOVERY_ROOTS: tuple[tuple[str, str], ...] = (
    ("main.py", "application"),
    ("audio-too", "application"),
    ("ableton", "application"),
    ("agent", "application"),
    ("README.md", "documentation"),
    ("LICENSE", "documentation"),
    ("docs/commands.md", "documentation"),
    ("pyproject.toml", "configuration"),
    ("requirements.txt", "configuration"),
    (".env.example", "configuration"),
    ("audio_too", "application"),
    ("scripts", "application"),
    ("server/app", "application"),
    ("server/agents", "application_and_data"),
    ("server/portfolio", "client_data"),
    ("data", "database_and_runtime"),
    ("thursday", "application_sessions_and_configuration"),
    ("studio/kenn/kenn/core", "application"),
    ("studio/kenn/kenn/retrieval", "application"),
    ("studio/kenn/kenn/llm", "application"),
    ("studio/kenn/kenn/adaptive", "application"),
    ("studio/kenn/kenn/training", "application"),
    ("studio/kenn/kenn/evals", "application"),
    ("studio/kenn/kenn/static", "application"),
    ("studio/kenn/kenn/Training_Data_Notes", "knowledge"),
    ("studio/kenn/kenn/Training_Data_Sources", "knowledge"),
    ("studio/kenn/kenn/Training_Data_Transcripts", "knowledge"),
    ("studio/kenn/kenn/chats", "sessions"),
    ("studio/kenn/kenn/data/index", "index"),
    ("studio/kenn/kenn/artifacts/models/minilm", "model"),
    ("studio/kenn/kenn/artifacts/models/kokoro", "model"),
    ("studio/kenn/kenn/main.py", "application"),
    ("studio/kenn/kenn/server.py", "application"),
    ("studio/kenn/kenn/requirements.txt", "configuration"),
    ("studio/audio_analysis/audio_analysis", "application"),
    ("studio/agents/MixReview/__init__.py", "application"),
    ("studio/agents/MixReview/ableton_live_api.py", "application"),
    ("studio/agents/MixReview/revision_agent.py", "application"),
    ("studio/audiogen/audiogen/ai", "application"),
    ("studio/audiogen/audiogen/audio", "application"),
    ("studio/audiogen/audiogen/composition", "application"),
    ("studio/audiogen/audiogen/core", "application"),
    ("studio/audiogen/audiogen/data", "application_and_data"),
    ("studio/audiogen/audiogen/docs", "documentation"),
    ("studio/audiogen/audiogen/midi", "application"),
    ("studio/audiogen/audiogen/presets", "configuration"),
    ("studio/audiogen/audiogen/runner", "application"),
    ("studio/audiogen/audiogen/sampler", "application"),
    ("studio/audiogen/audiogen/scripts", "application"),
    ("studio/audiogen/audiogen/tools", "application"),
    ("studio/audiogen/audiogen/training", "application"),
    ("studio/audiogen/audiogen/utils", "application"),
    ("studio/audiogen/audiogen/app_controller.py", "application"),
    ("studio/audiogen/audiogen/gui_scene_adapter.py", "application"),
    ("studio/audiogen/audiogen/main.py", "application"),
    ("studio/audiogen/audiogen/main_llm.py", "application"),
    ("studio/audiogen/audiogen/main_llm_chorus_only.py", "application"),
    ("studio/audiogen/audiogen/main_render_full_song.py", "application"),
    ("studio/audiogen/audiogen/pyproject.toml", "configuration"),
    ("studio/audiogen/audiogen/requirements-dev.lock", "configuration"),
)

_IGNORED_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache", "backups"}
_IGNORED_SUFFIXES = {".pyc", ".pyo", ".db-wal", ".db-shm"}


class RecoveryError(RuntimeError):
    """Raised when an archive is unsafe, corrupt, or incomplete."""


def _ignored(path: Path) -> bool:
    return any(part in _IGNORED_DIRS for part in path.parts) or any(
        path.name.endswith(suffix) for suffix in _IGNORED_SUFFIXES
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix == ".db":
        src = sqlite3.connect(f"file:{source}?mode=ro", uri=True, timeout=30.0)
        dst = sqlite3.connect(target, timeout=30.0)
        try:
            src.backup(dst)
        finally:
            src.close()
            dst.close()
        shutil.copystat(source, target)
        return
    shutil.copy2(source, target)


def _copy_root(source: Path, target: Path) -> None:
    if source.is_file():
        _copy_file(source, target)
        return
    for item in sorted(source.rglob("*")):
        relative = item.relative_to(source)
        if _ignored(relative):
            continue
        destination = target / relative
        if item.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        elif item.is_file():
            _copy_file(item, destination)


def _manifest(stage: Path, managed_roots: list[dict[str, str]]) -> dict:
    entries = []
    role_by_root = {item["path"]: item["role"] for item in managed_roots}
    for path in sorted(item for item in stage.rglob("*") if item.is_file()):
        relative = path.relative_to(stage).as_posix()
        role = next(
            role_by_root[root]
            for root in role_by_root
            if relative == root or relative.startswith(f"{root}/")
        )
        entries.append(
            {
                "path": relative,
                "role": role,
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    index_current = stage / "studio/kenn/kenn/data/index/CURRENT"
    return {
        "schema": SCHEMA,
        "created_at": datetime.now(UTC).isoformat(),
        "managed_roots": managed_roots,
        "index_version": (
            index_current.read_text(encoding="utf-8").strip()
            if index_current.exists()
            else ""
        ),
        "entries": entries,
        "file_count": len(entries),
        "total_bytes": sum(item["bytes"] for item in entries),
    }


def create_archive(repo_root: Path, archive_path: Path) -> dict:
    """Create a consistent recovery archive without modifying ``repo_root``."""
    repo_root = repo_root.resolve()
    archive_path = archive_path.resolve()
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="audio-too-backup-") as temp:
        stage = Path(temp) / "payload"
        stage.mkdir()
        managed_roots = []
        for relative, role in RECOVERY_ROOTS:
            source = repo_root / relative
            if not source.exists():
                continue
            _copy_root(source, stage / relative)
            managed_roots.append({"path": relative, "role": role})
        if not managed_roots:
            raise RecoveryError(f"No recoverable paths found under {repo_root}")
        manifest = _manifest(stage, managed_roots)
        (stage / MANIFEST_NAME).write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temporary_archive = archive_path.with_suffix(archive_path.suffix + ".tmp")
        temporary_archive.unlink(missing_ok=True)
        with tarfile.open(temporary_archive, "w:gz") as archive:
            for path in sorted(stage.rglob("*")):
                archive.add(path, arcname=path.relative_to(stage), recursive=False)
        os.replace(temporary_archive, archive_path)
    return manifest


def _safe_members(archive: tarfile.TarFile) -> list[tarfile.TarInfo]:
    members = archive.getmembers()
    for member in members:
        path = Path(member.name)
        if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk():
            raise RecoveryError(f"Unsafe archive member: {member.name}")
    return members


def _load_and_verify(stage: Path) -> dict:
    manifest_path = stage / MANIFEST_NAME
    if not manifest_path.exists():
        raise RecoveryError("Recovery manifest is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != SCHEMA:
        raise RecoveryError(f"Unsupported recovery schema: {manifest.get('schema')}")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or len(entries) != manifest.get("file_count"):
        raise RecoveryError("Recovery manifest entry count is invalid")
    for entry in entries:
        relative = str(entry.get("path", ""))
        path = stage / relative
        if not path.is_file():
            raise RecoveryError(f"Archive file is missing: {relative}")
        if path.stat().st_size != int(entry.get("bytes", -1)) or _sha256(path) != entry.get(
            "sha256"
        ):
            raise RecoveryError(f"Archive checksum failed: {relative}")
    return manifest


def verify_archive(archive_path: Path) -> dict:
    """Fully extract and checksum an archive in a disposable directory."""
    with tempfile.TemporaryDirectory(prefix="audio-too-verify-") as temp:
        stage = Path(temp)
        with tarfile.open(archive_path, "r:gz") as archive:
            archive.extractall(stage, members=_safe_members(archive), filter="data")
        return _load_and_verify(stage)


def restore_archive(archive_path: Path, target_root: Path) -> dict:
    """Verify then replace every managed root under an explicit target."""
    target_root = target_root.resolve()
    target_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="audio-too-restore-", dir=target_root.parent) as temp:
        stage = Path(temp) / "payload"
        stage.mkdir()
        with tarfile.open(archive_path, "r:gz") as archive:
            archive.extractall(stage, members=_safe_members(archive), filter="data")
        manifest = _load_and_verify(stage)
        rollback = Path(temp) / "rollback"
        for item in manifest["managed_roots"]:
            relative = Path(item["path"])
            source = stage / relative
            target = target_root / relative
            previous = rollback / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                previous.parent.mkdir(parents=True, exist_ok=True)
                os.replace(target, previous)
            try:
                os.replace(source, target)
            except Exception:
                if previous.exists():
                    os.replace(previous, target)
                raise
    return manifest
