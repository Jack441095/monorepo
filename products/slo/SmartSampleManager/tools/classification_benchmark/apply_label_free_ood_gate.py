#!/usr/bin/env python3
"""Apply a corpus-relative embedding novelty gate to fused decisions.

High-novelty rows are downgraded from ``suggest`` to ``review`` while retaining
the suppressed candidate as review evidence.  The gate is advisory and never
creates labels or file actions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


VERSION = "label_free_ood_gate_v1"


def _read(path: Path, record_type: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("record_type") != record_type:
        raise ValueError(f"unexpected record type in {path}")
    safety = payload.get("safety") or {}
    if (not safety.get("read_only") or safety.get("semantic_labels_created")
            or safety.get("rename_actions") or safety.get("auto_action_allowed")):
        raise ValueError(f"input is not read-only: {path}")
    return payload


def apply(fused: Path, ood: Path, out: Path,
          threshold: float = 0.35) -> dict[str, Any]:
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between zero and one")
    fused_payload = _read(fused, "slo_label_free_fused_decision_receipt")
    ood_payload = _read(ood, "slo_label_free_embedding_ood_receipt")
    ood_rows = {str(row["path"]): row for row in ood_payload.get("rows", [])
                if isinstance(row, dict) and isinstance(row.get("path"), str)}
    rows: list[dict[str, Any]] = []
    missing = 0
    overridden = 0
    for original in fused_payload.get("rows", []):
        if not isinstance(original, dict) or not isinstance(original.get("path"), str):
            raise ValueError("fused row has no path")
        row = dict(original)
        novelty_row = ood_rows.get(original["path"])
        if novelty_row is None:
            missing += 1
            row["ood_novelty_score"] = None
            row["ood_override"] = False
        else:
            novelty = float(novelty_row.get("novelty_score"))
            row["ood_novelty_score"] = novelty
            row["ood_override"] = False
            if row.get("decision") == "suggest" and novelty >= threshold:
                overridden += 1
                row["ood_override"] = True
                row["suppressed_candidate_label"] = row.get("candidate_label")
                row["candidate_label"] = None
                row["decision"] = "review"
                reasons = list(row.get("reasons") or [])
                reasons.append("embedding_novelty_above_review_gate")
                row["reasons"] = sorted(set(reasons))
        rows.append(row)
    if missing:
        raise ValueError(f"OOD receipt is missing {missing} fused paths")
    result = {
        "record_type": "slo_label_free_ood_gated_decision_receipt",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "source_fused_decisions": str(fused.resolve()),
        "source_fused_decisions_sha256": hashlib.sha256(fused.read_bytes()).hexdigest(),
        "source_ood_receipt": str(ood.resolve()),
        "source_ood_receipt_sha256": hashlib.sha256(ood.read_bytes()).hexdigest(),
        "n_files": len(rows),
        "n_original_suggest": sum(row.get("decision") == "suggest" for row in fused_payload.get("rows", [])),
        "n_ood_overridden": overridden,
        "n_suggest": sum(row.get("decision") == "suggest" for row in rows),
        "n_review": sum(row.get("decision") == "review" for row in rows),
        "novelty_review_threshold": threshold,
        "rows": rows,
        "calibration": "corpus_relative_leave_one_out_knn_novelty_uncalibrated",
        "accuracy_claim": None,
        "safety": {
            "read_only": True,
            "ground_truth_read": False,
            "semantic_labels_created": False,
            "rename_actions": False,
            "source_audio_modified": False,
            "auto_action_allowed": False,
            "human_approval_required": True,
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fused", type=Path, required=True)
    parser.add_argument("--ood", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--threshold", type=float, default=0.35)
    args = parser.parse_args()
    result = apply(args.fused, args.ood, args.out, args.threshold)
    print(json.dumps({"out": str(args.out), "n_files": result["n_files"],
                      "n_ood_overridden": result["n_ood_overridden"],
                      "n_suggest": result["n_suggest"], "read_only": True}, indent=2))


if __name__ == "__main__":
    main()
