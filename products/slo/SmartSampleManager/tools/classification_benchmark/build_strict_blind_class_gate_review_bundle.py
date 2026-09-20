#!/usr/bin/env python3
"""Build a filename/folder-blind class-gate review bundle.

The candidate manifest is evaluator-side data and must not be shown to the
reviewer.  This command copies each selected audio file to a fresh staging
directory under a deterministic opaque basename, emits a reviewer CSV with no
original path or candidate fields, and writes a separate evaluator mapping
that binds the staged file back to its candidate row.  Source audio is never
modified and no label or policy is created.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any


VERSION = "strict_blind_class_gate_review_bundle_v1"
REVIEW_FIELDS = [
    "id",
    "review_path",
    "content_sha256",
    "review_prompt",
    "human_label",
    "reviewer",
    "note",
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_rows(manifest_path: Path) -> list[dict[str, Any]]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        # Accept the generated receipt form, but never accept an arbitrary
        # record type that could accidentally be treated as a validation set.
        if payload.get("record_type") != "slo_class_conditional_gate_validation_manifest":
            raise ValueError("manifest receipt has an unexpected record type")
        rows = payload.get("items")
    else:
        rows = payload
    if not isinstance(rows, list) or not rows:
        raise ValueError("validation manifest must contain a non-empty list")

    required = {"id", "path", "candidate_class", "candidate_confidence", "vendor"}
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict) or not required.issubset(row):
            raise ValueError("every manifest row must contain candidate and identity fields")
        row_id = str(row["id"])
        raw_source = os.fspath(row["path"])
        if not os.path.isabs(raw_source):
            raise ValueError("review paths must be absolute")
        source = Path(os.path.realpath(raw_source))
        if row_id in seen_ids:
            raise ValueError(f"duplicate manifest id: {row_id}")
        if str(source) in seen_paths:
            raise ValueError(f"duplicate manifest path: {source}")
        if not source.is_file():
            raise ValueError(f"review audio file does not exist: {source}")
        if not str(row.get("vendor", "")).strip():
            raise ValueError(f"manifest row {row_id} is missing vendor")
        seen_ids.add(row_id)
        seen_paths.add(str(source))
        normalized.append({
            "id": row_id,
            "source": str(source),
            "candidate_class": str(row["candidate_class"]),
            "candidate_confidence": float(row["candidate_confidence"]),
            "candidate_similarity": (
                float(row["candidate_similarity"])
                if row.get("candidate_similarity") is not None else None
            ),
            "vendor": str(row["vendor"]),
        })
    return normalized


def _assert_fresh_output(output_dir: Path, sources: list[str]) -> None:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"output directory must be new and empty: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_real = Path(os.path.realpath(output_dir))
    for source_value in sources:
        source_parent = Path(os.path.realpath(source_value)).parent
        try:
            common = os.path.commonpath((str(output_real), str(source_parent)))
        except ValueError:
            # Different filesystem roots are safe.
            continue
        if common == str(source_parent):
            raise ValueError("output directory must not be inside a source-audio directory")


def build_bundle(manifest_path: Path, output_dir: Path) -> dict[str, Any]:
    rows = _load_rows(manifest_path)
    _assert_fresh_output(output_dir, [row["source"] for row in rows])
    audio_dir = output_dir / "review_audio"
    evaluator_dir = output_dir / "evaluator"
    audio_dir.mkdir(parents=True, exist_ok=False)
    evaluator_dir.mkdir(parents=True, exist_ok=False)

    review_rows: list[dict[str, Any]] = []
    evaluator_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        source = Path(row["source"])
        content_hash = _sha256(source)
        suffix = source.suffix.lower()
        if not suffix or len(suffix) > 8 or not suffix[1:].isalnum():
            suffix = ".audio"
        staged_name = f"sample_{index:04d}_{content_hash[:16]}{suffix}"
        staged = audio_dir / staged_name
        shutil.copyfile(source, staged)
        staged_hash = _sha256(staged)
        if staged_hash != content_hash:
            raise RuntimeError(f"staged content hash mismatch for {source}")

        review_rows.append({
            "id": row["id"],
            "review_path": str(staged.resolve()),
            "content_sha256": content_hash,
            "review_prompt": (
                "Listen to the audio only. Enter the best supported frozen class; "
                "use UNKNOWN/OOD when no class is defensible."
            ),
            "human_label": "",
            "reviewer": "",
            "note": "",
        })
        evaluator_rows.append({
            "id": row["id"],
            "staged_path": str(staged.resolve()),
            "source_path": row["source"],
            "content_sha256": content_hash,
            "candidate_class": row["candidate_class"],
            "candidate_confidence": row["candidate_confidence"],
            "candidate_similarity": row["candidate_similarity"],
            "vendor": row["vendor"],
        })

    csv_path = output_dir / "review_queue.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_FIELDS)
        writer.writeheader()
        writer.writerows(review_rows)

    evaluator_path = evaluator_dir / "candidate_mapping.json"
    evaluator_path.write_text(json.dumps({
        "record_type": "slo_strict_blind_class_gate_evaluator_mapping",
        "schema_version": "1.0.0",
        "rows": evaluator_rows,
        "safety": {
            "reviewer_candidate_fields_excluded": True,
            "labels_created": False,
            "policy_promoted": False,
            "rename_actions": False,
            "source_audio_modified": False,
        },
    }, indent=2) + "\n", encoding="utf-8")

    receipt = {
        "record_type": "slo_strict_blind_class_gate_review_bundle",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "source_manifest": str(manifest_path.resolve()),
        "source_manifest_sha256": _sha256(manifest_path),
        "bundle_dir": str(output_dir.resolve()),
        "review_csv": str(csv_path.resolve()),
        "review_csv_sha256": _sha256(csv_path),
        "evaluator_mapping": str(evaluator_path.resolve()),
        "evaluator_mapping_sha256": _sha256(evaluator_path),
        "n_rows": len(review_rows),
        "safety": {
            "filename_folder_semantics_hidden": True,
            "embedded_metadata_stripped": False,
            "candidate_fields_hidden_from_review_csv": True,
            "labels_created": False,
            "policy_promoted": False,
            "rename_actions": False,
            "source_audio_modified": False,
        },
    }
    receipt_path = output_dir / "bundle_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    receipt["bundle_receipt"] = str(receipt_path.resolve())
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    receipt = build_bundle(args.manifest, args.output_dir)
    print(json.dumps({"n_rows": receipt["n_rows"], "bundle_dir": receipt["bundle_dir"]}, indent=2))


if __name__ == "__main__":
    main()
