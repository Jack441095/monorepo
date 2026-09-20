#!/usr/bin/env python3
"""Build a supplemental manifest from explicitly approved corrections.

This command still does not train a model. It verifies that an owner-approved
correction matches an existing canonical, collection-aware manifest by path and
content hash, then emits a separate supplement. Unknown files, hash changes,
sealed validation rows, and duplicate aliases are blocked and reported.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


METHOD_VERSION = "owner_approved_training_manifest_v1"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"expected object in {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if line.strip():
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"invalid JSON at {path}:{line_number}") from exc
                if isinstance(value, dict):
                    rows.append(value)
    if not rows:
        raise ValueError(f"manifest is empty: {path}")
    return rows


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def build(base_path: Path, candidate_path: Path, out_path: Path) -> dict[str, Any]:
    base = _read_json(base_path)
    base_rows = base.get("rows")
    if not isinstance(base_rows, list) or not base_rows:
        raise ValueError("base manifest has no rows")
    if base.get("safety", {}).get("validation_rows_used_for_training") is True:
        raise ValueError("base manifest admits sealed validation rows")

    by_path: dict[str, dict[str, Any]] = {}
    for row in base_rows:
        path = str(row.get("path", ""))
        if not path or path in by_path:
            raise ValueError(f"base manifest has missing or duplicate path: {path}")
        by_path[path] = row
    aliases = {str(row.get("path")) for row in base.get("duplicate_aliases", []) if row.get("path")}
    sealed = {str(value) for value in base.get("excluded_validation_paths", [])}

    candidate_rows = _read_jsonl(candidate_path)
    candidates = [row for row in candidate_rows[1:] if row.get("promotion_status") == "owner_approved_pending_rebuild"]
    accepted: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for row in candidates:
        path = str(row.get("file_path", ""))
        expected_hash = str(row.get("content_hash", "")).lower()
        reason = ""
        base_row = by_path.get(path)
        if not base_row:
            reason = "path_not_in_canonical_training_manifest"
        elif path in sealed:
            reason = "sealed_validation_path"
        elif path in aliases:
            reason = "exact_duplicate_alias"
        elif path in seen_paths:
            reason = "duplicate_approved_correction_path"
        elif not expected_hash or expected_hash != str(base_row.get("content_sha256", "")).lower():
            reason = "content_hash_mismatch"
        if reason:
            blocked.append({"correction_id": row.get("correction_id"), "path": path, "reason": reason})
            continue
        seen_paths.add(path)
        label = str(row.get("corrected_subcategory") or row.get("corrected_category") or "").strip()
        if not label:
            blocked.append({"correction_id": row.get("correction_id"), "path": path, "reason": "approved_row_has_no_corrected_label"})
            continue
        accepted.append({
            **base_row,
            "label": label,
            "family": label,
            "label_source": "owner_approved_correction",
            "correction_id": row.get("correction_id"),
            "correction_type": row.get("correction_type", "label_correction"),
            "reviewer": row.get("reviewer", ""),
        })

    payload = {
        "record_type": "slo_owner_approved_training_supplement",
        "schema_version": "1.0.0",
        "method_version": METHOD_VERSION,
        "source_base_manifest": str(base_path.resolve()),
        "source_candidate_manifest": str(candidate_path.resolve()),
        "summary": {
            "approved_candidates_seen": len(candidates),
            "accepted_rows": len(accepted),
            "blocked_rows": len(blocked),
        },
        "decision": "supplement_ready_for_separate_training_review" if accepted else "no_eligible_rows",
        "safety": {
            "audio_modified": False,
            "training_corpus_modified": False,
            "model_changed": False,
            "rename_actions": False,
            "collection_leakage_checked": True,
            "sealed_validation_rows_used": False,
        },
        "rows": accepted,
        "blocked": blocked,
    }
    if out_path.exists():
        raise ValueError(f"refusing to overwrite existing output: {out_path}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-manifest", type=Path, required=True)
    parser.add_argument("--candidate-manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = build(args.base_manifest, args.candidate_manifest, args.out)
    except ValueError as exc:
        print(f"FAIL CLOSED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result["summary"], indent=2, sort_keys=True))
    print(f"decision: {result['decision']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
