#!/usr/bin/env python3
"""Build a read-only exact-content duplicate inventory.

Content identity is deliberately resolved before acoustic similarity.  The
output chooses a deterministic canonical path for each exact byte-identical
group and retains every alias path.  It is an inventory for review and
downstream never-act decisions; it never deletes, moves, renames, or rewrites
audio.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


VERSION = "canonical_duplicate_groups_v1"
CHUNK_SIZE = 1024 * 1024


def sha256_file(path: str | os.PathLike[str], chunk_size: int = CHUNK_SIZE) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _iter_paths(paths: Iterable[str | os.PathLike[str]]) -> list[str]:
    # Canonical ordering makes receipts deterministic even when an upstream
    # manifest was produced by a parallel scanner.
    return sorted({os.path.abspath(os.fspath(path)) for path in paths})


def group_paths(paths: Iterable[str | os.PathLike[str]]) -> dict[str, Any]:
    ordered = _iter_paths(paths)
    errors: list[dict[str, str]] = []
    by_size: dict[int, list[str]] = defaultdict(list)
    for path in ordered:
        try:
            by_size[os.path.getsize(path)].append(path)
        except OSError as exc:
            errors.append({"path": path, "error": str(exc)})

    # Hash only files that can have a byte-identical partner. This preserves
    # exactness while avoiding an unnecessary second pass for unique sizes.
    candidates = [path for paths_for_size in by_size.values()
                  if len(paths_for_size) > 1 for path in paths_for_size]
    by_hash: dict[str, list[str]] = defaultdict(list)
    records: list[dict[str, Any]] = []
    for path in candidates:
        try:
            size = os.path.getsize(path)
            digest = sha256_file(path)
            by_hash[digest].append(path)
            records.append({"path": path, "size_bytes": size, "sha256": digest})
        except (OSError, PermissionError) as exc:
            errors.append({"path": path, "error": str(exc)})

    groups = []
    for digest, members in sorted(by_hash.items()):
        if len(members) < 2:
            continue
        members = sorted(members)
        groups.append({
            "sha256": digest,
            "size_bytes": os.path.getsize(members[0]),
            "canonical_path": members[0],
            "alias_paths": members[1:],
            "member_count": len(members),
            "decision": "never_act_without_explicit_duplicate_review",
        })

    return {
        "record_type": "slo_canonical_duplicate_groups",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "summary": {
            "n_input_paths": len(ordered),
            "n_missing_or_error": len(errors),
            "n_hashed": len(records),
            "n_exact_duplicate_groups": len(groups),
            "n_duplicate_aliases": sum(g["member_count"] - 1 for g in groups),
        },
        "groups": groups,
        "errors": errors,
        "safety": {
            "read_only": True,
            "source_files_modified": False,
            "files_deleted": False,
            "files_moved": False,
            "rename_actions": False,
            "content_hash_is_byte_identity": True,
            "canonical_path_is_not_an_apply_instruction": True,
        },
    }


def _load_paths(path: Path) -> list[str]:
    if path.suffix == ".npz":
        import numpy as np
        data = np.load(path, allow_pickle=True)
        return [str(value) for value in data["paths"]]
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [str(value) for value in payload]
    if isinstance(payload, dict) and isinstance(payload.get("paths"), list):
        return [str(value) for value in payload["paths"]]
    raise ValueError("input must be an NPZ with paths or JSON list/object with paths")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True,
                        help="NPZ embedding cache or JSON path manifest")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = group_paths(_load_paths(args.input))
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
