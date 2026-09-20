#!/usr/bin/env python3
"""Rank real KENN knowledge gaps and recheck them against the current index."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
KENN_PARENT = ROOT / "studio" / "kenn"
APP = ROOT / "business" / "app"
for value in (ROOT, KENN_PARENT, APP):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

from kenn.adaptive.gap_clustering import cluster_queries, fetch_query_signals  # noqa: E402


def _recheck(question: str) -> dict[str, Any]:
    from kenn.core.chat import answer_payload

    payload = answer_payload(question, limit=8, allow_llm=False)
    sources = payload.get("sources") or []
    has_note = any(str(source.get("kind", "")) == "note" for source in sources)
    confidence = str(payload.get("confidence", "low")).lower()
    resolved = confidence in {"medium", "high"} and has_note and not payload.get("weak_match")
    return {
        "resolved_now": resolved,
        "confidence_now": confidence,
        "weak_match_now": bool(payload.get("weak_match")),
        "top_source_now": str(sources[0].get("label", "")) if sources else "",
        "route_now": str(payload.get("route", "")),
    }


def is_synthetic_question(question: str) -> bool:
    normalized = re.sub(r"\W+", " ", question.lower()).strip()
    return bool(re.search(r"\b(test|pytest|fixture|dedupe|dummy|placeholder)\b", normalized))


def build_report(*, recheck: bool = True, limit: int = 100, include_synthetic: bool = False) -> dict[str, Any]:
    all_signals = fetch_query_signals()
    synthetic = [item for item in all_signals if is_synthetic_question(item["question"])]
    signals = [item for item in all_signals if include_synthetic or not is_synthetic_question(item["question"])][: max(1, limit)]
    if recheck and signals:
        from kenn.core.chat import warm_index

        warm_index()
    rows: list[dict[str, Any]] = []
    for signal in signals:
        row = dict(signal)
        if recheck:
            row.update(_recheck(row["question"]))
        else:
            row.update({"resolved_now": False, "confidence_now": "unchecked", "weak_match_now": None, "top_source_now": "", "route_now": ""})
        row["priority_score"] = (
            int(row["severity"]) * 3
            + int(math.log2(int(row["occurrences"]) + 1)) * 4
            + len(row["sources"]) * 4
            + (0 if row["resolved_now"] else 5)
        )
        rows.append(row)
    rows.sort(key=lambda item: (-item["priority_score"], item["normalized"]))

    unresolved = [row for row in rows if not row["resolved_now"]]
    clusters_raw = cluster_queries([row["question"] for row in unresolved]) if len(unresolved) >= 3 else {}
    clusters = []
    by_question = {row["question"]: row for row in unresolved}
    for cluster_id, questions in clusters_raw.items():
        clusters.append(
            {
                "cluster_id": cluster_id,
                "questions": questions,
                "priority_score": sum(by_question[q]["priority_score"] for q in questions),
                "occurrences": sum(by_question[q]["occurrences"] for q in questions),
            }
        )
    clusters.sort(key=lambda item: (-item["priority_score"], -item["occurrences"]))
    return {
        "schema": "kenn.knowledge_gap_report.v1",
        "summary": {
            "signals": len(rows),
            "resolved_since_capture": sum(1 for row in rows if row["resolved_now"]),
            "open_ranked_gaps": len(unresolved),
            "clusters": len(clusters),
            "synthetic_rows_excluded": 0 if include_synthetic else len(synthetic),
        },
        "clusters": clusters,
        "gaps": rows,
    }


def _slug(question: str) -> str:
    """Turn a question into a kebab-case filename hint."""
    slug = re.sub(r"[^\w\s-]", "", question.lower())
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")
    # Drop common filler words at the front
    slug = re.sub(r"^(how-do-i|what-is|why-does|when-should|can-i|should-i|which)-", "", slug)
    return slug[:60]


def _source_badge(sources: list[str]) -> str:
    priority = {"benchmark_failures": "⛔ eval-fail", "knowledge_upgrade_cases": "📋 planned", "demo_feedback": "👥 feedback", "unknown_route_sessions": "❓ unrouted", "kenn_sessions": "🔁 repeat"}
    labels = [priority.get(s, s) for s in sources]
    return " + ".join(labels)


def print_report(report: dict[str, Any], *, suggest: bool = False) -> None:
    summary = report["summary"]
    open_gaps = [item for item in report["gaps"] if not item["resolved_now"]]
    resolved = summary["resolved_since_capture"]
    total = summary["signals"]

    print(f"\nKENN gap report  •  {open_gaps and len(open_gaps) or 0} open / {total} signals")
    print(f"  ✅ {resolved} resolved  •  🚫 {summary['synthetic_rows_excluded']} synthetic excluded")
    if summary["clusters"]:
        print(f"  🔗 {summary['clusters']} topic clusters")
    print()

    if not open_gaps:
        print("  No open gaps — KENN is fully covering all tracked questions.")
        return

    print("  Open gaps (highest priority first):\n")
    for index, row in enumerate(open_gaps, start=1):
        badge = _source_badge(row["sources"])
        print(f"  {index:>2}. [{badge}]  (score {row['priority_score']}, {row['occurrences']}x asked)")
        print(f"      Q: {row['question']}")
        if suggest:
            slug = _slug(row["question"])
            print(f"      → draft note: {slug}.md")
        print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rank real KENN knowledge gaps from logs and feedback.")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--no-recheck", action="store_true", help="Do not query the current KENN index.")
    parser.add_argument("--include-synthetic", action="store_true", help="Include obvious test/fixture questions.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--suggest", action="store_true", help="Show suggested draft note filenames for each open gap")
    args = parser.parse_args(argv)
    report = build_report(recheck=not args.no_recheck, limit=args.limit, include_synthetic=args.include_synthetic)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_report(report, suggest=args.suggest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
