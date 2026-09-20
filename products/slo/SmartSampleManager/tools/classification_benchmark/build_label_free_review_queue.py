#!/usr/bin/env python3
"""Build a ranked, read-only review queue from a label-free receipt.

The queue prioritises uncertainty rather than pretending uncalibrated CLAP
scores are probabilities. Multi-view disagreement is the strongest signal;
small top-1 margins and high entropy break ties. No labels are created,
promoted, or written back to the source library.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


VERSION = "label_free_review_queue_v2"


def _read_receipt(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        raise ValueError("receipt is empty")
    header = json.loads(lines[0])
    if header.get("record_type") not in {
        "slo_label_free_zero_shot_receipt",
        "slo_label_free_ensemble_receipt",
        "slo_label_free_specialist_receipt",
        "slo_label_free_specialist_ensemble_receipt",
    }:
        raise ValueError("incompatible receipt record_type")
    safety = header.get("safety") or {}
    if not safety.get("read_only") or safety.get("semantic_labels_created") or safety.get("rename_actions"):
        raise ValueError("receipt is not a read-only, label-free receipt")
    rows = [json.loads(line) for line in lines[1:]]
    if any(row.get("semantic_label") is not None for row in rows):
        raise ValueError("receipt contains semantic labels")
    return header, rows


def _priority(row: dict[str, Any], n_labels: int) -> float:
    if "model_agreement" in row:
        # Independent model disagreement is stronger evidence than a small
        # uncalibrated score margin.  Status disagreement is also useful: it
        # catches rows where one model would have passed its own gate.
        model_disagreement = 0.0 if bool(row.get("model_agreement")) else 1.0
        status_disagreement = float(row.get("model_a_status") != row.get("model_b_status"))
        margins = [float(x) for x in (row.get("model_a_margin"), row.get("model_b_margin"))
                   if isinstance(x, (int, float))]
        margin = sum(margins) / len(margins) if margins else 1.0
        margin_uncertainty = max(0.0, min(1.0, (0.08 - margin) / 0.08))
        agreements = [float(x) for x in (
            (row.get("evidence") or {}).get("model_a", {}).get("view_agreement"),
            (row.get("evidence") or {}).get("model_b", {}).get("view_agreement"),
        ) if isinstance(x, (int, float))]
        view_disagreement = 1.0 - min(agreements) if agreements else 0.0
        return (0.55 * model_disagreement + 0.20 * status_disagreement
                + 0.15 * max(0.0, min(1.0, view_disagreement))
                + 0.10 * margin_uncertainty)
    agreement = float(row.get("view_agreement", 1.0))
    margin = float(row.get("margin", 1.0))
    entropy = float(row.get("entropy", 0.0))
    disagreement = max(0.0, min(1.0, 1.0 - agreement))
    margin_uncertainty = max(0.0, min(1.0, (0.08 - margin) / 0.08))
    entropy_uncertainty = max(0.0, min(1.0, entropy / max(math.log(max(n_labels, 2)), 1e-9)))
    return 0.5 * disagreement + 0.3 * margin_uncertainty + 0.2 * entropy_uncertainty


def build_queue(receipt: Path, out: Path, limit: int = 500) -> dict[str, Any]:
    header, rows = _read_receipt(receipt)
    labels = header.get("prompt_bank") or {}
    if not labels:
        banks = header.get("specialist_prompt_banks") or {}
        labels = {label: prompts for bank in banks.values() for label, prompts in bank.items()}
    review = [row for row in rows if row.get("status") == "review" and row.get("error") is None]
    ranked = []
    for row in review:
        item = dict(row)
        item["review_priority"] = _priority(row, len(labels))
        item["review_reason"] = {
            "view_disagreement": float(1.0 - float(row.get("view_agreement", 1.0))),
            "top1_margin": float(row.get("margin", 0.0)),
            "entropy": float(row.get("entropy", 0.0)),
        }
        if "model_agreement" in row:
            evidence = row.get("evidence") or {}
            a_view = (evidence.get("model_a") or {}).get("view_agreement")
            b_view = (evidence.get("model_b") or {}).get("view_agreement")
            item["review_reason"] = {
                "model_disagreement": not bool(row.get("model_agreement")),
                "status_disagreement": row.get("model_a_status") != row.get("model_b_status"),
                "model_a_suggestion": row.get("model_a_suggestion"),
                "model_b_suggestion": row.get("model_b_suggestion"),
                "view_disagreement": 1.0 - min(
                    [float(x) for x in (a_view, b_view) if isinstance(x, (int, float))]
                    or [1.0]
                ),
                "margin_mean": row.get("margin_mean"),
            }
        elif header.get("record_type") == "slo_label_free_specialist_receipt":
            item["review_reason"] = {
                "specialist_status": row.get("specialist_status"),
                "domain": row.get("domain_suggestion"),
                "specialist_suggestion": row.get("specialist_suggestion"),
                "top1_margin": row.get("margin"),
                "entropy": row.get("entropy"),
            }
        ranked.append(item)
    ranked.sort(key=lambda row: (-row["review_priority"], row["path"]))
    if limit >= 0:
        ranked = ranked[:limit]
    payload = {
        "record_type": "slo_label_free_review_queue",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "source_receipt": str(receipt.resolve()),
        "source_method_version": header.get("method_version"),
        "n_review_candidates": len(review),
        "n_queued": len(ranked),
        "safety": {
            "read_only": True,
            "semantic_labels_created": False,
            "ground_truth_read": False,
            "rename_actions": False,
            "human_approval_required": True,
        },
        "rows": ranked,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()
    payload = build_queue(args.receipt, args.out, args.limit)
    print(json.dumps({"out": str(args.out), "n_review_candidates": payload["n_review_candidates"],
                      "n_queued": payload["n_queued"], "read_only": True}, indent=2))


if __name__ == "__main__":
    main()
