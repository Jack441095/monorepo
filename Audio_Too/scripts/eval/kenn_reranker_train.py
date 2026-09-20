#!/usr/bin/env python3
"""Train an offline KENN source reranker experiment."""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
TRAINING_DIR = ROOT / "studio" / "kenn" / "kenn" / "artifacts" / "training"
DEFAULT_DATASET = TRAINING_DIR / "kenn_reranker_pairs.jsonl"
DEFAULT_MODEL = TRAINING_DIR / "kenn_reranker_model.json"
DEFAULT_METRICS = TRAINING_DIR / "kenn_reranker_metrics.json"
WORD_RE = re.compile(r"[a-z0-9]+")

sys.path.insert(0, str(ROOT / "studio" / "kenn"))
from kenn.training.training_records import read_jsonl  # noqa: E402


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def tokens(text: str) -> set[str]:
    return {token for token in WORD_RE.findall(str(text).lower()) if len(token) > 2}


def features(row: dict[str, Any]) -> list[float]:
    question = tokens(str(row.get("question") or ""))
    source = tokens(str(row.get("source_label") or ""))
    topics = {str(topic).replace("_", " ").lower() for topic in row.get("topics") or []}
    overlap = len(question & source)
    union = len(question | source)
    rank = float(row.get("rank") or 0)
    source_label = str(row.get("source_label") or "").lower()
    source_kind = str(row.get("source_kind") or "").lower()
    return [
        1.0,
        overlap / max(1, len(question)),
        overlap / max(1, union),
        1.0 / max(1.0, rank) if rank > 0 else 0.0,
        1.0 if ".md" in source_label else 0.0,
        1.0 if "pdf" in source_label else 0.0,
        1.0 if source_kind == "note" else 0.0,
        1.0 if any(topic and topic in source_label for topic in topics) else 0.0,
        min(1.0, len(source) / 12.0),
    ]


def label(row: dict[str, Any]) -> int:
    return 1 if int(row.get("label") or 0) == 1 else 0


def split_by_case(rows: list[dict[str, Any]], validation_ratio: float, seed: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_case[str(row.get("case_id") or row.get("question") or row.get("id"))].append(row)
    cases = sorted(by_case)
    rng = random.Random(seed)
    rng.shuffle(cases)
    validation_count = max(1, round(len(cases) * validation_ratio)) if len(cases) > 1 else 0
    validation_cases = set(cases[:validation_count])
    train: list[dict[str, Any]] = []
    validation: list[dict[str, Any]] = []
    for case_id, case_rows in by_case.items():
        if case_id in validation_cases:
            validation.extend(case_rows)
        else:
            train.extend(case_rows)
    return train, validation


def sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


def score(weights: list[float], row: dict[str, Any]) -> float:
    return sigmoid(sum(weight * value for weight, value in zip(weights, features(row))))


def train_linear(rows: list[dict[str, Any]], *, epochs: int, lr: float, l2: float) -> list[float]:
    if not rows:
        return [0.0] * len(features({}))
    weights = [0.0] * len(features(rows[0]))
    for _ in range(max(1, epochs)):
        for row in rows:
            xs = features(row)
            error = score(weights, row) - label(row)
            for index, value in enumerate(xs):
                weights[index] -= lr * (error * value + l2 * weights[index])
    return weights


def try_train_torch(rows: list[dict[str, Any]], *, epochs: int, lr: float, l2: float) -> tuple[list[float], str]:
    try:
        import torch
    except ModuleNotFoundError:
        raise
    if not rows:
        return [0.0] * len(features({})), ""
    xs = torch.tensor([features(row) for row in rows], dtype=torch.float32)
    ys = torch.tensor([[float(label(row))] for row in rows], dtype=torch.float32)
    model = torch.nn.Linear(xs.shape[1], 1)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=l2)
    loss_fn = torch.nn.BCEWithLogitsLoss()
    for _ in range(max(1, epochs)):
        optimizer.zero_grad()
        loss = loss_fn(model(xs), ys)
        loss.backward()
        optimizer.step()
    with torch.no_grad():
        weight_values = model.weight.detach().reshape(-1).tolist()
        bias = float(model.bias.detach().reshape(-1)[0])
    return [bias + float(weight_values[0]), *[float(value) for value in weight_values[1:]]], "torch"


def auc(rows: list[dict[str, Any]], weights: list[float]) -> float:
    positives = [score(weights, row) for row in rows if label(row) == 1]
    negatives = [score(weights, row) for row in rows if label(row) == 0]
    if not positives or not negatives:
        return 0.0
    wins = 0.0
    total = 0
    for pos in positives:
        for neg in negatives:
            total += 1
            if pos > neg:
                wins += 1
            elif pos == neg:
                wins += 0.5
    return wins / max(1, total)


def ranking_metrics(rows: list[dict[str, Any]], weights: list[float]) -> dict[str, float]:
    by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_case[str(row.get("case_id") or row.get("question") or row.get("id"))].append(row)
    top1 = 0
    mrr_total = 0.0
    cases = 0
    for case_rows in by_case.values():
        if not any(label(row) == 1 for row in case_rows):
            continue
        ranked = sorted(case_rows, key=lambda row: score(weights, row), reverse=True)
        cases += 1
        if label(ranked[0]) == 1:
            top1 += 1
        for index, row in enumerate(ranked, start=1):
            if label(row) == 1:
                mrr_total += 1.0 / index
                break
    return {
        "cases": float(cases),
        "top1": round(top1 / max(1, cases), 4),
        "mrr": round(mrr_total / max(1, cases), 4),
    }


