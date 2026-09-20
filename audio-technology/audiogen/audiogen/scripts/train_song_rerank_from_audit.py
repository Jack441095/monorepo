#!/usr/bin/env python3
"""Train Phase B ridge song reranker from ``run_summary.csv`` (batch note audit output)."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from composition.song_rerank_model import evaluate_model, fit_ridge_regressor


def _load_run_summary(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(dict(row))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Fit ridge rerank model from audit run_summary.csv")
    ap.add_argument(
        "audit_dir",
        help="Directory containing run_summary.csv (e.g. full_song_seed_audit_YYYYMMDD_HHMMSS)",
    )
    ap.add_argument(
        "--output",
        default="artifacts/song_rerank/rerank_v1.json",
        help="Output JSON model path",
    )
    ap.add_argument("--ridge-lambda", type=float, default=2.0)
    ap.add_argument("--holdout-frac", type=float, default=0.2, help="Fraction of rows for eval only")
    args = ap.parse_args()

    audit_dir = Path(str(args.audit_dir)).expanduser()
    summary = audit_dir / "run_summary.csv"
    if not summary.is_file():
        alt = list(audit_dir.glob("**/run_summary.csv"))
        if not alt:
            print(f"Missing run_summary.csv under {audit_dir}", file=sys.stderr)
            return 2
        summary = alt[0]

    rows = _load_run_summary(summary)
    if len(rows) < 12:
        print(f"Too few rows ({len(rows)}) in {summary}", file=sys.stderr)
        return 2

    holdout_n = max(1, int(round(len(rows) * float(args.holdout_frac))))
    train_rows = rows[:-holdout_n] if holdout_n < len(rows) else rows
    eval_rows = rows[-holdout_n:] if holdout_n < len(rows) else []

    model = fit_ridge_regressor(train_rows, ridge_lambda=float(args.ridge_lambda))
    out = Path(str(args.output)).expanduser()
    model.save(out)

    train_metrics = evaluate_model(model, train_rows)
    eval_metrics = evaluate_model(model, eval_rows) if eval_rows else {"n": 0.0, "mae": 0.0, "corr": 0.0}
    report = {
        "audit_summary": str(summary),
        "train_rows": len(train_rows),
        "eval_rows": len(eval_rows),
        "train": train_metrics,
        "eval": eval_metrics,
        "model_path": str(out),
    }
    report_path = out.with_suffix(".train_report.json")
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"wrote {out}")
    print(f"wrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
