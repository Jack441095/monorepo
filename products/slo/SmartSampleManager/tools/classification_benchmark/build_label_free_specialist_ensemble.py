#!/usr/bin/env python3
"""Combine two routed specialist receipts into a conservative agreement gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


VERSION = "label_free_specialist_ensemble_v1"


def _read(path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        raise ValueError("specialist receipt is empty")
    header = json.loads(lines[0])
    if header.get("record_type") != "slo_label_free_specialist_receipt":
        raise ValueError("input is not a specialist receipt")
    safety = header.get("safety") or {}
    if not safety.get("read_only") or safety.get("semantic_labels_created") or safety.get("rename_actions"):
        raise ValueError("specialist receipt is not read-only")
    rows: dict[str, dict[str, Any]] = {}
    for line in lines[1:]:
        row = json.loads(line)
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            raise ValueError("specialist row has no path")
        if row["path"] in rows:
            raise ValueError(f"duplicate specialist path: {row['path']}")
        if row.get("semantic_label") is not None:
            raise ValueError("specialist receipt contains semantic labels")
        rows[row["path"]] = row
    return header, rows


def _score(row: dict[str, Any]) -> float | None:
    value = row.get("specialist_score")
    return float(value) if isinstance(value, (int, float)) else None


def build(model_a: Path, model_b: Path, out: Path,
          min_view_agreement: float = 0.67) -> dict[str, Any]:
    if not 0.0 <= min_view_agreement <= 1.0:
        raise ValueError("min_view_agreement must be between zero and one")
    header_a, rows_a = _read(model_a)
    header_b, rows_b = _read(model_b)
    paths = sorted(set(rows_a) | set(rows_b))
    rows: list[dict[str, Any]] = []
    for path in paths:
        a, b = rows_a.get(path), rows_b.get(path)
        domain_a = a.get("domain_suggestion") if a else None
        domain_b = b.get("domain_suggestion") if b else None
        domain = domain_a if domain_a == domain_b else None
        suggestion_a = a.get("specialist_suggestion") if a else None
        suggestion_b = b.get("specialist_suggestion") if b else None
        same_label = bool(suggestion_a and suggestion_a == suggestion_b and domain is not None)
        a_pass = bool(a and a.get("status") == "suggest" and a.get("specialist_status") == "scored")
        b_pass = bool(b and b.get("status") == "suggest" and b.get("specialist_status") == "scored")
        a_view = float(a.get("view_agreement", 0.0)) if a else 0.0
        b_view = float(b.get("view_agreement", 0.0)) if b else 0.0
        both_view_ok = a_view >= min_view_agreement and b_view >= min_view_agreement
        accepted = same_label and a_pass and b_pass and both_view_ok
        score_a, score_b = _score(a or {}), _score(b or {})
        consensus_score = min(score_a, score_b) if accepted and score_a is not None and score_b is not None else None
        rows.append({
            "path": path,
            "domain_suggestion": domain,
            "specialist_status": "scored" if a and b and a.get("specialist_status") == "scored" and b.get("specialist_status") == "scored" else "not_dispatched",
            "status": "suggest" if accepted else "review",
            "semantic_label": None,
            "specialist_suggestion": suggestion_a if accepted else None,
            "specialist_score": consensus_score,
            "specialist_alternatives": (a.get("specialist_alternatives", []) if a else [])[:3],
            "specialist_model_agreement": same_label,
            "model_a_suggestion": suggestion_a,
            "model_b_suggestion": suggestion_b,
            "model_a_score": score_a,
            "model_b_score": score_b,
            "model_a_margin": a.get("margin") if a else None,
            "model_b_margin": b.get("margin") if b else None,
            "model_a_status": a.get("status") if a else "missing",
            "model_b_status": b.get("status") if b else "missing",
            "model_a_view_agreement": a_view if a else None,
            "model_b_view_agreement": b_view if b else None,
            "calibration": "uncalibrated_specialist_model_agreement",
        })
    header = {
        "record_type": "slo_label_free_specialist_ensemble_receipt",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "model_a_receipt": str(model_a.resolve()),
        "model_b_receipt": str(model_b.resolve()),
        "model_a": header_a.get("model"),
        "model_b": header_b.get("model"),
        "n_files": len(rows),
        "n_suggest": sum(row["status"] == "suggest" for row in rows),
        "n_review": sum(row["status"] == "review" for row in rows),
        "n_agree": sum(row["specialist_model_agreement"] for row in rows),
        "min_view_agreement": min_view_agreement,
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
    parser.add_argument("--model-a", type=Path, required=True)
    parser.add_argument("--model-b", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--min-view-agreement", type=float, default=0.67)
    args = parser.parse_args()
    result = build(args.model_a, args.model_b, args.out, args.min_view_agreement)
    print(json.dumps({"out": str(args.out), "n_files": result["n_files"],
                      "n_suggest": result["n_suggest"], "n_agree": result["n_agree"],
                      "read_only": True}, indent=2))


if __name__ == "__main__":
    main()
