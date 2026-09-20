"""Atomic, locked, versioned storage for KENN retrieval index bundles."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

import numpy as np

logger = logging.getLogger(__name__)

INDEX_DIR = Path(__file__).resolve().parent.parent / "data" / "index"
VERSIONS_DIRNAME = "versions"
CURRENT_FILENAME = "CURRENT"
PREVIOUS_FILENAME = "PREVIOUS"
LOCK_FILENAME = ".promotion.lock"
MANIFEST_FILENAME = "manifest.json"
REQUIRED_ARTIFACTS = ("chunks.jsonl", "terms.json")
OPTIONAL_ARTIFACTS = ("embeddings.npy",)
_VERSION_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_PROCESS_LOCK = threading.Lock()
# Found 2026-08-11 (staff-review correctness pass): every promote_index()
# call creates a new versions/ directory and nothing ever removed old ones --
# 39 accumulated over about a month of normal work, until the KENN product
# package's file-count budget (which includes this directory wholesale)
# started failing. Keep a bounded retention window instead of pruning to
# exactly 1: PREVIOUS enables rollback_index(), and a few more recent
# versions give headroom to diagnose a bad promotion without needing backups.
DEFAULT_VERSION_RETENTION = 5


class IndexValidationError(ValueError):
    """An index bundle is incomplete, inconsistent, or corrupt."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_bytes(path: Path, data: bytes) -> None:
    with path.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


