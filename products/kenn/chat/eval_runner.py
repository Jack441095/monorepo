"""Run KENN's held-out chat evaluations through the scoped service boundary."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import app

from kenn.core.chat import answer_payload
from kenn.core.chat_routing import classify_answer_mode, route_query
from kenn.core.evidence import from_mix_review_context, from_plugin_context, history_turn


ENGINE_EVAL_ROOT = app.ENGINE_ROOT / "kenn" / "evals"
CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}
PUBLIC_KNOWLEDGE_CASES = {
    "knowledge_upgrade_cases.json": {
        "recording",
        "mastering",
        "monitoring",
        "mixing",
        "sound_design",
        "production",
        "arrangement",
    },
    "internet_source_cases.json": {"standards", "mastering"},
}
PUBLIC_BOUNDARY_CATEGORIES = {"game_audio", "broadcast"}


def _load_cases(filename: str) -> list[dict[str, Any]]:
    path = ENGINE_EVAL_ROOT / filename
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data.get("cases")
    if not isinstance(cases, list):
        raise ValueError(f"{path} does not contain a cases list")
    return [case for case in cases if isinstance(case, dict)]


def _case_turns(case: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    if isinstance(case.get("turns"), list) and case["turns"]:
        turns = [str(turn).strip() for turn in case["turns"] if str(turn).strip()]
        if turns:
            return turns[-1], [{"role": "user", "content": turn} for turn in turns[:-1]]
    question = str(case.get("question") or "").strip()
    raw_history = case.get("history") or []
    history = [
        {"role": str(turn.get("role") or "user"), "content": str(turn.get("content") or "")}
        for turn in raw_history
        if isinstance(turn, dict) and str(turn.get("content") or "").strip()
    ]
    return question, history


def _with_fixture_evidence(case: dict[str, Any], history: list[dict[str, str]]) -> list[dict[str, str]]:
    enriched = list(history)
    plugin_packet = from_plugin_context(case.get("plugin_context"))
    if plugin_packet:
        enriched.append(history_turn(plugin_packet))
    review_packet = from_mix_review_context(case.get("mix_review_context"))
    if review_packet:
        enriched.append(history_turn(review_packet))
    return enriched


def _engine_payload(
    question: str,
    history: list[dict[str, str]],
    session_id: str = "",
) -> dict[str, Any]:
    """Call the real engine for fixture-backed cases without public uploads.

    The fixtures are structured evidence test inputs, not an upload API. They
    stay inside the local evaluation process and are never accepted by the
    public ChatRequest model.
    """
    route = route_query(question, history)
    mode = classify_answer_mode(question, route, history=history)
    return answer_payload(
        question,
        limit=4,
        history=history,
        allow_llm=False,
        session_id=session_id,
        answer_mode=mode,
    )


def _check_diagnostic(case: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    answer = str(payload.get("answer") or "")
    folded = answer.casefold()
    failures: list[str] = []
    for needle in case.get("must_include") or []:
        if str(needle).casefold() not in folded:
            failures.append(f"missing:{needle}")
    any_needles = [str(item) for item in case.get("must_include_any") or []]
    if any_needles and not any(item.casefold() in folded for item in any_needles):
        failures.append("missing_any:" + "|".join(any_needles))
    for needle in case.get("must_not_include") or []:
        if str(needle).casefold() in folded:
            failures.append(f"forbidden:{needle}")
    for pair in case.get("must_appear_before") or []:
        if not isinstance(pair, list) or len(pair) != 2:
            failures.append(f"invalid_order_pair:{pair!r}")
            continue
        first, second = (str(item).casefold() for item in pair)
        first_pos, second_pos = folded.find(first), folded.find(second)
        if first_pos < 0 or second_pos < 0 or first_pos >= second_pos:
            failures.append(f"order:{pair[0]}<{pair[1]}")
    return failures


def _check_conversation(case: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    answer = str(payload.get("answer") or "")
    folded = answer.casefold()
    failures: list[str] = []
    any_needles = [str(item) for item in case.get("answer_must_include_any") or []]
    if any_needles and not any(item.casefold() in folded for item in any_needles):
        failures.append("missing_answer_any:" + "|".join(any_needles))
    sources = payload.get("sources") or []
    source_text = " ".join(
        str(source.get("source") or "") for source in sources if isinstance(source, dict)
    ).casefold()
    for needle in case.get("source_must_include") or []:
        if str(needle).casefold() not in source_text:
            failures.append(f"missing_source:{needle}")
    kinds = {
        str(source.get("kind") or "")
        for source in sources
        if isinstance(source, dict)
    }
    expected_kinds = {str(kind) for kind in case.get("source_kinds_any") or []}
    if expected_kinds and not kinds.intersection(expected_kinds):
        failures.append("missing_source_kind:" + "|".join(sorted(expected_kinds)))
    expected_weak = case.get("weak_match")
    if expected_weak is not None and bool(payload.get("weak_match")) != bool(expected_weak):
        failures.append(f"weak_match:{payload.get('weak_match')}!={expected_weak}")
    confidence = str(payload.get("confidence") or "low")
    if CONFIDENCE_RANK.get(confidence, -1) < CONFIDENCE_RANK.get(str(case.get("min_confidence") or "low"), 0):
        failures.append(f"confidence_below:{case.get('min_confidence')}")
    if case.get("max_confidence") and CONFIDENCE_RANK.get(confidence, 9) > CONFIDENCE_RANK.get(str(case["max_confidence"]), 9):
        failures.append(f"confidence_above:{case.get('max_confidence')}")
    return failures


def _run_case(case: dict[str, Any], suite: str) -> dict[str, Any]:
    question, history = _case_turns(case)
    fixture_backed = bool(case.get("plugin_context") or case.get("mix_review_context"))
    history_with_evidence = _with_fixture_evidence(case, history)
    try:
        if isinstance(case.get("turns"), list) and case["turns"]:
            session_id = f"eval-{suite}-{case.get('id', 'unknown')}"
            payload = {}
            for turn in case["turns"]:
                payload = _engine_payload(str(turn), [], session_id=session_id)
        elif fixture_backed:
            payload = _engine_payload(question, history_with_evidence)
        else:
            payload = app.answer_mix_question(question, history)
        failures = (
            _check_diagnostic(case, payload)
            if suite == "diagnostic"
            else _check_conversation(case, payload)
        )
        return {
            "id": str(case.get("id") or "unknown"),
            "suite": suite,
            "category": str(case.get("category") or ("fixture" if fixture_backed else suite)),
            "passed": not failures,
            "failures": failures,
            "confidence": payload.get("confidence", "low"),
            "found": bool(payload.get("found")),
            "weak_match": bool(payload.get("weak_match")),
            "source_count": len(payload.get("sources") or []),
            "negative_advice_guard": bool(
                suite == "diagnostic"
                and (case.get("must_not_include") or case.get("must_appear_before"))
            ),
        }
    except Exception as exc:  # surfaced in the receipt; never reported green
        return {
            "id": str(case.get("id") or "unknown"),
            "suite": suite,
            "category": str(case.get("category") or suite),
            "passed": False,
            "failures": [f"error:{type(exc).__name__}:{exc}"],
            "confidence": "error",
            "found": False,
            "weak_match": True,
            "source_count": 0,
            "negative_advice_guard": bool(
                suite == "diagnostic"
                and (case.get("must_not_include") or case.get("must_appear_before"))
            ),
        }


def _run_abstention_check() -> dict[str, Any]:
    probes = (
        "Can you control my Ableton session?",
        "What is the weather today?",
        "Upload my WAV and analyse it.",
        "Can you generate a mix for me?",
        "Can you create a mix?",
        "Can you render my mix?",
        "Can you automate my mix?",
        "Can you launch a clip in my mix?",
        "Can you mix this for me?",
        "Can you fix my mix?",
        "Can you apply these mix changes?",
        "Can you process my mix?",
        "Can you review my mix?",
        "Which compressor is best for bass?",
        "What's the best EQ for vocals?",
        "Which plugin should I use for harshness?",
        "What limiter do you recommend for mastering?",
        "Which of these plugins is better for drums?",
        "Who invented mixing?",
        "Write lyrics for my mix.",
        "How much does a mix engineer charge?",
        "What is a mix engineer salary?",
        "Recommend a studio for my mix.",
        "Can you listen to this mix and tell me if it is good?",
        "Which compressor would you use for bass?",
        "What plugin do you prefer for vocals?",
    )
    results = []
    for question in probes:
        payload = app.answer_mix_question(question)
        results.append(
            {
                "intent": payload.get("intent"),
                "found": bool(payload.get("found")),
                "sources": len(payload.get("sources") or []),
                "passed": payload.get("intent") == "out_of_scope"
                and not payload.get("found")
                and not payload.get("sources"),
            }
        )
    passed = sum(1 for item in results if item["passed"])
    return {
        "probes": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "abstention_rate": round(passed / len(results), 3) if results else 1.0,
        "results": results,
    }


def _run_public_corpus_boundary_check() -> dict[str, Any]:
    """Verify specialist corpus material cannot enter the public chat path."""
    results: list[dict[str, Any]] = []
    for filename in PUBLIC_KNOWLEDGE_CASES:
        for case in _load_cases(filename):
            if case.get("category") not in PUBLIC_BOUNDARY_CATEGORIES:
                continue
            payload = app.answer_mix_question(str(case.get("question") or ""))
            passed = (
                payload.get("intent") == "out_of_scope"
                and not payload.get("found")
                and not payload.get("sources")
            )
            results.append(
                {
                    "id": str(case.get("id") or "unknown"),
                    "category": str(case.get("category") or "unknown"),
                    "passed": passed,
                    "intent": payload.get("intent"),
                    "found": bool(payload.get("found")),
                    "source_count": len(payload.get("sources") or []),
                }
            )
    return {
        "total": len(results),
        "passed": sum(1 for result in results if result["passed"]),
        "failed": sum(1 for result in results if not result["passed"]),
        "results": results,
    }


def _summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_category: dict[str, dict[str, int]] = {}
    for result in results:
        category = result["category"]
        bucket = by_category.setdefault(category, {"passed": 0, "failed": 0, "total": 0})
        bucket["total"] += 1
        bucket["passed" if result["passed"] else "failed"] += 1
    return {
        "total": len(results),
        "passed": sum(1 for result in results if result["passed"]),
        "failed": sum(1 for result in results if not result["passed"]),
        "by_category": by_category,
    }


def run_evaluation() -> dict[str, Any]:
    diagnostic_cases = _load_cases("diagnostic_reasoning_cases.json")
    conversation_cases = _load_cases("conversation_cases.json")
    results = [
        *[_run_case(case, "diagnostic") for case in diagnostic_cases],
        *[_run_case(case, "conversation") for case in conversation_cases],
    ]
    public_quality_results: dict[str, list[dict[str, Any]]] = {}
    for filename, allowed_categories in PUBLIC_KNOWLEDGE_CASES.items():
        suite = filename.removesuffix("_cases.json")
        selected = [
            case
            for case in _load_cases(filename)
            if case.get("category") in allowed_categories
        ]
        public_quality_results[suite] = [
            _run_case(case, suite) for case in selected
        ]
    for suite_results in public_quality_results.values():
        results.extend(suite_results)
    diagnostic_results = [result for result in results if result["suite"] == "diagnostic"]
    guard_results = [result for result in diagnostic_results if result["negative_advice_guard"]]
    abstention = _run_abstention_check()
    corpus_boundary = _run_public_corpus_boundary_check()
    return {
        "schema": "kenn_chat_eval_receipt.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engine": "Audio_Too/studio/kenn (read-only dependency)",
        "llm_enabled": False,
        "scope": "mix_advice_only",
        "diagnostic": _summary(diagnostic_results),
        "conversation": _summary([result for result in results if result["suite"] == "conversation"]),
        "public_knowledge": {
            suite: _summary(suite_results)
            for suite, suite_results in public_quality_results.items()
        },
        "negative_advice_guard": {
            "total": len(guard_results),
            "passed": sum(1 for result in guard_results if result["passed"]),
            "failed": sum(1 for result in guard_results if not result["passed"]),
        },
        "abstention_check": abstention,
        "public_corpus_boundary": corpus_boundary,
        "passed": (
            all(result["passed"] for result in results)
            and abstention["failed"] == 0
            and corpus_boundary["failed"] == 0
        ),
        "failures": [result for result in results if not result["passed"]],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--receipt",
        default=str(app.SERVICE_ROOT / ".runtime" / "eval-receipt.json"),
        help="Path for the machine-readable receipt (default: ignored runtime path)",
    )
    args = parser.parse_args()
    receipt = run_evaluation()
    output = Path(args.receipt).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
