#!/usr/bin/env python3
"""Run a focused Audio Tips LLM audit and write a JSON report."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent.parent
ABLETON = ROOT / "studio" / "kenn" / "kenn"
DEFAULT_SUITE = ABLETON / "evals" / "questions.json"
DEFAULT_OUT = ABLETON / "artifacts" / "audits"


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def index_stats() -> dict:
    chunks_path = ABLETON / "data" / "index" / "chunks.jsonl"
    chunks = [json.loads(line) for line in chunks_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    kind_counts = Counter(str(chunk.get("kind", "manual")) for chunk in chunks)
    source_counts = Counter(str(chunk.get("source", "")) for chunk in chunks)
    return {
        "chunks": len(chunks),
        "kind_counts": dict(kind_counts),
        "unique_sources": len(source_counts),
        "notes": len(list((ABLETON / "Training_Data_Notes").glob("*.md"))),
        "pdfs": len(list((ABLETON / "Training_Data_PDF").glob("*.pdf"))),
        "avg_chunk_chars": round(sum(len(chunk.get("text", "")) for chunk in chunks) / max(1, len(chunks)), 1),
        "top_sources": [{"source": source, "chunks": count} for source, count in source_counts.most_common(10)],
    }


def gap_probe_report() -> dict:
    # See the matching note in ableton_benchmark.py: without ROOT itself on
    # sys.path, answer_payload()'s embedder silently falls back to BM25-only
    # for every question here too.
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ABLETON.parent))
    sys.path.insert(0, str(ROOT / "scripts"))
    sys.path.insert(0, str(ROOT / "scripts" / "eval"))
    from ableton_gap_report import PROBE_QUESTIONS  # noqa: E402
    from kenn.core.chat import answer_payload  # noqa: E402

    rows = []
    for question in PROBE_QUESTIONS:
        payload = answer_payload(question, allow_llm=False)
        sources = payload.get("sources") or []
        rows.append(
            {
                "question": question,
                "confidence": payload.get("confidence", "low"),
                "source_quality": payload.get("source_quality", "low"),
                "top_source": sources[0].get("label", "") if sources else "",
            }
        )
    low = [row for row in rows if row["confidence"] == "low"]
    return {
        "total": len(rows),
        "low_confidence": len(low),
        "rows": rows,
    }


def run_audit(args: argparse.Namespace) -> tuple[dict, Path]:
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "scripts"))
    sys.path.insert(0, str(ROOT / "scripts" / "eval"))
    from ableton_benchmark import run_benchmark  # noqa: E402

    args.output_dir.mkdir(parents=True, exist_ok=True)
    bench_args = SimpleNamespace(
        suite=args.suite,
        output_dir=ABLETON / "artifacts" / "benchmarks",
        limit=args.limit,
        repeat=args.repeat,
        allow_llm=args.allow_llm,
    )
    benchmark_summary, _records, benchmark_path, benchmark_jsonl = run_benchmark(bench_args)
    gaps = gap_probe_report()
    stats = index_stats()
    warnings: list[str] = []
    if benchmark_summary["failed_runs"]:
        warnings.append("benchmark_failures")
    if benchmark_summary["source_diversity_warning_runs"]:
        warnings.append("source_diversity_warnings")
    if gaps["low_confidence"]:
        warnings.append("low_confidence_gap_probes")
    if benchmark_summary["duration_ms"]["p95"] > args.p95_warn_ms:
        warnings.append("p95_latency_above_threshold")
    critical_failures = bool(benchmark_summary["failed_runs"] or gaps["low_confidence"])
    recommendations: list[str] = []
    if benchmark_summary["failed_runs"]:
        recommendations.append("Fix the failing eval cases before expanding the knowledge base.")
    if gaps["low_confidence"]:
        recommendations.append("Add or approve focused notes for low-confidence gap probes, then rebuild the index.")
    if benchmark_summary["duration_ms"]["p95"] > args.p95_warn_ms:
        recommendations.append("Optimize retrieval search/indexing before adding large PDFs; search dominates latency.")
    if benchmark_summary["source_diversity_warning_runs"]:
        recommendations.append("Review repeated or dominating source chunks; dedupe or split oversized sources.")
    if not recommendations:
        recommendations.append("Audit is clean. Add targeted PDFs/notes only for planned new topic coverage.")

    report = {
        "created_at": iso_now(),
        "suite": str(args.suite),
        "warnings": warnings,
        "recommendations": recommendations,
        "status": "fail" if critical_failures else "pass",
        "thresholds": {"p95_warn_ms": args.p95_warn_ms},
        "index": stats,
        "benchmark": {
            **benchmark_summary,
            "summary_json": str(benchmark_path),
            "jsonl_log": str(benchmark_jsonl),
        },
        "gap_probes": gaps,
    }
    report_path = args.output_dir / f"ableton_audit_{utc_stamp()}.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report, report_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a full Audio Tips LLM audit.")
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE, help="Question suite JSON.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT, help="Directory for audit reports.")
    parser.add_argument("--limit", type=int, default=8, help="Retrieval source limit.")
    parser.add_argument("--repeat", type=int, default=1, help="Benchmark repetitions.")
    parser.add_argument("--allow-llm", action="store_true", help="Allow optional rewrite model.")
    parser.add_argument("--p95-warn-ms", type=float, default=2500.0, help="Warn if benchmark p95 latency exceeds this.")
    args = parser.parse_args()

    report, path = run_audit(args)
    print(f"Audit status: {report['status']}")
    print(f"Warnings: {report['warnings'] or 'none'}")
    print(
        "Benchmark: "
        f"{report['benchmark']['passed_runs']}/{report['benchmark']['total_runs']} passed · "
        f"p95 {report['benchmark']['duration_ms']['p95']} ms · "
        f"source warnings {report['benchmark']['source_diversity_warning_runs']}"
    )
    print(f"Gap probes: {report['gap_probes']['low_confidence']} low of {report['gap_probes']['total']}")
    print(f"Audit JSON: {path}")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
