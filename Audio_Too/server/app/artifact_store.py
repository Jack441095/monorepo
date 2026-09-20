"""Content-addressed artifact storage and lineage registry."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import db
import event_store
from nite_core import ArtifactRef

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_ROOT = REPO_ROOT / "data" / "artifacts"
HASH_CHUNK_BYTES = 1024 * 1024
MAX_METADATA_BYTES = 64 * 1024
_READY_DB: Path | None = None
_SCHEMA_LOCK = threading.Lock()


class ArtifactError(ValueError):
    """Base error for artifact validation or integrity failures."""


class MissingParentArtifact(ArtifactError):
    pass


class ArtifactIntegrityError(ArtifactError):
    pass


@dataclass(frozen=True)
class PreparedBlob:
    content_hash: str
    size_bytes: int
    storage_path: str
    created_file: bool


def ensure_schema() -> None:
    global _READY_DB
    current = Path(db.DB_PATH)
    if _READY_DB == current:
        return
    with _SCHEMA_LOCK:
        if _READY_DB == current:
            return
        db.init_db()
        _READY_DB = current


def reset_connection_state() -> None:
    global _READY_DB
    _READY_DB = None


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(HASH_CHUNK_BYTES):
            digest.update(chunk)
            size += len(chunk)
    return f"sha256:{digest.hexdigest()}", size


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _metadata(value: dict | None) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ArtifactError("Artifact metadata must be a JSON object.")
    try:
        encoded = json.dumps(value, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ArtifactError("Artifact metadata must contain only finite JSON values.") from exc
    if len(encoded.encode("utf-8")) > MAX_METADATA_BYTES:
        raise ArtifactError("Artifact metadata exceeds the 64 KiB limit.")
    return json.loads(encoded)


def _blob_relative_path(content_hash: str) -> Path:
    digest = content_hash.removeprefix("sha256:")
    return Path("sha256") / digest[:2] / digest[2:]


def _store_blob(source: Path, content_hash: str, size_bytes: int) -> tuple[Path, bool]:
    relative = _blob_relative_path(content_hash)
    destination = ARTIFACT_ROOT / relative
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        ARTIFACT_ROOT.chmod(0o700)
    except OSError:
        pass
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    for directory in (ARTIFACT_ROOT / "sha256", destination.parent):
        try:
            directory.chmod(0o700)
        except OSError:
            pass
    if destination.exists():
        actual_hash, actual_size = _hash_file(destination)
        if actual_hash != content_hash or actual_size != size_bytes:
            raise ArtifactIntegrityError(
                f"Existing blob failed integrity verification: {content_hash}"
            )
        return relative, False

    staged = destination.with_name(f".{destination.name}.{uuid4().hex}.part")
    created = False
    try:
        with source.open("rb") as source_handle, staged.open("xb") as target_handle:
            shutil.copyfileobj(source_handle, target_handle, length=HASH_CHUNK_BYTES)
            target_handle.flush()
            os.fsync(target_handle.fileno())
        staged.chmod(0o600)
        staged_hash, staged_size = _hash_file(staged)
        if staged_hash != content_hash or staged_size != size_bytes:
            raise ArtifactIntegrityError("Staged artifact changed while it was being ingested.")
        try:
            os.link(staged, destination)
            created = True
        except FileExistsError:
            pass
        finally:
            staged.unlink(missing_ok=True)
        if not destination.exists():
            raise ArtifactIntegrityError("Artifact blob could not be finalized.")
        final_hash, final_size = _hash_file(destination)
        if final_hash != content_hash or final_size != size_bytes:
            raise ArtifactIntegrityError("Finalized artifact failed integrity verification.")
        return relative, created
    finally:
        staged.unlink(missing_ok=True)


def _decode(row, parent_ids: tuple[str, ...] = ()) -> dict | None:
    if row is None:
        return None
    item = dict(row)
    try:
        metadata = json.loads(item.pop("metadata_json") or "{}")
    except json.JSONDecodeError:
        metadata = {}
    item["metadata"] = metadata if isinstance(metadata, dict) else {}
    item["parent_ids"] = parent_ids
    item["uri"] = f"artifact://{item['id']}"
    return item


def _parents(conn, artifact_id: str) -> tuple[str, ...]:
    rows = conn.execute(
        """SELECT parent_artifact_id FROM artifact_edges
           WHERE artifact_id = ? ORDER BY parent_artifact_id""",
        (artifact_id,),
    ).fetchall()
    return tuple(row["parent_artifact_id"] for row in rows)


def _get_with_conn(conn, artifact_id: str) -> dict | None:
    row = conn.execute(
        """SELECT a.*, b.size_bytes, b.storage_path
           FROM artifacts a JOIN artifact_blobs b USING(content_hash)
           WHERE a.id = ?""",
        (artifact_id,),
    ).fetchone()
    return _decode(row, _parents(conn, artifact_id))


def get(artifact_id: str) -> dict | None:
    ensure_schema()
    with db.connect() as conn:
        return _get_with_conn(conn, artifact_id)


def get_by_external_key(external_key: str) -> dict | None:
    if not str(external_key or "").strip():
        return None
    ensure_schema()
    with db.connect() as conn:
        row = conn.execute(
            """SELECT a.*, b.size_bytes, b.storage_path
               FROM artifacts a JOIN artifact_blobs b USING(content_hash)
               WHERE a.external_key = ?""",
            (external_key,),
        ).fetchone()
        return _decode(row, _parents(conn, row["id"])) if row else None


def register_file(
    path: str | Path,
    *,
    kind: str,
    media_type: str,
    producer: str,
    producer_version: str,
    project_id: str = "",
    external_key: str = "",
    source_uri: str = "",
    parent_ids: tuple[str, ...] = (),
    metadata: dict | None = None,
) -> dict:
    """Ingest a file and create one logical artifact record.

    ``external_key`` makes registration idempotent for a producer operation.
    Separate keys may reference the same content-addressed blob.
    """
    prepared = prepare_blob(path)
    try:
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            item = register_prepared(
                conn,
                prepared,
                kind=kind,
                media_type=media_type,
                producer=producer,
                producer_version=producer_version,
                project_id=project_id,
                external_key=external_key,
                source_uri=source_uri,
                parent_ids=parent_ids,
                metadata=metadata,
            )
            conn.commit()
    except Exception:
        discard_unreferenced_blob(prepared)
        raise
    return item


def prepare_blob(path: str | Path) -> PreparedBlob:
    """Copy and verify bytes before a caller begins its metadata transaction."""
    ensure_schema()
    supplied_source = Path(path).expanduser()
    if supplied_source.is_symlink():
        raise ArtifactError("Artifact source must not be a symbolic link.")
    source = supplied_source.resolve()
    if not source.is_file():
        raise ArtifactError("Artifact source must be an existing regular file.")
    content_hash, size_bytes = _hash_file(source)
    relative_path, created_file = _store_blob(source, content_hash, size_bytes)
    return PreparedBlob(
        content_hash=content_hash,
        size_bytes=size_bytes,
        storage_path=relative_path.as_posix(),
        created_file=created_file,
    )


def register_prepared(
    conn,
    prepared: PreparedBlob,
    *,
    kind: str,
    media_type: str,
    producer: str,
    producer_version: str,
    project_id: str = "",
    external_key: str = "",
    source_uri: str = "",
    parent_ids: tuple[str, ...] = (),
    metadata: dict | None = None,
) -> dict:
    """Register a prepared blob inside the caller's open SQLite transaction."""
    clean_metadata = _metadata(metadata)
    clean_external_key = str(external_key or "").strip()
    if len(clean_external_key) > 256:
        raise ArtifactError("Artifact external_key must be 256 characters or fewer.")
    candidate_id = f"art_{uuid4().hex[:24]}"
    unique_parents = tuple(dict.fromkeys(parent_ids))
    ArtifactRef(
        artifact_id=candidate_id,
        kind=kind,
        media_type=media_type,
        content_hash=prepared.content_hash,
        uri=f"artifact://{candidate_id}",
        producer=producer,
        producer_version=producer_version,
        parent_ids=unique_parents,
        metadata=clean_metadata,
    )
    if clean_external_key:
        row = conn.execute(
            "SELECT id, content_hash FROM artifacts WHERE external_key = ?",
            (clean_external_key,),
        ).fetchone()
        if row:
            if row["content_hash"] != prepared.content_hash:
                raise ArtifactError("Artifact external_key was reused for different content.")
            return _get_with_conn(conn, row["id"])  # type: ignore[return-value]
    if unique_parents:
        placeholders = ",".join("?" for _ in unique_parents)
        found = {
            row["id"]
            for row in conn.execute(
                f"SELECT id FROM artifacts WHERE id IN ({placeholders})", unique_parents
            ).fetchall()
        }
        missing = sorted(set(unique_parents) - found)
        if missing:
            raise MissingParentArtifact(f"Unknown parent artifact: {', '.join(missing)}")
    timestamp = _now()
    conn.execute(
        """INSERT OR IGNORE INTO artifact_blobs
           (content_hash, size_bytes, storage_path, created_at) VALUES (?, ?, ?, ?)""",
        (prepared.content_hash, prepared.size_bytes, prepared.storage_path, timestamp),
    )
    conn.execute(
        """INSERT INTO artifacts
           (id, content_hash, kind, media_type, producer, producer_version,
            project_id, external_key, source_uri, metadata_json, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)""",
        (
            candidate_id,
            prepared.content_hash,
            str(kind),
            str(media_type),
            str(producer),
            str(producer_version),
            str(project_id or ""),
            clean_external_key or None,
            str(source_uri or ""),
            json.dumps(clean_metadata, ensure_ascii=True, separators=(",", ":")),
            timestamp,
        ),
    )
    conn.executemany(
        """INSERT INTO artifact_edges
           (artifact_id, parent_artifact_id, relationship, created_at)
           VALUES (?, ?, 'derived_from', ?)""",
        ((candidate_id, parent_id, timestamp) for parent_id in unique_parents),
    )
    event_store.append_in_transaction(
        conn,
        event_type="artifact.registered",
        aggregate_type="artifact",
        aggregate_id=candidate_id,
        actor_id=str(producer),
        project_id=str(project_id or ""),
        correlation_id=clean_external_key or f"artifact:{candidate_id}",
        payload={
            "kind": str(kind),
            "media_type": str(media_type),
            "content_hash": prepared.content_hash,
            "size_bytes": prepared.size_bytes,
            "parent_ids": list(unique_parents),
        },
    )
    return _get_with_conn(conn, candidate_id)  # type: ignore[return-value]


