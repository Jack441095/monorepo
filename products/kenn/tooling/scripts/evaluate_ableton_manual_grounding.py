#!/usr/bin/env python3
"""Evaluate whether explicit official-reference queries select local manual evidence.

The evaluator never downloads or reads a manual outside KENN's active local
index. It is intentionally non-qualifying until an authorized local manual
has been indexed with ``./ableton build --include-local-manuals``.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "backend" / "src"))

from kenn.core.manual_grounding_evaluation import REFERENCE_CASES, SCHEMA, evaluate_cases


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-manual", action="store_true",
        help="Return nonzero when no official local manual is present in the active index.",
    )
    args = parser.parse_args()

    from kenn.core.chat_retrieval import display_results, load_chunks, load_terms, search

    chunks = load_chunks()
    manual_count = sum(
        str(chunk.get("evidence_class") or "") == "official_ableton_manual"
        for chunk in chunks
    )
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "official_manual_chunk_count": manual_count,
    }
    if not manual_count:
        report.update({
            "status": "manual_not_indexed",
            "all_cases_passed": False,
            "next_step": "Place an authorized local Live manual in Training_Data_PDF and run ./ableton build --include-local-manuals.",
        })
        print(json.dumps(report, indent=2, sort_keys=True))
        return 2 if args.require_manual else 0

    terms = load_terms()
    evaluated = evaluate_cases(
        REFERENCE_CASES,
        search_fn=lambda query: search(query, chunks, terms, limit=8),
        display_fn=lambda query, results: display_results(query, results, 3),
    )
    report.update(evaluated)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["all_cases_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
