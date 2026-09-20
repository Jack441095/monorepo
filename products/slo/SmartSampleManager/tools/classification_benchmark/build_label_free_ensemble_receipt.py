#!/usr/bin/env python3
"""Combine two independent label-free receipts with a conservative agreement gate.

This is an evidence combiner, not a classifier.  It never reads ground-truth
labels, writes metadata, renames files, or modifies source audio.  A row can
remain ``suggest`` only when both receipts agree on the top label and both
individual rows were already suggestions; every disagreement is ``review``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


VERSION = "label_free_ensemble_v1"


def _read(path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        raise ValueError(f"receipt is empty: {path}")
    header = json.loads(lines[0])
    if header.get("record_type") != "slo_label_free_zero_shot_receipt":
        raise ValueError("receipt has an incompatible record_type")
    safety = header.get("safety") or {}
    if not safety.get("read_only") or safety.get("semantic_labels_created") or safety.get("rename_actions"):
        raise ValueError("receipt is not a read-only suggestion receipt")
    rows: dict[str, dict[str, Any]] = {}
    for line in lines[1:]:
        row = json.loads(line)
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            raise ValueError("receipt row has no path")
        if row["path"] in rows:
            raise ValueError(f"duplicate path in receipt: {row['path']}")
        rows[row["path"]] = row
    return header, rows


def combine(primary: Path, secondary: Path, out: Path) -> dict[str, Any]:
    h1, r1 = _read(primary)
    h2, r2 = _read(secondary)
    if h1.get("prompt_bank") != h2.get("prompt_bank"):
        raise ValueError("prompt banks do not match")
    # A decoder error may legitimately be absent from a resumed receipt.  It
    # is safe to union those paths as review-only; any successful row missing
    # from the other receipt still fails closed as a coverage mismatch.
    extra1 = set(r1) - set(r2)
    extra2 = set(r2) - set(r1)
    if any(r1[p].get("error") is None for p in extra1) or any(r2[p].get("error") is None for p in extra2):
        raise ValueError("receipts do not cover the same paths (successful coverage mismatch)")
    rows: list[dict[str, Any]] = []
    for path in sorted(r1):
        a, b = r1.get(path), r2.get(path)
        if a is None or b is None:
            present = a or b or {}
            rows.append({
                "path": path,
                "content_sha256": present.get("content_sha256"),
                "status": "review",
                "semantic_label": None,
                "ensemble_suggestion": None,
                "model_a_suggestion": a.get("zero_shot_suggestion") if a else None,
                "model_b_suggestion": b.get("zero_shot_suggestion") if b else None,
                "model_agreement": False,
                "model_a_status": a.get("status") if a else "missing",
                "model_b_status": b.get("status") if b else "missing",
                "calibration": "uncalibrated_multi_model_agreement",
                "error": {"model_a": a.get("error") if a else "missing from receipt",
                          "model_b": b.get("error") if b else "missing from receipt"},
            })
            continue
        a_label = a.get("zero_shot_suggestion")
        b_label = b.get("zero_shot_suggestion")
        agree = bool(a_label and a_label == b_label)
        a_ok = a.get("status") == "suggest"
        b_ok = b.get("status") == "suggest"
        status = "suggest" if agree and a_ok and b_ok else "review"
        scores = [x for x in (a.get("semantic_score"), b.get("semantic_score"))
                  if isinstance(x, (int, float))]
        margins = [x for x in (a.get("margin"), b.get("margin"))
                   if isinstance(x, (int, float))]
        row: dict[str, Any] = {
            "path": path,
            "content_sha256": a.get("content_sha256") if a.get("content_sha256") == b.get("content_sha256") else None,
            "status": status,
            "semantic_label": None,
            "ensemble_suggestion": a_label if agree else None,
            "model_a_suggestion": a_label,
            "model_b_suggestion": b_label,
            "model_agreement": agree,
            "model_a_status": a.get("status"),
            "model_b_status": b.get("status"),
            "model_a_score": a.get("semantic_score"),
            "model_b_score": b.get("semantic_score"),
            "model_a_margin": a.get("margin"),
            "model_b_margin": b.get("margin"),
            "score_mean": sum(scores) / len(scores) if scores else None,
            "margin_mean": sum(margins) / len(margins) if margins else None,
            "calibration": "uncalibrated_multi_model_agreement",
            "evidence": {
                "model_a": {"alternatives": a.get("alternatives", []), "view_agreement": a.get("view_agreement")},
                "model_b": {"alternatives": b.get("alternatives", []), "view_agreement": b.get("view_agreement")},
            },
        }
        if a.get("error") or b.get("error"):
            row["error"] = {"model_a": a.get("error"), "model_b": b.get("error")}
        rows.append(row)
    n_suggest = sum(row["status"] == "suggest" for row in rows)
    header = {
        "record_type": "slo_label_free_ensemble_receipt",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "primary_receipt": str(primary.resolve()),
        "secondary_receipt": str(secondary.resolve()),
        "models": [h1.get("model"), h2.get("model")],
        "prompt_bank": h1.get("prompt_bank"),
        "n_files": len(rows),
        "n_suggest": n_suggest,
        "n_review": len(rows) - n_suggest,
        "views": [h1.get("views", 1), h2.get("views", 1)],
        "safety": {
            "read_only": True,
            "semantic_labels_created": False,
            "ground_truth_read": False,
            "training_data_created": False,
            "rename_actions": False,
            "source_audio_modified": False,
            "suggestions_are_uncalibrated": True,
            "human_approval_required": True,
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(header, sort_keys=True) + "\n")
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    return header


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary", type=Path, required=True)
    parser.add_argument("--secondary", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(combine(args.primary, args.secondary, args.out), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