def discard_unreferenced_blob(prepared: PreparedBlob) -> bool:
    """Remove a newly-created blob after its surrounding transaction rolls back."""
    if not prepared.created_file:
        return False
    ensure_schema()
    with db.connect() as conn:
        referenced = conn.execute(
            "SELECT 1 FROM artifact_blobs WHERE content_hash = ?", (prepared.content_hash,)
        ).fetchone()
    if referenced:
        return False
    (ARTIFACT_ROOT / prepared.storage_path).unlink(missing_ok=True)
    return True


def list_for_project(project_id: str, *, limit: int = 100) -> list[dict]:
    ensure_schema()
    safe_limit = max(1, min(500, int(limit or 100)))
    with db.connect() as conn:
        rows = conn.execute(
            """SELECT a.*, b.size_bytes, b.storage_path
               FROM artifacts a JOIN artifact_blobs b USING(content_hash)
               WHERE a.project_id = ? AND a.status = 'active'
               ORDER BY a.created_at DESC, a.rowid DESC LIMIT ?""",
            (str(project_id), safe_limit),
        ).fetchall()
        return [_decode(row, _parents(conn, row["id"])) for row in rows]


def resolve_path(artifact_id: str) -> Path:
    item = get(artifact_id)
    if not item or item["status"] != "active":
        raise ArtifactError("Artifact not found.")
    root = ARTIFACT_ROOT.resolve()
    path = (root / item["storage_path"]).resolve()
    if path != root and root not in path.parents:
        raise ArtifactIntegrityError("Artifact storage path escaped the managed root.")
    return path


