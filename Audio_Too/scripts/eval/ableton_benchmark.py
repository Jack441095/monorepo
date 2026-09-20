#!/usr/bin/env python3
"""Benchmark Audio Tips LLM answer generation and write JSON logs."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
ABLETON = ROOT / "studio" / "kenn" / "kenn"
DEFAULT_SUITE = ABLETON / "evals" / "questions.json"
DEFAULT_OUT = ABLETON / "artifacts" / "benchmarks"


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_suite(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data.get("cases")
    if not isinstance(cases, list):
        raise ValueError(f"Benchmark suite must contain a cases list: {path}")
    return cases


def percentile(values: list[float], percent: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * percent))
    return ordered[index]


def source_diversity(payload: dict) -> dict:
    sources = payload.get("sources") or []
    labels = [str(source.get("label", "")) for source in sources]
    source_keys = [
        f"{source.get('kind', '')}:{source.get('source', '')}:{source.get('page', '')}"
        for source in sources
    ]
    warnings: list[str] = []
    if len(labels) > 1 and len(set(labels)) < len(labels):
        warnings.append("duplicate_source_labels")
    if len(source_keys) > 1 and len(set(source_keys)) < len(source_keys):
        warnings.append("duplicate_source_chunks")
    if len(sources) >= 3 and len({source.get("source", "") for source in sources}) == 1:
        warnings.append("single_source_dominates")
    return {
        "unique_labels": len(set(labels)),
        "unique_source_chunks": len(set(source_keys)),
        "warnings": warnings,
    }


def summarize(records: list[dict], *, suite: Path, limit: int, repeat: int, allow_llm: bool) -> dict:
    durations = [float(record["duration_ms"]) for record in records]
    eval_failures = [record for record in records if record["eval_failures"]]
    diversity_warnings = [record for record in records if record["source_diversity"]["warnings"]]
    confidence_counts: dict[str, int] = {}
    source_quality_counts: dict[str, int] = {}
    route_counts: dict[str, int] = {}
    intent_counts: dict[str, int] = {}
    answer_mode_counts: dict[str, int] = {}
    case_category_counts: dict[str, int] = {}
    case_category_failures: dict[str, int] = {}
    case_tag_counts: dict[str, int] = {}
    grounding_mode_counts: dict[str, int] = {}
    quality_scores: list[float] = []
    timing_components: dict[str, list[float]] = {}
    required_facts = 0
    covered_facts = 0
    citation_expectations = 0
    matched_citations = 0
    citations = 0
    structurally_valid_citations = 0
    forbidden_claim_hits = 0
    critical_forbidden_claim_hits = 0
    abstention_cases = 0
    correct_abstentions = 0
    retrieval_failures = 0
    generation_failures = 0
    answer_lengths: list[int] = []
    for record in records:
        confidence_counts[record["confidence"]] = confidence_counts.get(record["confidence"], 0) + 1
        source_quality_counts[record["source_quality"]] = source_quality_counts.get(record["source_quality"], 0) + 1
        route_counts[record.get("route", "unknown")] = route_counts.get(record.get("route", "unknown"), 0) + 1
        intent_counts[record.get("intent", "unknown")] = intent_counts.get(record.get("intent", "unknown"), 0) + 1
        answer_mode_counts[record.get("answer_mode", "unknown")] = answer_mode_counts.get(record.get("answer_mode", "unknown"), 0) + 1
        category = str(record.get("category") or "standard")
        case_category_counts[category] = case_category_counts.get(category, 0) + 1
        if record["eval_failures"]:
            case_category_failures[category] = case_category_failures.get(category, 0) + 1
        for tag in record.get("case_tags") or []:
            tag_key = str(tag)
            case_tag_counts[tag_key] = case_tag_counts.get(tag_key, 0) + 1
        grounding_mode = str(record.get("grounding_mode") or "unknown")
        grounding_mode_counts[grounding_mode] = grounding_mode_counts.get(grounding_mode, 0) + 1
        if record.get("answer_quality_score") is not None:
            quality_scores.append(float(record.get("answer_quality_score") or 0))
        for key, value in dict(record.get("timings_ms") or {}).items():
            timing_components.setdefault(key, []).append(float(value or 0))
        dimensions = dict(record.get("evaluation_dimensions") or {})
        required_facts += int(dimensions.get("required_fact_count") or 0)
        covered_facts += int(dimensions.get("required_fact_covered") or 0)
        citation_expectations += int(dimensions.get("citation_expectation_count") or 0)
        matched_citations += int(dimensions.get("citation_expectation_matched") or 0)
        citations += int(dimensions.get("citation_count") or 0)
        structurally_valid_citations += int(
            dimensions.get("structurally_valid_citations") or 0
        )
        forbidden_claim_hits += len(dimensions.get("forbidden_claim_hits") or [])
        critical_forbidden_claim_hits += len(
            dimensions.get("critical_forbidden_claim_hits") or []
        )
        if dimensions.get("abstention_required"):
            abstention_cases += 1
            correct_abstentions += int(bool(dimensions.get("abstention_correct")))
        retrieval_failures += int(not bool(dimensions.get("retrieval_ok", True)))
        generation_failures += int(not bool(dimensions.get("generation_ok", True)))
        answer_lengths.append(int(record.get("answer_chars") or 0))

    return {
        "created_at": iso_now(),
        "suite": str(suite),
        "limit": limit,
        "repeat": repeat,
        "allow_llm": allow_llm,
        "total_runs": len(records),
        "unique_questions": len({record["question"] for record in records}),
        "passed_runs": len(records) - len(eval_failures),
        "failed_runs": len(eval_failures),
        "source_diversity_warning_runs": len(diversity_warnings),
        "grounding_contract": {
            "required_fact_coverage": round(covered_facts / required_facts, 4) if required_facts else 1.0,
            "required_facts_covered": covered_facts,
            "required_facts_total": required_facts,
            "citation_validity": (
                round(structurally_valid_citations / citations, 4)
                if citations
                else 1.0
            ),
            "structurally_valid_citations": structurally_valid_citations,
            "citations_total": citations,
            "expected_source_recall_at_k": (
                round(matched_citations / citation_expectations, 4)
                if citation_expectations
                else 1.0
            ),
            "citation_expectations_matched": matched_citations,
            "citation_expectations_total": citation_expectations,
            "forbidden_claim_hits": forbidden_claim_hits,
            "critical_unsupported_claims": critical_forbidden_claim_hits,
            "abstention_precision": (
                round(correct_abstentions / abstention_cases, 4) if abstention_cases else 1.0
            ),
            "correct_abstentions": correct_abstentions,
            "abstention_cases": abstention_cases,
            "retrieval_failure_runs": retrieval_failures,
            "generation_failure_runs": generation_failures,
            "answer_chars": {
                "mean": round(statistics.fmean(answer_lengths), 2) if answer_lengths else 0,
                "p95": round(percentile(answer_lengths, 0.95), 2),
                "max": max(answer_lengths) if answer_lengths else 0,
            },
        },
        "duration_ms": {
            "min": round(min(durations), 2) if durations else 0,
            "mean": round(statistics.fmean(durations), 2) if durations else 0,
            "median": round(statistics.median(durations), 2) if durations else 0,
            "p95": round(percentile(durations, 0.95), 2),
            "max": round(max(durations), 2) if durations else 0,
        },
        "confidence_counts": confidence_counts,
        "source_quality_counts": source_quality_counts,
        "route_counts": route_counts,
        "intent_counts": intent_counts,
        "answer_mode_counts": answer_mode_counts,
        "case_category_counts": case_category_counts,
        "case_category_failures": case_category_failures,
        "case_category_pass_rates": {
            category: round(
                (case_category_counts[category] - case_category_failures.get(category, 0))
                / max(1, case_category_counts[category]),
                4,
            )
            for category in sorted(case_category_counts)
        },
        "case_tag_counts": case_tag_counts,
        "grounding_mode_counts": grounding_mode_counts,
        "answer_quality_score": {
            "mean": round(statistics.fmean(quality_scores), 2) if quality_scores else 0,
            "p95": round(percentile(quality_scores, 0.95), 2),
            "min": round(min(quality_scores), 2) if quality_scores else 0,
        },
        "timing_components_ms": {
            key: {
                "mean": round(statistics.fmean(values), 2) if values else 0,
                "p95": round(percentile(values, 0.95), 2),
                "max": round(max(values), 2) if values else 0,
            }
            for key, values in sorted(timing_components.items())
        },
        "slowest_runs": [
            {
                "id": record["id"],
                "question": record["question"],
                "duration_ms": record["duration_ms"],
                "timings_ms": record.get("timings_ms", {}),
                "confidence": record["confidence"],
                "source_quality": record["source_quality"],
            }
            for record in sorted(records, key=lambda item: float(item["duration_ms"]), reverse=True)[:8]
        ],
        "failures": [
            {
                "id": record["id"],
                "question": record["question"],
                "eval_failures": record["eval_failures"],
            }
            for record in eval_failures
        ],
        "source_diversity_warnings": [
            {
                "id": record["id"],
                "question": record["question"],
                "warnings": record["source_diversity"]["warnings"],
                "source_labels": record["source_labels"],
            }
            for record in diversity_warnings
        ],
    }


def run_benchmark(args: argparse.Namespace) -> tuple[dict, list[dict], Path, Path]:
    # Found 2026-07-12: without ROOT itself on sys.path, `import audio_too`
    # (the top-level package kenn.core.chat's embedder and ableton_bridge's
    # audiogen_bridge both need) failed on every single query, silently
    # degrading semantic retrieval to BM25-only for the entire benchmark run
    # -- the benchmark still "passed" with misleadingly good-looking numbers
    # while never actually exercising the embedding path it's meant to
    # measure.
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ABLETON.parent))
    sys.path.insert(0, str(ROOT / "scripts"))
    sys.path.insert(0, str(ROOT / "scripts" / "eval"))
    from ableton_eval import evaluate_case, evaluation_dimensions, validate_suite  # noqa: E402
    from kenn.core.chat import answer_payload, warm_index  # noqa: E402
    from kenn.training.training_records import answer_record, write_jsonl  # noqa: E402

    cases = load_suite(args.suite)
    validate_suite(cases)
    warm_index()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = utc_stamp()
    summary_path = args.output_dir / f"ableton_benchmark_{stamp}.json"
    jsonl_path = args.output_dir / f"ableton_benchmark_{stamp}.jsonl"
    training_jsonl_path = args.output_dir / f"kenn_answer_records_{stamp}.jsonl"

    records: list[dict] = []
    training_records: list[dict] = []
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for iteration in range(1, args.repeat + 1):
            for case in cases:
                question = str(case.get("question", "")).strip()
                if not question:
                    continue
                started = time.perf_counter()
                payload = answer_payload(
                    question,
                    limit=args.limit,
                    allow_llm=args.allow_llm,
                    profile=True,
                )
                diversity = source_diversity(payload)
                duration_ms = (time.perf_counter() - started) * 1000
                eval_failures = evaluate_case(case, payload)
                dimensions = evaluation_dimensions(case, payload)
                record = {
                    "created_at": iso_now(),
                    "iteration": iteration,
                    "id": case.get("id") or question,
                    "question": question,
                    "duration_ms": round(duration_ms, 2),
                    "confidence": payload.get("confidence", "unknown"),
                    "source_quality": payload.get("source_quality", "unknown"),
                    "route": payload.get("route", "unknown"),
                    "intent": payload.get("intent", "unknown"),
                    "answer_mode": payload.get("answer_mode", "unknown"),
                    "category": case.get("category", "standard"),
                    "case_tags": list(case.get("tags") or []),
                    "answer_quality_score": (
                        payload.get("answer_quality", {}).get("score")
                        if isinstance(payload.get("answer_quality"), dict)
                        else None
                    ),
                    "answer_quality_warnings": (
                        payload.get("answer_quality", {}).get("warnings", [])
                        if isinstance(payload.get("answer_quality"), dict)
                        else []
                    ),
                    "intent_guard": payload.get("intent_guard", "unknown"),
                    "grounding_mode": payload.get("grounding_mode", "unknown"),
                    "grounding_score": (
                        payload.get("grounding", {}).get("score")
                        if isinstance(payload.get("grounding"), dict)
                        else None
                    ),
                    "weak_match": bool(payload.get("weak_match")),
                    "topics": payload.get("topics", []),
                    "source_count": len(payload.get("sources") or []),
                    "source_labels": [source.get("label") for source in payload.get("sources") or []],
                    "source_diversity": diversity,
                    "answer_chars": len(str(payload.get("answer") or "")),
                    "llm_enhanced": bool(payload.get("llm_enhanced")),
                    "timings_ms": payload.get("timings_ms", {}),
                    "index_cache": payload.get("index_cache", {}),
                    "eval_failures": eval_failures,
                    "evaluation_dimensions": dimensions,
                }
                training_records.append(answer_record(case, payload, eval_failures))
                records.append(record)
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    summary = summarize(records, suite=args.suite, limit=args.limit, repeat=args.repeat, allow_llm=args.allow_llm)
    summary["jsonl_log"] = str(jsonl_path)
    summary["training_jsonl"] = str(write_jsonl(training_jsonl_path, training_records))
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary, records, summary_path, jsonl_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark Audio Tips LLM answer generation.")
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE, help="Question suite JSON.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT, help="Directory for JSON logs.")
    parser.add_argument("--limit", type=int, default=8, help="Retrieval source limit.")
    parser.add_argument("--repeat", type=int, default=1, help="Run each question this many times.")
    parser.add_argument("--allow-llm", action="store_true", help="Allow optional cloud/local rewrite if configured.")
    args = parser.parse_args()

    summary, _records, summary_path, jsonl_path = run_benchmark(args)
    print(f"Benchmark runs: {summary['total_runs']} ({summary['passed_runs']} passed, {summary['failed_runs']} failed)")
    print(
        "Latency ms: "
        f"mean {summary['duration_ms']['mean']} · "
        f"median {summary['duration_ms']['median']} · "
        f"p95 {summary['duration_ms']['p95']} · "
        f"max {summary['duration_ms']['max']}"
    )
    print(f"Confidence: {summary['confidence_counts']}")
    print(f"Source quality: {summary['source_quality_counts']}")
    print(f"Source diversity warnings: {summary['source_diversity_warning_runs']}")
    print(f"Summary JSON: {summary_path}")
    print(f"Per-question JSONL: {jsonl_path}")
    return 0 if summary["failed_runs"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
