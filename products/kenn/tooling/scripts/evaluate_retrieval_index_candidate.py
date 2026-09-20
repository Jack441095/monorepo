#!/usr/bin/env python3
"""Shadow-evaluate a staged index without changing any live retrieval pointer."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "backend" / "src"))

from kenn.core.chat_retrieval import display_results  # noqa: E402
from kenn.core.retrieval_index_candidate import inspect_candidate  # noqa: E402
from kenn.core.retrieval_index_shadow import candidate_search, load_candidate_bundle  # noqa: E402
from kenn.core.manual_grounding_evaluation import REFERENCE_CASES, evaluate_cases  # noqa: E402


SCHEMA = "kenn.retrieval_index_candidate_shadow_evaluation.v1"
UNSUPPORTED_QUERY = "What does the official Ableton manual say about taxes?"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--expected-manual-sha256", required=True)
    parser.add_argument("--expected-manual-filename", default="live12-manual-en.pdf")
    args = parser.parse_args()
    preflight = inspect_candidate(
        args.candidate_root,
        expected_manual_sha256=args.expected_manual_sha256,
        expected_manual_filename=args.expected_manual_filename,
    )
    report: dict = {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "preflight": preflight,
        "live_index_modified": False,
    }
    if not preflight["promotion_eligible"]:
        report.update({"status": "preflight_rejected", "all_checks_passed": False})
        print(json.dumps(report, indent=2, sort_keys=True))
        return 1

    chunks, terms = load_candidate_bundle(args.candidate_root)
    evaluation = evaluate_cases(
        REFERENCE_CASES,
        search_fn=lambda query: candidate_search(query, chunks, terms, limit=8),
        display_fn=lambda query, results: display_results(query, results, 3),
    )
    unsupported_results = display_results(
        UNSUPPORTED_QUERY,
        candidate_search(UNSUPPORTED_QUERY, chunks, terms, limit=8),
        3,
    )
    unsupported = {
        "query": UNSUPPORTED_QUERY,
        "selected_count": len(unsupported_results),
        "passed": not unsupported_results,
    }
    report.update(
        {
            "status": "evaluated",
            "manual_grounding": evaluation,
            "unsupported_official_request": unsupported,
            "all_checks_passed": bool(evaluation["all_cases_passed"] and unsupported["passed"]),
            "limitations": [
                "This is a BM25-only shadow evaluation of the staged artifacts; it does not evaluate live latency, generated answer quality, or execution safety.",
                "The command is read-only and never promotes or reloads a live retrieval index.",
            ],
        }
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["all_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
