#!/usr/bin/env python3
"""Export KENN source-ranking examples for future reranker/Torch experiments."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
BENCHMARK_DIR = ROOT / "studio" / "kenn" / "kenn" / "artifacts" / "benchmarks"
TRAINING_DIR = ROOT / "studio" / "kenn" / "kenn" / "artifacts" / "training"
DEFAULT_OUTPUT = TRAINING_DIR / "kenn_reranker_pairs.jsonl"
DEFAULT_MANIFEST = TRAINING_DIR / "kenn_reranker_manifest.json"
HARD_NEGATIVES = TRAINING_DIR / "kenn_hard_negatives.jsonl"
CURATED_HARD_NEGATIVES = ROOT / "studio" / "kenn" / "kenn" / "evals" / "curated_hard_negatives.jsonl"

sys.path.insert(0, str(ROOT / "studio" / "kenn"))
from kenn.training.training_records import read_jsonl, write_jsonl  # noqa: E402


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def latest_jsonl(directory: Path, pattern: str) -> Path | None:
    paths = sorted(directory.glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
    return paths[0] if paths else None


def pair_id(case_id: str, label: int, rank: int, source_label: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in source_label).strip("-")[:80]
    return f"{case_id}:{label}:{rank}:{safe}"


def examples_from_records(records: list[dict[str, Any]], hard_negatives: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        case_id = str(record.get("id") or record.get("case_id") or "")
        question = str(record.get("question") or "")
        if not question:
            continue
        source_labels = [str(label) for label in record.get("source_labels") or [] if str(label)]
        source_kinds = [str(kind) for kind in record.get("source_kinds") or []]
        eval_passed = not bool(record.get("eval_failures"))
        if eval_passed and source_labels:
            key = pair_id(case_id, 1, 1, source_labels[0])
            if key not in seen:
                rows.append(
                    {
                        "schema": "kenn.reranker_pair.v1",
                        "id": key,
                        "case_id": case_id,
                        "question": question,
                        "source_label": source_labels[0],
                        "source_kind": source_kinds[0] if source_kinds else "",
                        "rank": 1,
                        "label": 1,
                        "reason": "top source on passing eval",
                        "route": record.get("route", ""),
                        "intent": record.get("intent", ""),
                        "topics": record.get("topics", []),
                    }
                )
                seen.add(key)
        for index, label in enumerate(source_labels[1:5], start=2):
            key = pair_id(case_id, 0, index, label)
            if key in seen:
                continue
            rows.append(
                {
                    "schema": "kenn.reranker_pair.v1",
                    "id": key,
                    "case_id": case_id,
                    "question": question,
                    "source_label": label,
                    "source_kind": source_kinds[index - 1] if index - 1 < len(source_kinds) else "",
                    "rank": index,
                    "label": 0,
                    "reason": "lower-ranked candidate",
                    "route": record.get("route", ""),
                    "intent": record.get("intent", ""),
                    "topics": record.get("topics", []),
                }
            )
            seen.add(key)
    for negative in hard_negatives:
        question = str(negative.get("question") or "")
        label = str(negative.get("negative_source_label") or negative.get("negative_source") or "")
        case_id = str(negative.get("case_id") or "")
        if not question or not label:
            continue
        key = pair_id(case_id, 0, 0, label)
        if key in seen:
            continue
        rows.append(
            {
                "schema": "kenn.reranker_pair.v1",
                "id": key,
                "case_id": case_id,
                "question": question,
                "source_label": label,
                "source_kind": negative.get("negative_source_kind", ""),
                "rank": 0,
                "label": 0,
                "reason": negative.get("reason", "reviewed hard negative"),
                "route": negative.get("route", ""),
                "intent": negative.get("intent", ""),
                "topics": negative.get("topics", []),
            }
        )
        seen.add(key)
    return rows


def torch_guidance(pair_count: int, positive_count: int, negative_count: int) -> dict[str, Any]:
    enough_data = pair_count >= 200 and positive_count >= 50 and negative_count >= 50
    return {
        "torch_benefit": "yes_later" if enough_data else "not_yet",
        "recommendation": (
            "Use Torch for a small cross-encoder or pairwise reranker experiment."
            if enough_data
            else "Keep collecting labels first; a rule-based reranker is easier to debug at this size."
        ),
        "minimum_target": {
            "pairs": 200,
            "positive": 50,
            "negative": 50,
        },
    }


def export_dataset(
    *,
    benchmark_jsonl: Path | None = None,
    hard_negatives_path: Path = HARD_NEGATIVES,
    curated_hard_negatives_path: Path = CURATED_HARD_NEGATIVES,
    output: Path = DEFAULT_OUTPUT,
    manifest_path: Path = DEFAULT_MANIFEST,
) -> dict[str, Any]:
    source_path = benchmark_jsonl or latest_jsonl(BENCHMARK_DIR, "ableton_benchmark_*.jsonl")
    records = read_jsonl(source_path)
    negatives = [*read_jsonl(hard_negatives_path), *read_jsonl(curated_hard_negatives_path)]
    pairs = examples_from_records(records, negatives)
    write_jsonl(output, pairs, sort_keys=True)
    positive = sum(1 for row in pairs if row.get("label") == 1)
    negative = sum(1 for row in pairs if row.get("label") == 0)
    manifest = {
        "schema": "kenn.reranker_manifest.v1",
        "created_at": iso_now(),
        "source_benchmark_jsonl": str(source_path or ""),
        "hard_negatives_path": str(hard_negatives_path),
        "curated_hard_negatives_path": str(curated_hard_negatives_path),
        "output": str(output),
        "pairs": len(pairs),
        "positive": positive,
        "negative": negative,
        "torch": torch_guidance(len(pairs), positive, negative),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def print_text(manifest: dict[str, Any]) -> None:
    print(f"Reranker pairs: {manifest.get('pairs', 0)}")
    print(f"Positive: {manifest.get('positive', 0)} - Negative: {manifest.get('negative', 0)}")
    print(f"Output: {manifest.get('output', '')}")
    torch = manifest.get("torch") or {}
    print(f"Torch: {torch.get('torch_benefit', 'unknown')} - {torch.get('recommendation', '')}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Export KENN reranker training pairs.")
    parser.add_argument("--benchmark-jsonl", type=Path, default=None, help="Benchmark JSONL to convert.")
    parser.add_argument("--hard-negatives", type=Path, default=HARD_NEGATIVES, help="Hard negative JSONL.")
    parser.add_argument(
        "--curated-hard-negatives",
        type=Path,
        default=CURATED_HARD_NEGATIVES,
        help="Tracked curated hard negative JSONL.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output pair JSONL.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="Output manifest JSON.")
    parser.add_argument("--json", action="store_true", help="Print manifest JSON.")
    args = parser.parse_args()
    manifest = export_dataset(
        benchmark_jsonl=args.benchmark_jsonl,
        hard_negatives_path=args.hard_negatives,
        curated_hard_negatives_path=args.curated_hard_negatives,
        output=args.output,
        manifest_path=args.manifest,
    )
    if args.json:
        print(json.dumps(manifest, indent=2, sort_keys=True))
    else:
        print_text(manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
