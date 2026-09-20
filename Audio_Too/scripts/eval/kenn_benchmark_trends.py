#!/usr/bin/env python3
"""Summarize KENN benchmark history for long-term quality tracking."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_BENCHMARK_DIR = ROOT / "studio" / "kenn" / "kenn" / "artifacts" / "benchmarks"


def load_summaries(directory: Path, *, limit: int = 12) -> list[dict[str, Any]]:
    paths = sorted(directory.glob("ableton_benchmark_*.json"), key=lambda path: path.stat().st_mtime)
    summaries: list[dict[str, Any]] = []
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or "total_runs" not in data:
            continue
        data = dict(data)
        data["path"] = str(path)
        summaries.append(data)
    return summaries[-max(1, limit) :]


def pass_rate(summary: dict[str, Any]) -> float:
    total = int(summary.get("total_runs") or 0)
    passed = int(summary.get("passed_runs") or 0)
    return round(passed / total, 4) if total else 0.0


def _duration(summary: dict[str, Any], key: str) -> float:
    duration = summary.get("duration_ms") if isinstance(summary.get("duration_ms"), dict) else {}
    return float(duration.get(key, 0) or 0)


def summarize_trends(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    if not summaries:
        return {"ok": False, "error": "No benchmark summaries found.", "runs": []}
    first = summaries[0]
    latest = summaries[-1]
    latest_categories = latest.get("case_category_pass_rates")
    if not isinstance(latest_categories, dict):
        latest_categories = {}
    latest_category_counts = latest.get("case_category_counts")
    if not isinstance(latest_category_counts, dict):
        latest_category_counts = {}
    return {
        "ok": True,
        "count": len(summaries),
        "first": {
            "created_at": first.get("created_at", ""),
            "path": first.get("path", ""),
            "pass_rate": pass_rate(first),
            "p95_ms": _duration(first, "p95"),
            "total_runs": int(first.get("total_runs") or 0),
        },
        "latest": {
            "created_at": latest.get("created_at", ""),
            "path": latest.get("path", ""),
            "pass_rate": pass_rate(latest),
            "p95_ms": _duration(latest, "p95"),
            "mean_ms": _duration(latest, "mean"),
            "total_runs": int(latest.get("total_runs") or 0),
            "failed_runs": int(latest.get("failed_runs") or 0),
            "category_counts": latest_category_counts,
            "category_pass_rates": latest_categories,
            "grounding_mode_counts": latest.get("grounding_mode_counts", {}),
            "source_diversity_warning_runs": int(latest.get("source_diversity_warning_runs") or 0),
        },
        "delta": {
            "pass_rate": round(pass_rate(latest) - pass_rate(first), 4),
            "p95_ms": round(_duration(latest, "p95") - _duration(first, "p95"), 2),
            "total_runs": int(latest.get("total_runs") or 0) - int(first.get("total_runs") or 0),
        },
        "runs": [
            {
                "created_at": item.get("created_at", ""),
                "pass_rate": pass_rate(item),
                "p95_ms": _duration(item, "p95"),
                "failed_runs": int(item.get("failed_runs") or 0),
                "total_runs": int(item.get("total_runs") or 0),
                "path": item.get("path", ""),
            }
            for item in summaries
        ],
    }


def print_text(report: dict[str, Any]) -> None:
    if not report.get("ok"):
        print(report.get("error", "No benchmark trend data."))
        return
    latest = report["latest"]
    delta = report["delta"]
    print(f"KENN benchmark trend: {report['count']} run(s)")
    print(
        "Latest: "
        f"{latest['total_runs']} runs, pass rate {latest['pass_rate']:.2%}, "
        f"p95 {latest['p95_ms']} ms, failures {latest['failed_runs']}"
    )
    print(f"Delta from first: pass rate {delta['pass_rate']:+.2%}, p95 {delta['p95_ms']:+.2f} ms")
    categories = latest.get("category_pass_rates") or {}
    if categories:
        print("Category pass rates:")
        for category, rate in sorted(categories.items()):
            count = (latest.get("category_counts") or {}).get(category, 0)
            print(f"  - {category}: {float(rate):.2%} ({count} run(s))")
    print(f"Latest summary: {latest['path']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize KENN benchmark trend artifacts.")
    parser.add_argument("--dir", type=Path, default=DEFAULT_BENCHMARK_DIR, help="Benchmark artifact directory.")
    parser.add_argument("--limit", type=int, default=12, help="Number of recent summaries to compare.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    report = summarize_trends(load_summaries(args.dir, limit=args.limit))
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_text(report)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
