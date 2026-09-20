#!/usr/bin/env python3
"""Fail CI/operator checks when the latest KENN benchmark regresses."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_BENCHMARK_DIR = ROOT / "studio" / "kenn" / "kenn" / "artifacts" / "benchmarks"
REQUIRED_CATEGORIES = ("adversarial", "ambiguity", "business", "refusal")


def latest_summary(
    directory: Path, require_categories: tuple[str, ...] = ()
) -> dict[str, Any] | None:
    paths = sorted(directory.glob("ableton_benchmark_*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        category_counts = data.get("case_category_counts") if isinstance(data, dict) else {}
        if not isinstance(category_counts, dict):
            category_counts = {}
        if require_categories and not all(
            int(category_counts.get(category) or 0) > 0 for category in require_categories
        ):
            continue
        if isinstance(data, dict) and "total_runs" in data:
            data = dict(data)
            data["path"] = str(path)
            return data
    return None


def pass_rate(summary: dict[str, Any]) -> float:
    total = int(summary.get("total_runs") or 0)
    passed = int(summary.get("passed_runs") or 0)
    return passed / total if total else 0.0


def evaluate_gate(
    summary: dict[str, Any] | None,
    *,
    min_pass_rate: float,
    max_p95_ms: float,
    max_source_warnings: int,
    require_categories: tuple[str, ...],
    min_unique_questions: int,
    min_citation_validity: float,
    min_required_fact_coverage: float,
    min_abstention_precision: float,
    max_critical_unsupported_claims: int,
) -> dict[str, Any]:
    if summary is None:
        return {"ok": False, "failures": ["no benchmark summary found"], "summary": {}}
    failures: list[str] = []
    duration = summary.get("duration_ms") if isinstance(summary.get("duration_ms"), dict) else {}
    p95 = float(duration.get("p95", 0) or 0)
    current_pass_rate = pass_rate(summary)
    source_warnings = int(summary.get("source_diversity_warning_runs") or 0)
    category_rates = summary.get("case_category_pass_rates")
    if not isinstance(category_rates, dict):
        category_rates = {}
    category_counts = summary.get("case_category_counts")
    if not isinstance(category_counts, dict):
        category_counts = {}
    grounding = summary.get("grounding_contract")
    if not isinstance(grounding, dict):
        grounding = {}
    unique_questions = int(summary.get("unique_questions") or 0)
    citation_validity = float(grounding.get("citation_validity", 0) or 0)
    fact_coverage = float(grounding.get("required_fact_coverage", 0) or 0)
    abstention_precision = float(grounding.get("abstention_precision", 0) or 0)
    unsupported_claims = int(grounding.get("critical_unsupported_claims") or 0)

    if current_pass_rate < min_pass_rate:
        failures.append(f"pass_rate {current_pass_rate:.2%} below {min_pass_rate:.2%}")
    if p95 > max_p95_ms:
        failures.append(f"p95 latency {p95:.2f} ms above {max_p95_ms:.2f} ms")
    if source_warnings > max_source_warnings:
        failures.append(f"source diversity warnings {source_warnings} above {max_source_warnings}")
    if unique_questions < min_unique_questions:
        failures.append(f"unique questions {unique_questions} below {min_unique_questions}")
    if citation_validity < min_citation_validity:
        failures.append(
            f"citation validity {citation_validity:.2%} below {min_citation_validity:.2%}"
        )
    if fact_coverage < min_required_fact_coverage:
        failures.append(
            f"required-fact coverage {fact_coverage:.2%} below {min_required_fact_coverage:.2%}"
        )
    if abstention_precision < min_abstention_precision:
        failures.append(
            f"abstention precision {abstention_precision:.2%} below {min_abstention_precision:.2%}"
        )
    if unsupported_claims > max_critical_unsupported_claims:
        failures.append(
            f"critical unsupported claims {unsupported_claims} above {max_critical_unsupported_claims}"
        )
    for category in require_categories:
        count = int(category_counts.get(category) or 0)
        rate = float(category_rates.get(category, 0) or 0)
        if count <= 0:
            failures.append(f"required category {category!r} has no runs")
        elif rate < min_pass_rate:
            failures.append(f"category {category!r} pass rate {rate:.2%} below {min_pass_rate:.2%}")

    return {
        "ok": not failures,
        "failures": failures,
        "thresholds": {
            "min_pass_rate": min_pass_rate,
            "max_p95_ms": max_p95_ms,
            "max_source_warnings": max_source_warnings,
            "require_categories": list(require_categories),
            "min_unique_questions": min_unique_questions,
            "min_citation_validity": min_citation_validity,
            "min_required_fact_coverage": min_required_fact_coverage,
            "min_abstention_precision": min_abstention_precision,
            "max_critical_unsupported_claims": max_critical_unsupported_claims,
        },
        "summary": {
            "path": summary.get("path", ""),
            "total_runs": int(summary.get("total_runs") or 0),
            "passed_runs": int(summary.get("passed_runs") or 0),
            "failed_runs": int(summary.get("failed_runs") or 0),
            "pass_rate": round(current_pass_rate, 4),
            "p95_ms": p95,
            "source_diversity_warning_runs": source_warnings,
            "case_category_counts": category_counts,
            "case_category_pass_rates": category_rates,
            "unique_questions": unique_questions,
            "grounding_contract": grounding,
        },
    }


def print_text(report: dict[str, Any]) -> None:
    summary = report.get("summary") or {}
    status = "pass" if report.get("ok") else "fail"
    print(f"Benchmark gate: {status}")
    if summary:
        print(
            f"Latest: {summary.get('passed_runs', 0)}/{summary.get('total_runs', 0)} passed · "
            f"p95 {summary.get('p95_ms', 0)} ms · "
            f"source warnings {summary.get('source_diversity_warning_runs', 0)}"
        )
        if summary.get("path"):
            print(f"Summary JSON: {summary['path']}")
    for failure in report.get("failures") or []:
        print(f"FAIL: {failure}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Gate the latest KENN benchmark summary.")
    parser.add_argument("--dir", type=Path, default=DEFAULT_BENCHMARK_DIR, help="Benchmark artifact directory.")
    parser.add_argument("--min-pass-rate", type=float, default=1.0, help="Required overall/category pass rate.")
    parser.add_argument("--max-p95-ms", type=float, default=2500.0, help="Maximum allowed p95 latency.")
    parser.add_argument("--max-source-warnings", type=int, default=0, help="Maximum source diversity warning runs.")
    parser.add_argument("--min-unique-questions", type=int, default=100)
    parser.add_argument("--min-citation-validity", type=float, default=0.95)
    parser.add_argument("--min-required-fact-coverage", type=float, default=0.90)
    parser.add_argument("--min-abstention-precision", type=float, default=0.90)
    parser.add_argument("--max-critical-unsupported-claims", type=int, default=0)
    parser.add_argument(
        "--require-category",
        action="append",
        default=list(REQUIRED_CATEGORIES),
        help="Required benchmark category. Can be passed more than once.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    categories = tuple(dict.fromkeys(str(item) for item in args.require_category if str(item).strip()))
    report = evaluate_gate(
        latest_summary(args.dir, categories),
        min_pass_rate=args.min_pass_rate,
        max_p95_ms=args.max_p95_ms,
        max_source_warnings=args.max_source_warnings,
        require_categories=categories,
        min_unique_questions=args.min_unique_questions,
        min_citation_validity=args.min_citation_validity,
        min_required_fact_coverage=args.min_required_fact_coverage,
        min_abstention_precision=args.min_abstention_precision,
        max_critical_unsupported_claims=args.max_critical_unsupported_claims,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_text(report)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
