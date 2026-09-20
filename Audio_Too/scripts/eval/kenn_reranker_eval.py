#!/usr/bin/env python3
"""Evaluate an offline KENN reranker model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kenn_reranker_train import DEFAULT_DATASET, DEFAULT_METRICS, DEFAULT_MODEL, evaluate, read_jsonl


def load_model(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_model(*, dataset: Path = DEFAULT_DATASET, model_path: Path = DEFAULT_MODEL, output: Path = DEFAULT_METRICS) -> dict:
    rows = read_jsonl(dataset)
    model = load_model(model_path)
    weights = [float(value) for value in model.get("weights") or []]
    metrics = {
        "schema": "kenn.reranker_eval.v1",
        "dataset": str(dataset),
        "model": str(model_path),
        "backend": model.get("backend", "unknown"),
        "total_rows": len(rows),
        "all": evaluate(rows, weights),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return metrics


def print_metrics(metrics: dict) -> None:
    all_metrics = metrics.get("all") or {}
    ranking = all_metrics.get("ranking") or {}
    print(f"Reranker eval backend: {metrics.get('backend', 'unknown')}")
    print(f"Rows: {metrics.get('total_rows', 0)}")
    print(
        "All data: "
        f"accuracy {all_metrics.get('accuracy', 0)} - auc {all_metrics.get('auc', 0)} - "
        f"top1 {ranking.get('top1', 0)} - mrr {ranking.get('mrr', 0)} - "
        f"top1_delta {all_metrics.get('top1_delta', 0)}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate an offline KENN reranker model.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--output", type=Path, default=DEFAULT_METRICS)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    metrics = evaluate_model(dataset=args.dataset, model_path=args.model, output=args.output)
    if args.json:
        print(json.dumps(metrics, indent=2, sort_keys=True))
    else:
        print_metrics(metrics)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
