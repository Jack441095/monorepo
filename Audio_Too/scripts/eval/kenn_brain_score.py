#!/usr/bin/env python3
"""Score KENN's answer quality across routing, grounding, refusal, and follow-up behavior."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
BENCHMARK_DIR = ROOT / "studio" / "kenn" / "kenn" / "artifacts" / "benchmarks"


def latest_json(directory: Path, pattern: str, required_key: str) -> dict[str, Any] | None:
    paths = sorted(directory.glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and required_key in data:
            data = dict(data)
            data["path"] = str(path)
            return data
    return None


def ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def clamp_score(value: float) -> float:
    return max(0.0, min(100.0, value))


def benchmark_scores(summary: dict[str, Any] | None) -> dict[str, Any]:
    if not summary:
        return {
            "overall": 0.0,
            "routing_judgment": 0.0,
            "grounding": 0.0,
            "answer_quality": 0.0,
            "latency": 0.0,
            "notes": ["no benchmark summary found"],
        }
    total = int(summary.get("total_runs") or 0)
    passed = int(summary.get("passed_runs") or 0)
    pass_score = 100.0 * ratio(passed, total)
    category_rates = summary.get("case_category_pass_rates") if isinstance(summary.get("case_category_pass_rates"), dict) else {}
    hard_categories = ["adversarial", "ambiguity", "business", "refusal"]
    hard_rates = [float(category_rates.get(category, 0) or 0) * 100 for category in hard_categories]
    routing_score = sum(hard_rates) / len(hard_rates) if hard_rates else 0.0
    source_warnings = int(summary.get("source_diversity_warning_runs") or 0)
    source_quality = summary.get("source_quality_counts") if isinstance(summary.get("source_quality_counts"), dict) else {}
    high_source_rate = 100.0 * ratio(float(source_quality.get("high", 0) or 0), total)
    warning_penalty = 100.0 * ratio(source_warnings, total)
    grounding_score = clamp_score(high_source_rate - warning_penalty)
    quality = summary.get("answer_quality_score") if isinstance(summary.get("answer_quality_score"), dict) else {}
    answer_quality_score = float(quality.get("mean", 0) or 0)
    duration = summary.get("duration_ms") if isinstance(summary.get("duration_ms"), dict) else {}
    p95 = float(duration.get("p95", 0) or 0)
    latency_score = clamp_score(100.0 - max(0.0, p95 - 500.0) / 20.0)
    return {
        "overall": round(pass_score, 2),
        "routing_judgment": round(routing_score, 2),
        "grounding": round(grounding_score, 2),
        "answer_quality": round(answer_quality_score, 2),
        "latency": round(latency_score, 2),
        "benchmark": {
            "path": summary.get("path", ""),
            "passed": passed,
            "total": total,
            "p95_ms": p95,
            "source_warnings": source_warnings,
            "category_rates": category_rates,
        },
        "notes": [],
    }


def probe_scores(probe: dict[str, Any] | None) -> dict[str, Any]:
    if not probe:
        return {
            "tester_realism": 0.0,
            "followup_memory": 0.0,
            "refusal_boundary": 0.0,
            "probe": {},
            "notes": ["no tester probe summary found"],
        }
    rows = probe.get("rows") if isinstance(probe.get("rows"), list) else []
    total = int(probe.get("total") or len(rows))
    passed = int(probe.get("passed") or 0)
    followups = [row for row in rows if "followup" in str(row.get("id", "")) or str(row.get("question", "")).lower() == "what should i do next?"]
    refusals = [row for row in rows if str(row.get("expected_confidence", "")).lower() == "low"]
    return {
        "tester_realism": round(100.0 * ratio(passed, total), 2),
        "followup_memory": round(100.0 * ratio(sum(1 for row in followups if row.get("ok")), len(followups)), 2),
        "refusal_boundary": round(100.0 * ratio(sum(1 for row in refusals if row.get("ok")), len(refusals)), 2),
        "probe": {
            "path": probe.get("path", ""),
            "passed": passed,
            "total": total,
            "followup_cases": len(followups),
            "refusal_cases": len(refusals),
        },
        "notes": [],
    }


def weighted_score(scores: dict[str, float]) -> float:
    weights = {
        "overall": 0.22,
        "routing_judgment": 0.18,
        "grounding": 0.18,
        "tester_realism": 0.14,
        "followup_memory": 0.10,
        "refusal_boundary": 0.10,
        "latency": 0.08,
    }
    return round(sum(float(scores.get(key, 0) or 0) * weight for key, weight in weights.items()), 2)


def recommendations(scores: dict[str, float]) -> list[str]:
    items: list[str] = []
    if scores.get("routing_judgment", 0) < 95:
        items.append("Add or review route-memory labels for hard/refusal/business cases.")
    if scores.get("grounding", 0) < 95:
        items.append("Review source labels and export hard negatives for bad top-source matches.")
    if scores.get("followup_memory", 0) < 95:
        items.append("Add follow-up evals with realistic conversation history.")
    if scores.get("refusal_boundary", 0) < 95:
        items.append("Add boundary prompts for legal, tax, exact-price, and unsupported-shortcut pressure.")
    if scores.get("tester_realism", 0) < 95:
        items.append("Promote failed tester probes into the canonical eval suite.")
    return items or ["Current brain score is strong; next gains should come from harder real-user cases and reranker labels."]


def build_scorecard(benchmark_dir: Path = BENCHMARK_DIR) -> dict[str, Any]:
    benchmark = latest_json(benchmark_dir, "ableton_benchmark_*.json", "total_runs")
    probe = latest_json(benchmark_dir, "kenn_tester_probe_*.json", "rows")
    b_scores = benchmark_scores(benchmark)
    p_scores = probe_scores(probe)
    dimensions = {
        "overall": b_scores["overall"],
        "routing_judgment": b_scores["routing_judgment"],
        "grounding": b_scores["grounding"],
        "answer_quality": b_scores["answer_quality"],
        "latency": b_scores["latency"],
        "tester_realism": p_scores["tester_realism"],
        "followup_memory": p_scores["followup_memory"],
        "refusal_boundary": p_scores["refusal_boundary"],
    }
    return {
        "ok": bool(benchmark and probe),
        "brain_score": weighted_score(dimensions),
        "dimensions": dimensions,
        "benchmark": b_scores.get("benchmark", {}),
        "probe": p_scores.get("probe", {}),
        "recommendations": recommendations(dimensions),
        "notes": [*b_scores.get("notes", []), *p_scores.get("notes", [])],
    }


def print_text(report: dict[str, Any]) -> None:
    print(f"KENN brain score: {report.get('brain_score', 0)}/100")
    for key, value in report.get("dimensions", {}).items():
        print(f"  - {key}: {value}")
    for item in report.get("recommendations") or []:
        print(f"Next: {item}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Score KENN brain quality from latest benchmark and tester probe.")
    parser.add_argument("--dir", type=Path, default=BENCHMARK_DIR, help="Benchmark artifact directory.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()
    report = build_scorecard(args.dir)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_text(report)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
