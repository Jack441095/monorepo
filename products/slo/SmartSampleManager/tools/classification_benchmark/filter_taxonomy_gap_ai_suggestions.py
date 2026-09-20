#!/usr/bin/env python3
"""Filter label-free AI suggestions to each taxonomy row's offered options.

The CLAP receipt is an open-world prompt score and is not calibrated ground
truth. This adapter only makes it useful as review evidence: it joins rows by
verified content hash/path, keeps alternatives allowed by that row's candidate
options, and never writes an owner label or changes the queue.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def filter_suggestions(queue_path: Path, receipt_path: Path, output_path: Path) -> dict[str, Any]:
    output_path = output_path.resolve()
    protected = [queue_path.resolve(), receipt_path.resolve()]
    if output_path in protected:
        raise ValueError("AI evidence output must be different from its inputs")
    if output_path.exists():
        for source in (queue_path, receipt_path):
            try:
                if os.path.samefile(output_path, source):
                    raise ValueError("AI evidence output must not alias an input")
            except OSError:
                pass
    with queue_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle); queue = list(reader)
    required = {"id", "path", "content_sha256", "candidate_parent_options"}
    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        raise ValueError("queue is missing required fields")
    by_hash: dict[str, dict[str, str]] = {}
    for row in queue:
        content_hash = (row.get("content_sha256") or "").strip().lower()
        if len(content_hash) != 64 or content_hash in by_hash:
            raise ValueError("queue has missing or duplicate content hash")
        by_hash[content_hash] = row

    lines = [json.loads(line) for line in receipt_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines or lines[0].get("record_type") != "slo_label_free_zero_shot_receipt":
        raise ValueError("input is not a zero-shot receipt")
    header, rows = lines[0], lines[1:]
    safety = header.get("safety") or {}
    if not safety.get("read_only") or safety.get("semantic_labels_created") or safety.get("rename_actions"):
        raise ValueError("zero-shot receipt is not read-only")
    output_rows: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    unmatched = 0
    for row in rows:
        content_hash = str(row.get("content_sha256") or "").lower()
        queue_row = by_hash.get(content_hash)
        if queue_row is None:
            unmatched += 1
            continue
        if content_hash in seen_hashes:
            raise ValueError(f"duplicate receipt content hash: {content_hash}")
        seen_hashes.add(content_hash)
        options = [x.strip() for x in queue_row.get("candidate_parent_options", "").split("|") if x.strip()]
        allowed = {x for x in options if x != "OOD"} | {"OOD"}
        alternatives = [item for item in (row.get("alternatives") or [])
                        if isinstance(item, dict) and item.get("label") in allowed]
        alternatives.sort(key=lambda item: float(item.get("score", float("-inf"))), reverse=True)
        candidate = alternatives[0] if alternatives else None
        candidate_score = float(candidate["score"]) if candidate and isinstance(candidate.get("score"), (int, float)) else None
        second_score = float(alternatives[1]["score"]) if len(alternatives) > 1 and isinstance(alternatives[1].get("score"), (int, float)) else None
        output_rows.append({
            "path": queue_row["path"], "content_sha256": content_hash,
            "queue_id": queue_row["id"],
            "candidate_parent_options": queue_row["candidate_parent_options"],
            "ai_candidate_label": candidate.get("label") if candidate else None,
            "ai_candidate_score": candidate_score,
            "ai_candidate_margin": candidate_score - second_score if candidate_score is not None and second_score is not None else None,
            "ai_allowed_alternatives": alternatives[:5],
            "ai_original_suggestion": row.get("zero_shot_suggestion"),
            "ai_original_status": row.get("status", "review"),
            "ai_view_agreement": row.get("view_agreement"),
            "semantic_label": None,
            "review_state": "owner_review_required",
        })
    output_rows.sort(key=lambda row: row["path"])
    result = {
        "record_type": "slo_taxonomy_gap_ai_option_filtered_receipt",
        "schema_version": "1.0.0",
        "queue": str(queue_path.resolve()), "queue_sha256": sha256_file(queue_path),
        "source_receipt": str(receipt_path.resolve()),
        "source_receipt_sha256": sha256_file(receipt_path),
        "n_queue_rows": len(queue), "n_receipt_rows": len(rows),
        "n_output_rows": len(output_rows), "n_unmatched_receipt_rows": unmatched,
        "n_ai_candidate_rows": sum(row["ai_candidate_label"] is not None for row in output_rows),
        "n_original_suggest_rows": sum(row["ai_original_status"] == "suggest" for row in output_rows),
        "rows": output_rows,
        "safety": {
            "read_only": True, "semantic_labels_created": False,
            "owner_labels_created": False, "training_data_created": False,
            "rename_actions": False, "source_audio_modified": False,
            "suggestions_are_uncalibrated": True, "human_approval_required": True,
        },
    }
    if len(output_rows) != len(queue) or unmatched:
        raise ValueError(f"receipt/queue coverage mismatch: output={len(output_rows)} queue={len(queue)} unmatched={unmatched}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".taxonomy_gap_ai_", suffix=".json",
                                      dir=output_path.parent)
    os.close(fd)
    try:
        Path(temporary).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, output_path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    result = filter_suggestions(args.queue, args.receipt, args.out)
    print(json.dumps({"out": str(args.out), "rows": result["n_output_rows"],
                      "candidates": result["n_ai_candidate_rows"], "read_only": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
