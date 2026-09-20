#!/usr/bin/env python3
"""Evaluate the repository's 128-case chat question corpus.

This is automated fixture evidence only. It checks answer terms, forbidden
claims, confidence, source provenance, and abstention fields where present;
it does not replace independent human technical review.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages" / "chat"))
sys.path.insert(0, str(REPO_ROOT / "apps" / "backend" / "src"))
import app  # noqa: E402
from kenn.core.chat_routing import business_pricing_query  # noqa: E402


CONFIDENCE = {"none": 0, "low": 1, "medium": 2, "high": 3}
QUALITY = {"none": 0, "low": 1, "medium": 2, "high": 3}
ENGINE_ONLY_ASSERTIONS = ("grounding_mode", "min_grounding_score", "min_answer_quality")


def _expects_public_abstention(case: dict) -> bool:
    case_id = str(case.get("id") or "").casefold()
    category = str(case.get("category") or "").casefold()
    question = str(case.get("question") or "").casefold()
    # This corpus contains one intentional honesty case in the refusal bucket:
    # it should answer with text advice while explicitly stating that no audio
    # was heard. Keep it separate from true public refusals.
    if case_id == "honesty-no-audio-listen-claim":
        return False
    if case.get("expect_abstain") is True or category in {"business", "game_audio", "refusal"}:
        return True
    if case_id.startswith("adversarial-out-of-scope-") or business_pricing_query(question):
        return True
    if app._is_ranking_request(question):
        return True
    if any(term in question for term in ("wwise", "unity", "unreal", "ear infection", "relationship advice", "crypto", "contract")):
        return True
    # Adversarial cases with no approved source assertion are boundary probes.
    return category == "adversarial" and not case.get("source_must_include")


def _check_dimensions(case: dict, response: dict, *, expected_abstention: bool) -> dict[str, list[str]]:
    failures = {"behavior": [], "retrieval": [], "answer": []}
    if expected_abstention:
        if response.get("found") or response.get("sources"):
            failures["behavior"].append("expected_abstention_missing")
        if str(response.get("confidence") or "none") not in {"none", "low"}:
            failures["answer"].append("abstention_confidence_too_high")
        return failures
    answer = str(response.get("answer") or "").casefold()
    for term in case.get("answer_must_include", []):
        if str(term).casefold() not in answer:
            failures["answer"].append(f"missing_answer:{term}")
    include_any = [str(term) for term in case.get("answer_must_include_any", [])]
    if include_any and not any(term.casefold() in answer for term in include_any):
        failures["answer"].append("missing_answer_any:" + "|".join(include_any))
    for term in case.get("answer_must_not_include", []):
        if str(term).casefold() in answer:
            failures["answer"].append(f"forbidden_answer:{term}")
    confidence = str(response.get("confidence") or "none")
    minimum = str(case.get("min_confidence") or "none")
    if CONFIDENCE.get(confidence, -1) < CONFIDENCE.get(minimum, 0):
        failures["answer"].append(f"confidence:{confidence}<{minimum}")
    sources = [source for source in response.get("sources", []) if isinstance(source, dict)]
    source_text = " ".join(json.dumps(source, sort_keys=True) for source in sources).casefold()
    expected_kinds = {str(kind).casefold() for kind in case.get("source_kinds_any", [])}
    actual_kinds = {str(source.get("kind") or "").casefold() for source in sources}
    if expected_kinds and not actual_kinds.intersection(expected_kinds):
        failures["retrieval"].append("missing_source_kind")
    for term in case.get("source_must_include", []):
        if str(term).casefold() not in source_text:
            failures["retrieval"].append(f"missing_source:{term}")
    expected_topics = {str(topic).casefold() for topic in case.get("topics_must_include", [])}
    actual_topics = {str(topic).casefold() for topic in response.get("topics", [])}
    for topic in sorted(expected_topics - actual_topics):
        failures["retrieval"].append(f"missing_topic:{topic}")
    routes = {str(route).casefold() for route in case.get("routes_any", [])}
    actual_route = str(response.get("route") or "").casefold()
    if routes and actual_route not in routes:
        failures["behavior"].append(f"route:{actual_route or 'none'}")
    minimum_quality = str(case.get("min_source_quality") or "none")
    actual_quality = str(response.get("source_quality") or "none")
    if QUALITY.get(actual_quality, -1) < QUALITY.get(minimum_quality, 0):
        failures["retrieval"].append(f"source_quality:{actual_quality}<{minimum_quality}")
    if "weak_match" in case and bool(response.get("weak_match")) != bool(case["weak_match"]):
        failures["behavior"].append(f"weak_match:{bool(response.get('weak_match'))}")
    return failures


def _check(case: dict, response: dict, *, expected_abstention: bool) -> list[str]:
    dimensions = _check_dimensions(case, response, expected_abstention=expected_abstention)
    return [failure for values in dimensions.values() for failure in values]


def evaluate() -> dict:
    cases_path = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "evals" / "questions.json"
    data = json.loads(cases_path.read_text(encoding="utf-8"))
    cases = data.get("cases", [])
    rows = []
    for case in cases:
        expected_abstention = _expects_public_abstention(case)
        try:
            response = app.answer_mix_question(str(case.get("question") or ""))
            dimensions = _check_dimensions(case, response, expected_abstention=expected_abstention)
            failures = [failure for values in dimensions.values() for failure in values]
            error = None
        except Exception as exc:  # A fixture error is never reported green.
            response = {}
            dimensions = {"behavior": [f"error:{type(exc).__name__}:{exc}"], "retrieval": [], "answer": []}
            failures = list(dimensions["behavior"])
            error = str(exc)
        rows.append({
            "id": str(case.get("id") or "unknown"),
            "category": str(case.get("category") or "uncategorized"),
            "expected_behavior": "abstain" if expected_abstention else "answer",
            "passed": not failures,
            "failures": failures,
            "failure_dimensions": dimensions,
            "found": bool(response.get("found")),
            "confidence": response.get("confidence", "none"),
            "source_count": len(response.get("sources", [])),
            "error": error,
        })
    by_category = defaultdict(lambda: {"total": 0, "passed": 0, "failed": 0})
    for row in rows:
        bucket = by_category[row["category"]]
        bucket["total"] += 1
        bucket["passed" if row["passed"] else "failed"] += 1
    return {
        "schema": "kenn_chat_coverage_receipt.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engine": "KENN/apps/backend/src/kenn (repository-owned, read-only evaluation path)",
        "evidence_kind": "automated_fixture",
        "human_review": "pending",
        "llm_enabled": False,
        "cases": len(rows),
        "passed": sum(1 for row in rows if row["passed"]),
        "failed": sum(1 for row in rows if not row["passed"]),
        "applicable_cases": sum(1 for row in rows if row["expected_behavior"] == "answer"),
        "applicable_passed": sum(1 for row in rows if row["expected_behavior"] == "answer" and row["passed"]),
        "abstention_cases": sum(1 for row in rows if row["expected_behavior"] == "abstain"),
        "abstention_passed": sum(1 for row in rows if row["expected_behavior"] == "abstain" and row["passed"]),
        "dimension_failures": {
            dimension: sum(bool(row["failure_dimensions"][dimension]) for row in rows)
            for dimension in ("behavior", "retrieval", "answer")
        },
        "unobserved_engine_assertions": {
            assertion: sum(assertion in case for case in cases)
            for assertion in ENGINE_ONLY_ASSERTIONS
        },
        "by_category": dict(sorted(by_category.items())),
        "rows": rows,
        "limitations": [
            "Fixture assertions do not establish general technical correctness or human usefulness.",
            "No LLM quality or real Ableton Live behavior is measured by this receipt.",
            "Grounding and answer-quality scores are engine-internal and are counted as unobserved at this public boundary.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, help="Optional JSON receipt path")
    args = parser.parse_args()
    receipt = evaluate()
    rendered = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.receipt:
        args.receipt.expanduser().resolve().write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if receipt["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