def baseline_rank_metrics(rows: list[dict[str, Any]]) -> dict[str, float]:
    by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_case[str(row.get("case_id") or row.get("question") or row.get("id"))].append(row)
    top1 = 0
    mrr_total = 0.0
    cases = 0
    for case_rows in by_case.values():
        if not any(label(row) == 1 for row in case_rows):
            continue
        ranked = sorted(case_rows, key=lambda row: float(row.get("rank") or 999999))
        cases += 1
        if label(ranked[0]) == 1:
            top1 += 1
        for index, row in enumerate(ranked, start=1):
            if label(row) == 1:
                mrr_total += 1.0 / index
                break
    return {
        "cases": float(cases),
        "top1": round(top1 / max(1, cases), 4),
        "mrr": round(mrr_total / max(1, cases), 4),
    }


def evaluate(rows: list[dict[str, Any]], weights: list[float]) -> dict[str, Any]:
    predictions = [(score(weights, row), label(row)) for row in rows]
    correct = sum(1 for value, expected in predictions if (value >= 0.5) == bool(expected))
    positives = sum(1 for _, expected in predictions if expected == 1)
    negatives = len(predictions) - positives
    model_ranking = ranking_metrics(rows, weights)
    baseline_ranking = baseline_rank_metrics(rows)
    return {
        "rows": len(rows),
        "positive": positives,
        "negative": negatives,
        "accuracy": round(correct / max(1, len(predictions)), 4),
        "auc": round(auc(rows, weights), 4),
        "ranking": model_ranking,
        "baseline_rank": baseline_ranking,
        "top1_delta": round(model_ranking["top1"] - baseline_ranking["top1"], 4),
        "mrr_delta": round(model_ranking["mrr"] - baseline_ranking["mrr"], 4),
    }


def train_model(
    *,
    dataset: Path = DEFAULT_DATASET,
    output: Path = DEFAULT_MODEL,
    metrics_path: Path = DEFAULT_METRICS,
    backend: str = "auto",
    epochs: int = 80,
    lr: float = 0.08,
    l2: float = 0.001,
    validation_ratio: float = 0.2,
    seed: int = 7,
) -> dict[str, Any]:
    rows = read_jsonl(dataset)
    train_rows, validation_rows = split_by_case(rows, validation_ratio, seed)
    selected_backend = backend
    torch_error = ""
    if backend in {"auto", "torch"}:
        try:
            weights, selected_backend = try_train_torch(train_rows, epochs=epochs, lr=lr, l2=l2)
        except ModuleNotFoundError as exc:
            if backend == "torch":
                raise
            torch_error = str(exc)
            selected_backend = "linear"
            weights = train_linear(train_rows, epochs=epochs, lr=lr, l2=l2)
    else:
        selected_backend = "linear"
        weights = train_linear(train_rows, epochs=epochs, lr=lr, l2=l2)
    output.parent.mkdir(parents=True, exist_ok=True)
    model = {
        "schema": "kenn.reranker_model.v1",
        "created_at": iso_now(),
        "backend": selected_backend,
        "dataset": str(dataset),
        "feature_names": [
            "bias",
            "query_source_overlap",
            "query_source_jaccard",
            "inverse_rank",
            "is_markdown_note",
            "is_pdf",
            "kind_note",
            "topic_in_source",
            "source_token_density",
        ],
        "weights": weights,
    }
    output.write_text(json.dumps(model, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    metrics = {
        "schema": "kenn.reranker_metrics.v1",
        "created_at": iso_now(),
        "backend": selected_backend,
        "torch_unavailable": bool(torch_error),
        "torch_error": torch_error,
        "dataset": str(dataset),
        "model": str(output),
        "total_rows": len(rows),
        "train": evaluate(train_rows, weights),
        "validation": evaluate(validation_rows, weights),
    }
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return metrics


def print_metrics(metrics: dict[str, Any]) -> None:
    validation = metrics.get("validation") or {}
    ranking = validation.get("ranking") or {}
    print(f"Reranker train backend: {metrics.get('backend', 'unknown')}")
    if metrics.get("torch_unavailable"):
        print("Torch unavailable; trained pure-Python linear baseline.")
    print(f"Rows: {metrics.get('total_rows', 0)}")
    print(
        "Validation: "
        f"accuracy {validation.get('accuracy', 0)} - auc {validation.get('auc', 0)} - "
        f"top1 {ranking.get('top1', 0)} - mrr {ranking.get('mrr', 0)} - "
        f"top1_delta {validation.get('top1_delta', 0)}"
    )
    print(f"Model: {metrics.get('model', '')}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Train an offline KENN reranker experiment.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET, help="Reranker pair JSONL.")
    parser.add_argument("--output", type=Path, default=DEFAULT_MODEL, help="Output model JSON.")
    parser.add_argument("--metrics", type=Path, default=DEFAULT_METRICS, help="Output metrics JSON.")
    parser.add_argument("--backend", choices=["auto", "linear", "torch"], default="auto")
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--lr", type=float, default=0.08)
    parser.add_argument("--l2", type=float, default=0.001)
    parser.add_argument("--validation-ratio", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        metrics = train_model(
            dataset=args.dataset,
            output=args.output,
            metrics_path=args.metrics,
            backend=args.backend,
            epochs=args.epochs,
            lr=args.lr,
            l2=args.l2,
            validation_ratio=args.validation_ratio,
            seed=args.seed,
        )
    except ModuleNotFoundError as exc:
        print(f"Torch backend requested but unavailable: {exc}")
        return 1
    if args.json:
        print(json.dumps(metrics, indent=2, sort_keys=True))
    else:
        print_metrics(metrics)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
