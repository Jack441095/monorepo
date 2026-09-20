#!/usr/bin/env python3
"""Merge owner-adjudicated taxonomy rows into a research manifest.

The adjudication importer intentionally emits only newly reviewed rows.  This
command joins those rows to an existing manifest for the next preflight pass.
It verifies paths and complete-file SHA-256 values again, assigns fresh
manifest IDs, and excludes duplicate-content aliases so a copied sample cannot
silently enter a held-out evaluation twice.  The output is research evidence
only; production taxonomy, cache and policy are never modified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any


KNOWN_CLASSES = {
    "Kick", "Snare", "Hi-Hat", "Clap", "Percussion", "Bass One-Shot",
    "Bass Loop", "Synth", "Synth Loop", "Vocal Phrase", "Vocal Loop",
    "Impact", "Riser", "Foley", "FX", "Atmosphere", "Music Loop", "OOD",
}
REQUIRED_DECISION_FIELDS = {
    "path", "sha256", "expected_subcategory", "ood", "label_authority",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_list(path: Path, description: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {description}: {exc}") from exc
    if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
        raise ValueError(f"{description} must be a JSON list of objects")
    return payload


def merge_manifests(base_path: Path, decisions_path: Path,
                    output_path: Path) -> dict[str, Any]:
    base = _load_list(base_path, "base manifest")
    decisions = _load_list(decisions_path, "adjudication manifest")
    base_paths: set[str] = set()
    base_hashes: Counter[str] = Counter()
    max_id = 0
    for index, row in enumerate(base):
        path = str(row.get("path", ""))
        content_hash = str(row.get("sha256", "")).lower()
        if not os.path.isabs(path) or not Path(path).is_file() or path in base_paths:
            raise ValueError(f"base manifest has missing or duplicate path at row {index}")
        if len(content_hash) != 64:
            raise ValueError(f"base manifest has invalid sha256 at row {index}")
        if sha256_file(Path(path)) != content_hash:
            raise ValueError(f"base manifest hash mismatch at row {index}: {path}")
        base_paths.add(path)
        base_hashes[content_hash] += 1
        try:
            max_id = max(max_id, int(row.get("sample_id", 0)))
        except (TypeError, ValueError):
            raise ValueError(f"base manifest has invalid sample_id at row {index}")

    merged = [dict(row) for row in base]
    accepted: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    decision_paths: set[str] = set()
    decision_hashes: set[str] = set()
    for index, row in enumerate(decisions):
        missing = sorted(REQUIRED_DECISION_FIELDS - set(row))
        if missing:
            raise ValueError(f"adjudication row {index} missing fields: {missing}")
        path = str(row.get("path", ""))
        if not os.path.isabs(path) or not Path(path).is_file():
            raise ValueError(f"adjudication source path does not exist: {path}")
        resolved = str(Path(path).resolve())
        expected_hash = str(row.get("sha256", "")).strip().lower()
        if len(expected_hash) != 64 or sha256_file(Path(resolved)) != expected_hash:
            raise ValueError(f"adjudication hash mismatch: {resolved}")
        label = str(row.get("expected_subcategory", "")).strip()
        authority = str(row.get("label_authority", "")).strip()
        if authority != "OWNER_ADJUDICATION":
            raise ValueError(f"adjudication row {index} is not owner-authorized")
        if label not in KNOWN_CLASSES:
            raise ValueError(f"adjudication row {index} has unsupported label: {label!r}")
        if label == "OOD" and row.get("ood") is not True:
            raise ValueError(f"OOD adjudication row {index} must set ood=true")
        if label != "OOD" and row.get("ood") is True:
            raise ValueError(f"known adjudication row {index} cannot set ood=true")

        if resolved in base_paths:
            blocked.append({"path": resolved, "reason": "path_already_in_base_manifest"})
            continue
        if resolved in decision_paths:
            blocked.append({"path": resolved, "reason": "duplicate_decision_path"})
            continue
        if expected_hash in base_hashes:
            blocked.append({"path": resolved, "reason": "duplicate_content_existing"})
            continue
        if expected_hash in decision_hashes:
            blocked.append({"path": resolved, "reason": "duplicate_content_decision"})
            continue

        max_id += 1
        new_row = dict(row)
        new_row["sample_id"] = max_id
        new_row["path"] = resolved
        new_row["filename"] = Path(resolved).name
        new_row["sha256"] = expected_hash
        new_row["review_status"] = "adjudicated"
        accepted.append(new_row)
        decision_paths.add(resolved)
        decision_hashes.add(expected_hash)

    merged.extend(accepted)
    receipt = {
        "record_type": "slo_taxonomy_gap_adjudication_manifest_merge",
        "schema_version": "1.0.0",
        "base_manifest": str(base_path.resolve()),
        "base_manifest_sha256": sha256_file(base_path),
        "adjudication_manifest": str(decisions_path.resolve()),
        "adjudication_manifest_sha256": sha256_file(decisions_path),
        "output_manifest": str(output_path.resolve()),
        "base_rows": len(base),
        "decision_rows": len(decisions),
        "accepted_rows": len(accepted),
        "blocked_rows": len(blocked),
        "blocked_reason_counts": dict(Counter(row["reason"] for row in blocked)),
        "merged_rows": len(merged),
        "merged_known_rows": sum(row.get("expected_subcategory") != "OOD" for row in merged),
        "merged_ood_rows": sum(row.get("expected_subcategory") == "OOD" for row in merged),
        "blocked": blocked,
        "safety": {
            "read_only": True,
            "source_audio_modified": False,
            "labels_invented": False,
            "duplicate_content_added": False,
            "production_cache_modified": False,
            "production_policy_changed": False,
        },
    }
    output_path = output_path.resolve()
    if output_path.exists():
        raise ValueError(f"refusing to overwrite existing output: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".merged_research_manifest_",
                                      suffix=".json", dir=output_path.parent)
    os.close(fd)
    try:
        Path(temporary).write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, output_path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    receipt["output_manifest_sha256"] = sha256_file(output_path)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-manifest", type=Path, required=True)
    parser.add_argument("--adjudication-manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    args = parser.parse_args(argv)
    receipt = merge_manifests(args.base_manifest, args.adjudication_manifest, args.out)
    args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
    args.receipt_out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"merged_rows": receipt["merged_rows"],
                      "accepted_rows": receipt["accepted_rows"],
                      "blocked_rows": receipt["blocked_rows"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
