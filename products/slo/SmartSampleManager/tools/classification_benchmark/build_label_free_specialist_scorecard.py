#!/usr/bin/env python3
"""Summarise routed specialist evidence without calling it accuracy."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any


VERSION = "label_free_specialist_scorecard_v1"


def _read(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        raise ValueError("specialist receipt is empty")
    header = json.loads(lines[0])
    if header.get("record_type") not in {
        "slo_label_free_specialist_receipt",
        "slo_label_free_specialist_ensemble_receipt",
    }:
        raise ValueError("input is not a specialist receipt")
    safety = header.get("safety") or {}
    if not safety.get("read_only") or safety.get("semantic_labels_created") or safety.get("rename_actions"):
        raise ValueError("specialist receipt is not read-only")
    rows = [json.loads(line) for line in lines[1:]]
    if any(not isinstance(row, dict) or not isinstance(row.get("path"), str)
           or row.get("semantic_label") is not None for row in rows):
        raise ValueError("specialist rows are invalid or contain labels")
    return header, rows


def _median(values: list[float]) -> float | None:
    return round(float(statistics.median(values)), 6) if values else None


def build(receipt: Path, out: Path) -> dict[str, Any]:
    header, rows = _read(receipt)
    domains = sorted({str(row.get("domain_suggestion")) for row in rows
                      if row.get("domain_suggestion")})
    by_domain: dict[str, dict[str, Any]] = {}
    for domain in domains:
        selected = [row for row in rows if row.get("domain_suggestion") == domain]
        scored = [row for row in selected if row.get("specialist_status") == "scored"]
        suggest = [row for row in selected if row.get("status") == "suggest"]
        agree = [row for row in selected if row.get("specialist_model_agreement") is True]
        values = lambda key: [float(row[key]) for row in scored
                              if isinstance(row.get(key), (int, float))]
        by_domain[domain] = {
            "n_files": len(selected),
            "n_scored": len(scored),
            "n_suggest": len(suggest),
            "n_review": len(selected) - len(suggest),
            "n_model_agree": len(agree),
            "agreement_rate": round(len(agree) / len(selected), 6) if selected else 0.0,
            "suggestion_coverage": round(len(suggest) / len(selected), 6) if selected else 0.0,
            "median_score_a": _median(values("model_a_score")),
            "median_score_b": _median(values("model_b_score")),
            "median_margin_a": _median(values("model_a_margin")),
            "median_margin_b": _median(values("model_b_margin")),
            "median_view_agreement_a": _median(values("model_a_view_agreement")),
            "median_view_agreement_b": _median(values("model_b_view_agreement")),
            "evidence_quality": "two_model_agreement_signal" if agree else "single_model_or_disagreement",
        }
    payload = {
        "record_type": "slo_label_free_specialist_scorecard",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "source_receipt": str(receipt.resolve()),
        "source_method_version": header.get("method_version"),
        "n_files": len(rows),
        "domains": by_domain,
        "calibration_kind": "evidence_quality_only_no_ground_truth",
        "accuracy_claim": None,
        "auto_action_allowed": False,
        "safety": {
            "read_only": True,
            "semantic_labels_created": False,
            "ground_truth_read": False,
            "training_data_created": False,
            "rename_actions": False,
            "source_audio_modified": False,
            "human_approval_required": True,
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.receipt, args.out)
    print(json.dumps({"out": str(args.out), "n_files": result["n_files"],
                      "domains": result["domains"], "read_only": True}, indent=2))


if __name__ == "__main__":
    main()
