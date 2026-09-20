#!/usr/bin/env python3
"""JSON-driven regression checks for Audio Tips LLM retrieval and answers."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
ABLETON = ROOT / "studio" / "kenn" / "kenn"
DEFAULT_SUITE = ABLETON / "evals" / "questions.json"

CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}
SOURCE_QUALITY_ORDER = {"low": 0, "medium": 1, "high": 2}


def load_suite(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data.get("cases")
    if not isinstance(cases, list):
        raise ValueError(f"Eval suite must contain a cases list: {path}")
    validate_suite(cases)
    return cases


def validate_suite(cases: list[dict]) -> None:
    """Reject an underspecified or accidentally narrowed held-out suite."""
    if not 100 <= len(cases) <= 200:
        raise ValueError(f"Held-out suite must contain 100-200 cases, got {len(cases)}")
    ids = [str(case.get("id") or "").strip() for case in cases]
    if not all(ids) or len(set(ids)) != len(ids):
        raise ValueError("Held-out suite case IDs must be present and unique")
    for case in cases:
        if not str(case.get("question") or "").strip():
            raise ValueError(f"Held-out case {case['id']!r} has no question")
        if not list(case.get("answer_must_include") or []):
            raise ValueError(f"Held-out case {case['id']!r} has no required facts")
    categories = {str(case.get("category") or "standard") for case in cases}
    required_categories = {"standard", "adversarial", "ambiguity", "business", "refusal"}
    missing = required_categories - categories
    if missing:
        raise ValueError(f"Held-out suite is missing required categories: {sorted(missing)}")
    source_cases = sum(bool(case.get("source_must_include")) for case in cases)
    if source_cases / len(cases) < 0.70:
        raise ValueError("Expected source IDs cover less than 70% of the held-out suite")


def confidence_at_least(actual: str, expected: str) -> bool:
    return CONFIDENCE_ORDER.get(actual, -1) >= CONFIDENCE_ORDER.get(expected, -1)


def confidence_at_most(actual: str, expected: str) -> bool:
    return CONFIDENCE_ORDER.get(actual, 99) <= CONFIDENCE_ORDER.get(expected, 99)


def source_quality_at_least(actual: str, expected: str) -> bool:
    return SOURCE_QUALITY_ORDER.get(actual, -1) >= SOURCE_QUALITY_ORDER.get(expected, -1)


def source_quality_at_most(actual: str, expected: str) -> bool:
    return SOURCE_QUALITY_ORDER.get(actual, 99) <= SOURCE_QUALITY_ORDER.get(expected, 99)


def _has_term(text: str, term: str) -> bool:
    import re
    lowered_text = text.lower()
    lowered_term = term.lower()
    if lowered_term not in lowered_text:
        return False
    if lowered_term in {"eq", "mud"}:
        pattern = r"(?<![a-zA-Z0-9_])" + re.escape(lowered_term) + r"(s)?(?![a-zA-Z0-9_])"
        return bool(re.search(pattern, lowered_text))
    return True


def terms_missing(text: str, terms: list[str]) -> list[str]:
    return [term for term in terms if not _has_term(text, term)]


def terms_present(text: str, terms: list[str]) -> list[str]:
    return [term for term in terms if _has_term(text, term)]


def terms_include_any(text: str, terms: list[str]) -> bool:
    return any(_has_term(text, term) for term in terms)


def _clean_eval_answer(answer: str) -> str:
    import re
    return re.sub(
        r"\n*past reasoning on this topic:.*?(?=\n\n|\n[→•]|\Z)",
        "",
        answer,
        flags=re.DOTALL | re.IGNORECASE
    )


def evaluation_dimensions(case: dict, payload: dict) -> dict:
    """Return machine-readable grounding dimensions without judging exact prose."""
    answer = _clean_eval_answer(str(payload.get("answer") or ""))
    required = list(case.get("answer_must_include") or [])
    required_any = list(case.get("answer_must_include_any") or [])
    covered_required = len(required) - len(terms_missing(answer, required))
    if required_any:
        covered_required += int(terms_include_any(answer, required_any))
    required_fact_count = len(required) + int(bool(required_any))

    expected_sources = list(case.get("source_must_include") or [])
    sources = list(payload.get("sources") or [])
    source_labels = " ".join(str(source.get("label", "")) for source in sources)
    matched_sources = len(expected_sources) - len(terms_missing(source_labels, expected_sources))
    structurally_valid_citations = sum(
        1
        for source in sources
        if str(source.get("label", "")).strip()
        and str(source.get("source", "")).strip()
        and str(source.get("kind", "")).strip()
        and str(source.get("text", "")).strip()
    )

    critical_forbidden = list(case.get("critical_forbidden_claims") or [])
    forbidden = list(case.get("answer_must_not_include") or []) + critical_forbidden
    forbidden_hits = terms_present(answer, forbidden)
    critical_forbidden_hits = terms_present(answer, critical_forbidden)

    abstention_required = bool(case.get("weak_match") is True) or str(
        case.get("max_confidence", "")
    ).lower() == "low"
    abstention_correct = bool(payload.get("weak_match")) and str(
        payload.get("confidence", "low")
    ).lower() == "low"

    source_kinds = {str(source.get("kind", "")) for source in payload.get("sources") or []}
    expected_kinds = set(case.get("source_kinds_any") or [])
    retrieval_ok = matched_sources == len(expected_sources)
    if expected_kinds:
        retrieval_ok = retrieval_ok and bool(source_kinds & expected_kinds)

    return {
        "required_fact_count": required_fact_count,
        "required_fact_covered": covered_required,
        "citation_expectation_count": len(expected_sources),
        "citation_expectation_matched": matched_sources,
        "citation_count": len(sources),
        "structurally_valid_citations": structurally_valid_citations,
        "forbidden_claim_hits": forbidden_hits,
        "critical_forbidden_claim_hits": critical_forbidden_hits,
        "abstention_required": abstention_required,
        "abstention_correct": abstention_correct if abstention_required else None,
        "retrieval_ok": retrieval_ok,
        "generation_ok": covered_required == required_fact_count and not forbidden_hits,
    }


def evaluate_case(case: dict, payload: dict) -> list[str]:
    failures: list[str] = []
    answer = _clean_eval_answer(str(payload.get("answer") or "")).lower()
    confidence = str(payload.get("confidence", "low")).lower()
    min_confidence = case.get("min_confidence")
    if min_confidence is None and "max_confidence" not in case:
        min_confidence = "medium"
    if min_confidence is not None and not confidence_at_least(confidence, str(min_confidence).lower()):
        failures.append(f"confidence {confidence!r} below {min_confidence!r}")
    max_confidence = case.get("max_confidence")
    if max_confidence and not confidence_at_most(confidence, str(max_confidence).lower()):
        failures.append(f"confidence {confidence!r} above {max_confidence!r}")

    source_quality = str(payload.get("source_quality", "low")).lower()
    min_source_quality = case.get("min_source_quality")
    if min_source_quality and not source_quality_at_least(source_quality, str(min_source_quality).lower()):
        failures.append(f"source_quality {source_quality!r} below {min_source_quality!r}")
    max_source_quality = case.get("max_source_quality")
    if max_source_quality and not source_quality_at_most(source_quality, str(max_source_quality).lower()):
        failures.append(f"source_quality {source_quality!r} above {max_source_quality!r}")

    missing = terms_missing(answer, list(case.get("answer_must_include") or []))
    if missing:
        failures.append(f"missing answer terms: {missing}")

    include_any = list(case.get("answer_must_include_any") or [])
    if include_any and not terms_include_any(answer, include_any):
        failures.append(f"answer does not include any of: {include_any}")

    banned = terms_present(answer, list(case.get("answer_must_not_include") or []))
    if banned:
        failures.append(f"banned answer terms present: {banned}")

    topics = set(payload.get("topics") or [])
    missing_topics = [topic for topic in case.get("topics_must_include") or [] if topic not in topics]
    if missing_topics:
        failures.append(f"missing topics: {missing_topics}")

    source_kinds = {str(source.get("kind", "")) for source in payload.get("sources") or []}
    expected_any = set(case.get("source_kinds_any") or [])
    if expected_any and not (source_kinds & expected_any):
        failures.append(f"sources do not include any of: {sorted(expected_any)}")

    source_must_include = list(case.get("source_must_include") or [])
    if source_must_include:
        labels = " ".join(str(source.get("label", "")) for source in payload.get("sources") or []).lower()
        missing_source_terms = [term for term in source_must_include if term.lower() not in labels]
        if missing_source_terms:
            failures.append(f"missing source label terms: {missing_source_terms}")

    answer_mode = str(payload.get("answer_mode", "unknown"))
    expected_mode = case.get("answer_mode")
    if expected_mode and answer_mode != str(expected_mode):
        failures.append(f"answer_mode {answer_mode!r} != {expected_mode!r}")

    expected_modes = set(case.get("answer_modes_any") or [])
    if expected_modes and answer_mode not in expected_modes:
        failures.append(f"answer_mode {answer_mode!r} not in {sorted(expected_modes)}")

    expected_route = case.get("route")
    if expected_route and str(payload.get("route", "unknown")) != str(expected_route):
        failures.append(f"route {payload.get('route', 'unknown')!r} != {expected_route!r}")

    expected_routes = set(case.get("routes_any") or [])
    if expected_routes and str(payload.get("route", "unknown")) not in expected_routes:
        failures.append(f"route {payload.get('route', 'unknown')!r} not in {sorted(expected_routes)}")

    expected_intent = case.get("intent")
    if expected_intent and str(payload.get("intent", "unknown")) != str(expected_intent):
        failures.append(f"intent {payload.get('intent', 'unknown')!r} != {expected_intent!r}")

    if "weak_match" in case and bool(payload.get("weak_match")) is not bool(case.get("weak_match")):
        failures.append(f"weak_match {bool(payload.get('weak_match'))!r} != {bool(case.get('weak_match'))!r}")

    expected_grounding_mode = case.get("grounding_mode")
    if expected_grounding_mode and str(payload.get("grounding_mode", "unknown")) != str(expected_grounding_mode):
        failures.append(f"grounding_mode {payload.get('grounding_mode', 'unknown')!r} != {expected_grounding_mode!r}")

    min_grounding_score = case.get("min_grounding_score")
    if min_grounding_score is not None:
        grounding = payload.get("grounding") if isinstance(payload.get("grounding"), dict) else {}
        score = int(grounding.get("score", 0) or 0)
        if score < int(min_grounding_score):
            failures.append(f"grounding_score {score} below {min_grounding_score}")

    min_quality = case.get("min_answer_quality")
    if min_quality is not None:
        quality = payload.get("answer_quality") if isinstance(payload.get("answer_quality"), dict) else {}
        score = int(quality.get("score", 0) or 0)
        if score < int(min_quality):
            failures.append(f"answer_quality {score} below {min_quality}")

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Audio Tips LLM regression evals.")
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE, help="Path to eval suite JSON.")
    parser.add_argument("--limit", type=int, default=8, help="Retrieval source limit.")
    args = parser.parse_args()

    # See the matching note in ableton_benchmark.py: without ROOT itself on
    # sys.path, answer_payload()'s embedder silently falls back to BM25-only.
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ABLETON.parent))
    from kenn.core.chat import answer_payload  # noqa: E402

    cases = load_suite(args.suite)
    failures = 0
    for case in cases:
        question = str(case.get("question", "")).strip()
        if not question:
            print(f"FAIL [{case.get('id', 'unknown')}]: missing question")
            failures += 1
            continue
        history = case.get("history") if isinstance(case.get("history"), list) else None
        payload = answer_payload(question, history=history, limit=args.limit, allow_llm=False)
        case_failures = evaluate_case(case, payload)
        label = case.get("id") or question
        if case_failures:
            print(f"FAIL [{label}] {question}")
            for failure in case_failures:
                print(f"  - {failure}")
            failures += 1
            continue
        print(f"OK   [{label}] ({payload.get('confidence', 'unknown')})")

    if failures:
        print(f"\n{failures} evaluation case(s) failed.")
        return 1
    print(f"\nAll {len(cases)} Audio Tips LLM evaluation case(s) passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
