#!/usr/bin/env python3
"""Mine KENN source near-misses for human hard-negative review."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
BENCHMARK_DIR = ROOT / "studio" / "kenn" / "kenn" / "artifacts" / "benchmarks"
TRAINING_DIR = ROOT / "studio" / "kenn" / "kenn" / "artifacts" / "training"
DEFAULT_OUTPUT = TRAINING_DIR / "kenn_hard_negative_candidates.jsonl"
WORD_RE = re.compile(r"[a-z0-9]+")

sys.path.insert(0, str(ROOT / "studio" / "kenn"))
from kenn.training.training_records import read_jsonl, write_jsonl  # noqa: E402


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def latest_jsonl(directory: Path, pattern: str) -> Path | None:
    paths = sorted(directory.glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
    return paths[0] if paths else None


def tokens(text: str) -> set[str]:
    return {token for token in WORD_RE.findall(str(text).lower()) if len(token) > 2}


def overlap_score(question: str, source_label: str, topics: list[str]) -> float:
    query_terms = tokens(question)
    source_terms = tokens(source_label)
    topic_terms = {part for topic in topics for part in tokens(str(topic).replace("_", " "))}
    if not query_terms:
        return 0.0
    lexical = len(query_terms & source_terms) / max(1, len(query_terms))
    topic = len(topic_terms & source_terms) / max(1, len(topic_terms)) if topic_terms else 0.0
    return round((lexical * 0.7) + (topic * 0.3), 4)


def mine_candidates(records: list[dict[str, Any]], *, min_score: float = 0.18, limit: int = 100) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for record in records:
        if record.get("eval_failures"):
            continue
        question = str(record.get("question") or "")
        case_id = str(record.get("id") or record.get("case_id") or question)
        labels = [str(label) for label in record.get("source_labels") or [] if str(label)]
        if len(labels) < 2:
            continue
        topics = [str(topic) for topic in record.get("topics") or []]
        positive = labels[0]
        positive_score = overlap_score(question, positive, topics)
        for rank, label in enumerate(labels[1:5], start=2):
            key = (case_id, label)
            if key in seen:
                continue
            seen.add(key)
            score = overlap_score(question, label, topics)
            if score < min_score and positive_score >= score:
                continue
            candidates.append(
                {
                    "schema": "kenn.hard_negative_candidate.v1",
                    "created_at": iso_now(),
                    "case_id": case_id,
                    "question": question,
                    "route": record.get("route", ""),
                    "intent": record.get("intent", ""),
                    "topics": topics,
                    "positive_source_label": positive,
                    "candidate_source_label": label,
                    "candidate_rank": rank,
                    "candidate_overlap_score": score,
                    "positive_overlap_score": positive_score,
                    "reason": "near-miss lower-ranked source; review before exporting as hard negative",
                    "review_decision": "pending",
                }
            )
    candidates.sort(
        key=lambda item: (
            -float(item["candidate_overlap_score"]),
            float(item["candidate_rank"]),
            str(item["case_id"]),
        )
    )
    return candidates[: max(1, limit)]


def mine(
    *,
    benchmark_jsonl: Path | None = None,
    output: Path = DEFAULT_OUTPUT,
    min_score: float = 0.18,
    limit: int = 100,
    write: bool = True,
) -> dict[str, Any]:
    source = benchmark_jsonl or latest_jsonl(BENCHMARK_DIR, "ableton_benchmark_*.jsonl")
    records = read_jsonl(source)
    candidates = mine_candidates(records, min_score=min_score, limit=limit)
    output_path = ""
    if write:
        output_path = str(write_jsonl(output, candidates, sort_keys=True))
    return {
        "ok": source is not None,
        "source_benchmark_jsonl": str(source or ""),
        "output": output_path,
        "records": len(records),
        "candidates": len(candidates),
        "min_score": min_score,
        "items": candidates,
    }


def print_text(report: dict[str, Any]) -> None:
    print(f"Hard-negative candidates: {report.get('candidates', 0)}")
    print(f"Source: {report.get('source_benchmark_jsonl', '')}")
    if report.get("output"):
        print(f"Output: {report['output']}")
    for item in report.get("items", [])[:8]:
        print(
            f"  - {item.get('case_id')}: rank {item.get('candidate_rank')} "
            f"score {item.get('candidate_overlap_score')} -> {item.get('candidate_source_label')}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Mine near-miss source candidates for hard-negative review.")
    parser.add_argument("--benchmark-jsonl", type=Path, default=None, help="Benchmark JSONL to mine.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Candidate JSONL output.")
    parser.add_argument("--min-score", type=float, default=0.18, help="Minimum overlap score for a candidate.")
    parser.add_argument("--limit", type=int, default=100, help="Maximum candidates to write.")
    parser.add_argument("--no-write", action="store_true", help="Preview only.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = mine(
        benchmark_jsonl=args.benchmark_jsonl,
        output=args.output,
        min_score=args.min_score,
        limit=args.limit,
        write=not args.no_write,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_text(report)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