@contextmanager
def promotion_lock(index_dir: Path = INDEX_DIR) -> Iterator[None]:
    """Serialize promotions across processes using an advisory file lock."""
    import fcntl

    index_dir.mkdir(parents=True, exist_ok=True)
    lock_path = index_dir / LOCK_FILENAME
    with _PROCESS_LOCK:
        with lock_path.open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def validate_version(version_dir: Path) -> dict:
    """Validate hashes, JSON shape, row counts, and embedding dimensions."""
    manifest_path = version_dir / MANIFEST_FILENAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IndexValidationError("Index manifest is missing or invalid.") from exc
    if manifest.get("schema_version") not in {1, 2}:
        raise IndexValidationError("Unsupported index manifest schema.")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise IndexValidationError("Index manifest has no artifact map.")
    for name in REQUIRED_ARTIFACTS:
        if name not in artifacts:
            raise IndexValidationError(f"Required index artifact is missing: {name}")
    for name, metadata in artifacts.items():
        if name not in {*REQUIRED_ARTIFACTS, *OPTIONAL_ARTIFACTS}:
            raise IndexValidationError(f"Unsupported index artifact: {name}")
        path = version_dir / name
        if not path.is_file() or not isinstance(metadata, dict):
            raise IndexValidationError(f"Index artifact is missing: {name}")
        if path.stat().st_size != int(metadata.get("size_bytes", -1)):
            raise IndexValidationError(f"Index artifact size mismatch: {name}")
        if _sha256(path) != metadata.get("sha256"):
            raise IndexValidationError(f"Index artifact hash mismatch: {name}")

    chunks = []
    try:
        for line in (version_dir / "chunks.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise TypeError
                chunks.append(record)
        terms = json.loads((version_dir / "terms.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        raise IndexValidationError("Index content is not valid JSON.") from exc
    chunk_count = len(chunks)
    if not chunks or not isinstance(terms, dict):
        raise IndexValidationError("Index must contain chunks and term metadata.")
    if int(terms.get("total_docs", -1)) != chunk_count:
        raise IndexValidationError("Term metadata does not match the chunk count.")
    if len(terms.get("term_counts", [])) != chunk_count:
        raise IndexValidationError("Term counts do not match the chunk count.")
    if len(terms.get("lengths", [])) != chunk_count:
        raise IndexValidationError("Document lengths do not match the chunk count.")
    embeddings_path = version_dir / "embeddings.npy"
    if embeddings_path.exists():
        try:
            embeddings = np.load(str(embeddings_path), mmap_mode="r", allow_pickle=False)
        except Exception as exc:
            raise IndexValidationError("Embedding artifact is invalid.") from exc
        if embeddings.ndim != 2 or embeddings.shape[0] != chunk_count:
            raise IndexValidationError("Embeddings do not match the chunk count.")
    if int(manifest.get("chunk_count", -1)) != chunk_count:
        raise IndexValidationError("Manifest chunk count is incorrect.")
    return manifest


# Found 2026-09-15 profiling a warm chat turn: active_version_dir() ran the
# full validate_version() on every call, and every answer calls it several
# times over (semantic-cache versioning, chunk loading, embedding loading).
# That is a SHA-256 over ~10 MB of artifacts plus a re-parse of 2808 JSONL
# chunk records and a 2.5 MB terms.json -- measured at 71-90 ms per call,
# which was ~99% of the wall time of a cache-hit answer. Validation is an
# integrity check on a bundle that only changes at promotion time, not a
# per-request concern, so memoise it against a cheap fingerprint: the
# resolved version id plus each artifact's (size, mtime_ns). Promotion
# writes a fresh version directory and flips the pointer, so the fingerprint
# always moves when the active bundle does. The residual gap is an in-place
# rewrite that preserves both size and mtime_ns within one process lifetime
# -- the standard trade-off for any stat-based cache, and promote_index()
# never writes that way. Full validation still runs on the first resolve in
# each process, and unconditionally in promotion/rollback paths that call
# validate_version() directly.
_validation_cache: dict[Path, tuple[tuple, dict]] = {}
_validation_cache_lock = threading.Lock()


def _version_fingerprint(version_dir: Path) -> tuple:
    stats = []
    for name in (MANIFEST_FILENAME, *REQUIRED_ARTIFACTS, *OPTIONAL_ARTIFACTS):
        try:
            info = (version_dir / name).stat()
        except OSError:
            stats.append((name, None, None))
        else:
            stats.append((name, info.st_size, info.st_mtime_ns))
    return tuple(stats)


def clear_validation_cache() -> None:
    """Drop memoised validation results (used by promotion and by tests)."""
    with _validation_cache_lock:
        _validation_cache.clear()


def validate_version_cached(version_dir: Path) -> dict:
    """validate_version(), skipped when the bundle is byte-identical to last seen.

    Raises IndexValidationError exactly as validate_version() does; failures
    are not cached, so a repaired bundle is picked up on the next call.
    """
    fingerprint = _version_fingerprint(version_dir)
    with _validation_cache_lock:
        cached = _validation_cache.get(version_dir)
        if cached is not None and cached[0] == fingerprint:
            return cached[1]
    manifest = validate_version(version_dir)
    with _validation_cache_lock:
        _validation_cache[version_dir] = (fingerprint, manifest)
    return manifest


def active_version_dir(index_dir: Path = INDEX_DIR) -> Path | None:
    """Resolve CURRENT, then its explicitly recorded last-known-good predecessor."""
    for pointer_name in (CURRENT_FILENAME, PREVIOUS_FILENAME):
        try:
            version_id = (index_dir / pointer_name).read_text(encoding="ascii").strip()
        except OSError:
            continue
        if not _VERSION_RE.fullmatch(version_id):
            continue
        candidate = index_dir / VERSIONS_DIRNAME / version_id
        try:
            validate_version_cached(candidate)
            return candidate
        except IndexValidationError:
            continue
    return None


def active_version_id(index_dir: Path = INDEX_DIR) -> str:
    version = active_version_dir(index_dir)
    return version.name if version else "legacy"


def active_artifact_path(name: str, index_dir: Path = INDEX_DIR) -> Path:
    if name not in {*REQUIRED_ARTIFACTS, *OPTIONAL_ARTIFACTS}:
        raise ValueError(f"Unsupported index artifact: {name}")
    version = active_version_dir(index_dir)
    if version is not None:
        return version / name
    return index_dir / name


def _pointer_version(index_dir: Path, pointer_name: str) -> Path | None:
    try:
        version_id = (index_dir / pointer_name).read_text(encoding="ascii").strip()
    except OSError:
        return None
    if not _VERSION_RE.fullmatch(version_id):
        return None
    candidate = index_dir / VERSIONS_DIRNAME / version_id
    try:
        validate_version(candidate)
    except IndexValidationError:
        return None
    return candidate


def rollback_index(index_dir: Path = INDEX_DIR) -> str:
    """Atomically select PREVIOUS, preserving the former valid CURRENT for redo."""
    with promotion_lock(index_dir):
        current = _pointer_version(index_dir, CURRENT_FILENAME)
        previous = _pointer_version(index_dir, PREVIOUS_FILENAME)
        if previous is None:
            raise IndexValidationError("No valid previous index version is available.")
        if current is not None and current.name == previous.name:
            raise IndexValidationError("Current and previous index versions are identical.")

        if current is not None:
            previous_tmp = index_dir / f".{PREVIOUS_FILENAME}.{os.getpid()}.tmp"
            try:
                _write_bytes(previous_tmp, f"{current.name}\n".encode("ascii"))
                os.replace(previous_tmp, index_dir / PREVIOUS_FILENAME)
                _fsync_directory(index_dir)
            finally:
                previous_tmp.unlink(missing_ok=True)

        current_tmp = index_dir / f".{CURRENT_FILENAME}.{os.getpid()}.tmp"
        try:
            _write_bytes(current_tmp, f"{previous.name}\n".encode("ascii"))
            os.replace(current_tmp, index_dir / CURRENT_FILENAME)
            _fsync_directory(index_dir)
        finally:
            current_tmp.unlink(missing_ok=True)
    clear_validation_cache()
    return previous.name


def prune_old_versions(
    index_dir: Path = INDEX_DIR, *, keep: int = DEFAULT_VERSION_RETENTION
) -> list[str]:
    """Delete version directories beyond the retention window.

    CURRENT and PREVIOUS are always preserved regardless of age (rollback_index()
    depends on PREVIOUS existing). Must be called while already holding
    promotion_lock -- promote_index() does this itself after each promotion,
    which is the only place this needs to run in normal operation.
    """
    versions_dir = index_dir / VERSIONS_DIRNAME
    if not versions_dir.is_dir():
        return []

    protected: set[str] = set()
    for pointer_name in (CURRENT_FILENAME, PREVIOUS_FILENAME):
        try:
            version_id = (index_dir / pointer_name).read_text(encoding="ascii").strip()
        except OSError:
            continue
        if _VERSION_RE.fullmatch(version_id):
            protected.add(version_id)

    candidates: list[tuple[float, Path]] = []
    for entry in versions_dir.iterdir():
        if not entry.is_dir() or entry.name.startswith(".") or entry.name in protected:
            continue
        try:
            mtime = entry.stat().st_mtime
        except OSError:
            continue
        candidates.append((mtime, entry))

    candidates.sort(key=lambda pair: pair[0], reverse=True)
    keep_unprotected = max(0, keep - len(protected))

    removed = []
    for _mtime, entry in candidates[keep_unprotected:]:
        shutil.rmtree(entry, ignore_errors=True)
        removed.append(entry.name)
    return removed


def promote_index(
    chunks: list[dict],
    terms: dict,
    embeddings: np.ndarray | None = None,
    *,
    index_dir: Path = INDEX_DIR,
    version_id: str = "",
    manifest_metadata: dict[str, Any] | None = None,
    fault_hook: Callable[[str], None] | None = None,
    version_retention: int = DEFAULT_VERSION_RETENTION,
) -> str:
    """Stage, validate, and atomically promote a complete index bundle.

    version_retention controls how many old versions/ directories survive
    this promotion (see prune_old_versions) -- pass a larger value, or 0 to
    disable pruning entirely, for callers that need every promoted version
    to remain on disk (e.g. tests inspecting concurrent-promotion history).
    """
    if not chunks:
        raise IndexValidationError("Cannot promote an empty index.")
    if embeddings is not None and (
        embeddings.ndim != 2 or embeddings.shape[0] != len(chunks)
    ):
        raise IndexValidationError("Embeddings do not match the chunk count.")
    chunks_bytes = b"".join(
        json.dumps(chunk, ensure_ascii=True, separators=(",", ":")).encode("utf-8") + b"\n"
        for chunk in chunks
    )
    terms_bytes = json.dumps(
        terms, ensure_ascii=True, separators=(",", ":")
    ).encode("utf-8")
    digest_input = chunks_bytes + terms_bytes
    if embeddings is not None:
        digest_input += str(embeddings.shape).encode("ascii") + embeddings.tobytes()
    if manifest_metadata:
        digest_input += json.dumps(
            manifest_metadata, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    content_digest = hashlib.sha256(digest_input).hexdigest()[:12]
    # Content addressing makes identical clean rebuilds idempotent: they reuse
    # the already-validated bundle instead of creating timestamp-only drift.
    version_id = version_id or f"v-{content_digest}"
    if not _VERSION_RE.fullmatch(version_id):
        raise IndexValidationError("Invalid index version identifier.")

    versions_dir = index_dir / VERSIONS_DIRNAME
    staging = versions_dir / f".staging-{version_id}-{os.getpid()}"
    final = versions_dir / version_id
    with promotion_lock(index_dir):
        prior_version = active_version_dir(index_dir)
        versions_dir.mkdir(parents=True, exist_ok=True)
        if final.exists():
            manifest = validate_version(final)
            if manifest.get("content_sha256") != content_digest:
                raise IndexValidationError("Index version ID already has different content.")
        else:
            shutil.rmtree(staging, ignore_errors=True)
            staging.mkdir()
            try:
                _write_bytes(staging / "chunks.jsonl", chunks_bytes)
                _write_bytes(staging / "terms.json", terms_bytes)
                if embeddings is not None:
                    with (staging / "embeddings.npy").open("wb") as handle:
                        np.save(handle, embeddings, allow_pickle=False)
                        handle.flush()
                        os.fsync(handle.fileno())
                artifacts = {}
                for name in (*REQUIRED_ARTIFACTS, *OPTIONAL_ARTIFACTS):
                    path = staging / name
                    if path.exists():
                        artifacts[name] = {
                            "sha256": _sha256(path),
                            "size_bytes": path.stat().st_size,
                        }
                manifest = {
                    "schema_version": 2 if manifest_metadata else 1,
                    "version_id": version_id,
                    "content_sha256": content_digest,
                    "chunk_count": len(chunks),
                    "embedding_dimensions": (
                        int(embeddings.shape[1]) if embeddings is not None else 0
                    ),
                    "created_at_epoch": time.time(),
                    "artifacts": artifacts,
                }
                if manifest_metadata:
                    manifest["build"] = manifest_metadata
                _write_bytes(
                    staging / MANIFEST_FILENAME,
                    json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode(
                        "utf-8"
                    ),
                )
                _fsync_directory(staging)
                validate_version(staging)
                if fault_hook:
                    fault_hook("after_stage")
                staging.rename(final)
                _fsync_directory(versions_dir)
                if fault_hook:
                    fault_hook("after_version_rename")
            except Exception:
                shutil.rmtree(staging, ignore_errors=True)
                raise

        if prior_version is not None and prior_version.name != version_id:
            previous_tmp = index_dir / f".{PREVIOUS_FILENAME}.{os.getpid()}.tmp"
            try:
                _write_bytes(previous_tmp, f"{prior_version.name}\n".encode("ascii"))
                os.replace(previous_tmp, index_dir / PREVIOUS_FILENAME)
                _fsync_directory(index_dir)
            finally:
                previous_tmp.unlink(missing_ok=True)

        pointer_tmp = index_dir / f".{CURRENT_FILENAME}.{os.getpid()}.tmp"
        try:
            _write_bytes(pointer_tmp, f"{version_id}\n".encode("ascii"))
            if fault_hook:
                fault_hook("before_pointer_replace")
            os.replace(pointer_tmp, index_dir / CURRENT_FILENAME)
            _fsync_directory(index_dir)
        finally:
            pointer_tmp.unlink(missing_ok=True)

        if version_retention > 0:
            try:
                prune_old_versions(index_dir, keep=version_retention)
            except Exception:
                # Best-effort cleanup -- a pruning failure must never fail an
                # otherwise-successful promotion.
                logger.warning("prune_old_versions failed after promoting %s", version_id, exc_info=True)
    clear_validation_cache()
    return version_id
