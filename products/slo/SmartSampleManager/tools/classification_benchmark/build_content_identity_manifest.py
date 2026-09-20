#!/usr/bin/env python3
"""Build a content-addressed, read-only identity manifest for local audio.

The SHA-256 is over the complete file bytes. Paths remain visible aliases, but
future embedding/cache records can key by `content_sha256` so moves and exact
duplicates do not create new identities.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


VERSION = "content_identity_manifest_v1"
CHUNK_SIZE = 1024 * 1024
AUDIO_EXTS = {".wav", ".aif", ".aiff", ".flac"}


def full_sha256(path: str | os.PathLike[str]) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(CHUNK_SIZE)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def build_manifest(paths: Iterable[str | os.PathLike[str]]) -> dict[str, Any]:
    ordered = sorted({os.path.abspath(os.fspath(value)) for value in paths})
    rows = []
    errors = []
    by_content: dict[str, list[str]] = defaultdict(list)
    for path in ordered:
        try:
            stat = os.stat(path)
            content = full_sha256(path)
            row = {
                "path": path,
                "content_sha256": content,
                "size_bytes": int(stat.st_size),
                "mtime_ns_at_scan": int(stat.st_mtime_ns),
            }
            rows.append(row)
            by_content[content].append(path)
        except OSError as exc:
            errors.append({"path": path, "error": str(exc)})
    duplicate_content = {
        content: sorted(members)
        for content, members in by_content.items() if len(members) > 1
    }
    return {
        "record_type": "slo_content_identity_manifest",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "n_input_paths": len(ordered),
        "n_hashed": len(rows),
        "n_errors": len(errors),
        "n_unique_content_ids": len(by_content),
        "n_duplicate_aliases": sum(len(members) - 1 for members in duplicate_content.values()),
        "rows": rows,
        "duplicate_content_groups": duplicate_content,
        "errors": errors,
        "safety": {
            "read_only": True,
            "source_audio_modified": False,
            "paths_modified": False,
            "cache_key_is_complete_file_sha256": True,
            "rename_actions": False,
        },
    }


def collect(root: str | os.PathLike[str]) -> list[str]:
    """Collect supported audio under ``root`` without following symlinks."""
    root_path = Path(root).resolve()
    if not root_path.is_dir():
        raise ValueError(f"identity root is not a directory: {root_path}")
    paths = []
    for directory, dirnames, filenames in os.walk(root_path):
        dirnames[:] = sorted(name for name in dirnames
                              if not name.startswith("."))
        for name in sorted(filenames):
            if name.startswith((".", "._")):
                continue
            path = Path(directory) / name
            if path.is_symlink() or path.suffix.lower() not in AUDIO_EXTS:
                continue
            paths.append(str(path.resolve()))
    return sorted(paths)
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
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path,
                        help="NPZ or JSON path manifest")
    source.add_argument("--root", type=Path,
                        help="directory to scan for supported audio")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    paths = collect(args.root) if args.root is not None else _load_paths(args.input)
    result = build_manifest(paths)
    if args.root is not None:
        result["source_root"] = str(args.root.resolve())
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("n_input_paths", "n_hashed", "n_errors", "n_unique_content_ids", "n_duplicate_aliases")}, indent=2))


if __name__ == "__main__":
    main()
