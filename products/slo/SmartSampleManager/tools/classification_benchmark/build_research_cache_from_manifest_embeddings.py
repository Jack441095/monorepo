#!/usr/bin/env python3
"""Create a disposable research SQLite cache from verified embeddings.

The output schema contains only the fields consumed by the research runner.
Manifest IDs, paths, source hashes and embedding dimensions must match exactly;
rows with extraction errors or missing embeddings are rejected.  The output is
written atomically outside the SmartSampleManager source tree and never replaces
the production cache.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import struct
import tempfile
from pathlib import Path
from typing import Any

import numpy as np


EMBEDDING_DIM = 512
METHOD_VERSION = "research_cache_from_manifest_embeddings_v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_manifest(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise ValueError("manifest must be a non-empty JSON list")
    return payload


def _load_embeddings(path: Path) -> dict[str, dict[str, Any]]:
    archive = np.load(path, allow_pickle=True)
    required = {"paths", "embeddings", "errors", "source_sha256", "manifest_id"}
    missing = sorted(required - set(archive.files))
    if missing:
        raise ValueError(f"embedding archive is missing fields: {missing}")
    rows: dict[str, dict[str, Any]] = {}
    for values in zip(archive["paths"], archive["embeddings"], archive["errors"],
                      archive["source_sha256"], archive["manifest_id"]):
        path_value, embedding, error, source_hash, sample_id = values
        ident = str(sample_id)
        if not ident or ident in rows:
            raise ValueError(f"embedding archive has missing or duplicate manifest_id: {ident}")
        rows[ident] = {
            "path": str(path_value),
            "embedding": np.asarray(embedding, dtype=np.float32),
            "error": str(error),
            "source_sha256": str(source_hash).lower(),
        }
    if not rows:
        raise ValueError("embedding archive contains no rows")
    return rows


def _schema(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE sample_cache (
            path TEXT PRIMARY KEY,
            mtime INTEGER NOT NULL,
            size INTEGER NOT NULL,
            category TEXT,
            subcategory TEXT,
            embedding BLOB,
            content_hash TEXT,
            embedding_status INTEGER NOT NULL
        )
    """)


def build_cache(manifest_path: Path, embeddings_path: Path, output_path: Path) -> dict[str, Any]:
    manifest = _load_manifest(manifest_path)
    embeddings = _load_embeddings(embeddings_path)
    manifest_by_id: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(manifest, start=1):
        ident = str(item.get("sample_id", index))
        if ident in manifest_by_id:
            raise ValueError(f"manifest has duplicate sample_id: {ident}")
        manifest_by_id[ident] = item

    if set(manifest_by_id) != set(embeddings):
        raise ValueError(
            "manifest/embedding ID sets differ: "
            f"manifest_only={sorted(set(manifest_by_id) - set(embeddings))[:5]}, "
            f"embedding_only={sorted(set(embeddings) - set(manifest_by_id))[:5]}"
        )

    rows: list[tuple[Any, ...]] = []
    for ident, item in manifest_by_id.items():
        source = embeddings[ident]
        path = Path(str(item.get("path", ""))).expanduser()
        expected_hash = str(item.get("sha256", "")).strip().lower()
        if not path.is_absolute() or not path.is_file():
            raise ValueError(f"source path does not exist for manifest id {ident}: {path}")
        if source["path"] != str(path):
            raise ValueError(f"embedding path mismatch for manifest id {ident}")
        if source["source_sha256"] != expected_hash:
            raise ValueError(f"embedding/source hash mismatch for manifest id {ident}")
        if source["error"]:
            raise ValueError(f"embedding extraction failed for manifest id {ident}: {source['error']}")
        embedding = source["embedding"].reshape(-1)
        if embedding.size != EMBEDDING_DIM or not np.isfinite(embedding).all():
            raise ValueError(f"invalid embedding shape/content for manifest id {ident}")
        if not np.isfinite(np.linalg.norm(embedding)) or np.linalg.norm(embedding) <= 0:
            raise ValueError(f"zero embedding for manifest id {ident}")
        category = "OOD" if item.get("ood") is True or item.get("expected_subcategory") == "OOD" else "Known"
        rows.append((
            str(path), int(path.stat().st_mtime * 1000), path.stat().st_size,
            category, str(item.get("expected_subcategory", "")),
            sqlite3.Binary(struct.pack(f"{EMBEDDING_DIM}f", *embedding.tolist())),
            expected_hash, 1,
        ))

    output_path = output_path.resolve()
    source_root = Path(__file__).resolve().parents[2]
    if os.path.commonpath([str(output_path), str(source_root)]) == str(source_root):
        raise ValueError("research cache output must be outside the SmartSampleManager source tree")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".research_cache_", suffix=".sqlite3", dir=output_path.parent)
    os.close(fd)
    try:
        with sqlite3.connect(temporary) as conn:
            _schema(conn)
            conn.executemany(
                "INSERT INTO sample_cache "
                "(path,mtime,size,category,subcategory,embedding,content_hash,embedding_status) "
                "VALUES (?,?,?,?,?,?,?,?)",
                rows,
            )
            conn.commit()
        os.replace(temporary, output_path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

    return {
        "record_type": "slo_research_cache_build",
        "schema_version": "1.0.0",
        "method_version": METHOD_VERSION,
        "manifest": str(manifest_path.resolve()),
        "manifest_sha256": sha256_file(manifest_path),
        "embeddings": str(embeddings_path.resolve()),
        "embeddings_sha256": sha256_file(embeddings_path),
        "output": str(output_path),
        "output_sha256": sha256_file(output_path),
        "rows": len(rows),
        "known_rows": sum(row[3] == "Known" for row in rows),
        "ood_rows": sum(row[3] == "OOD" for row in rows),
        "safety": {
            "source_audio_modified": False,
            "production_cache_modified": False,
            "production_policy_changed": False,
            "atomic_output": True,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--embeddings", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    args = parser.parse_args(argv)
    receipt = build_cache(args.manifest, args.embeddings, args.out)
    args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
    args.receipt_out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
