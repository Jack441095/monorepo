#!/usr/bin/env python3
"""Build a path-independent embedding index keyed by complete audio bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np


VERSION = "embedding_content_index_v1"


def build_index(embedding_paths: list[str], identity: dict[str, Any],
                model_version: str, embedding_dimensions: int) -> dict[str, Any]:
    identity_rows = {
        os.path.abspath(str(row["path"])): row
        for row in identity.get("rows", [])
        if isinstance(row, dict) and isinstance(row.get("path"), str)
    }
    paths = [os.path.abspath(str(path)) for path in embedding_paths]
    if len(paths) != len(set(paths)):
        raise ValueError("embedding cache contains duplicate paths")
    missing = [path for path in paths if path not in identity_rows]
    extra = sorted(set(identity_rows) - set(paths))
    if missing or extra:
        raise ValueError(f"identity/path mismatch: missing={len(missing)} extra={len(extra)}")
    by_content: dict[str, dict[str, Any]] = {}
    for index, path in enumerate(paths):
        row = identity_rows[path]
        content = row.get("content_sha256")
        if not isinstance(content, str) or len(content) != 64:
            raise ValueError(f"invalid content hash for {path}")
        item = by_content.setdefault(content, {
            "content_sha256": content,
            "embedding_row_indices": [],
            "paths": [],
            "size_bytes": row.get("size_bytes"),
        })
        item["embedding_row_indices"].append(index)
        item["paths"].append(path)
    records = sorted(by_content.values(), key=lambda item: item["content_sha256"])
    for record in records:
        record["paths"] = sorted(record["paths"])
        record["canonical_path"] = record["paths"][0]
        record["alias_count"] = len(record["paths"]) - 1
    return {
        "record_type": "slo_content_addressed_embedding_index",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "model_version": model_version,
        "embedding_dimensions": int(embedding_dimensions),
        "n_embedding_rows": len(paths),
        "n_content_ids": len(records),
        "n_alias_paths": sum(record["alias_count"] for record in records),
        "records": records,
        "safety": {
            "read_only": True,
            "source_audio_modified": False,
            "embedding_values_modified": False,
            "path_aliases_retained": True,
            "content_sha256_is_complete_file_hash": True,
            "rename_actions": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embeddings", type=Path, required=True)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--model-version", default="candidate_embeddings_testing_v1")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    data = np.load(args.embeddings, allow_pickle=True)
    identity = json.loads(args.identity.read_text(encoding="utf-8"))
    result = build_index([str(value) for value in data["paths"]], identity, args.model_version, int(data["emb"].shape[1]))
    result["embedding_cache"] = {
        "path": str(args.embeddings.resolve()),
        "sha256": hashlib.sha256(args.embeddings.read_bytes()).hexdigest(),
    }
    result["identity_manifest"] = {
        "path": str(args.identity.resolve()),
        "sha256": hashlib.sha256(args.identity.read_bytes()).hexdigest(),
    }
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("n_embedding_rows", "n_content_ids", "n_alias_paths", "embedding_dimensions")}, indent=2))


if __name__ == "__main__":
    main()