def verify(artifact_id: str) -> dict:
    item = get(artifact_id)
    if not item:
        return {"ok": False, "artifact_id": artifact_id, "error": "Artifact not found."}
    path = resolve_path(artifact_id)
    if not path.is_file():
        return {"ok": False, "artifact_id": artifact_id, "error": "Artifact blob is missing."}
    actual_hash, actual_size = _hash_file(path)
    ok = actual_hash == item["content_hash"] and actual_size == item["size_bytes"]
    return {
        "ok": ok,
        "artifact_id": artifact_id,
        "content_hash": item["content_hash"],
        "size_bytes": item["size_bytes"],
        "error": "" if ok else "Artifact blob failed integrity verification.",
    }


def as_ref(item: dict) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=item["id"],
        kind=item["kind"],
        media_type=item["media_type"],
        content_hash=item["content_hash"],
        uri=item["uri"],
        producer=item["producer"],
        producer_version=item["producer_version"],
        parent_ids=tuple(item.get("parent_ids", ())),
        metadata={
            **item.get("metadata", {}),
            "project_id": item.get("project_id", ""),
            "source_uri": item.get("source_uri", ""),
            "size_bytes": item.get("size_bytes", 0),
        },
        created_at=_contract_timestamp(item["created_at"]),
    )


def _contract_timestamp(value: str) -> str:
    """Convert the existing database timestamp format to a timezone-bearing wire value."""
    text = str(value or "").strip()
    if "T" in text and (text.endswith("Z") or "+" in text):
        return text
    return text.replace(" ", "T") + "Z"


def public_record(item: dict) -> dict:
    """Return artifact metadata without its private managed filesystem path."""
    ref = as_ref(item)
    return {
        **ref.to_dict(),
        "project_id": item.get("project_id", ""),
        "source_uri": item.get("source_uri", ""),
        "size_bytes": item.get("size_bytes", 0),
        "status": item.get("status", "active"),
    }
