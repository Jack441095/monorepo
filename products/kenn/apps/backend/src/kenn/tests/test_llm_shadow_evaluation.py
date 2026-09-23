"""Tests for the model-contract gate used by the offline LLM evaluator."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from scripts.evaluate_kenn_llm_shadow import DEFAULT_CASES, _failure_kind, _fixture_snapshot, _load_cases, _model_contract_gate
from kenn.core.live_intent import parse_request


def test_model_contract_gate_requires_acceptance_and_deterministic_match() -> None:
    result = _model_contract_gate([
        {
            "id": "mute",
            "llm_status": "accepted",
            "comparison": {"status": "match"},
            "deterministic_contract_ok": True,
        }
    ])

    assert result["model_contract_passed"] is True
    assert result["live_activation_allowed"] is False
    assert result["blockers"] == []
    assert result["promotion_assessment"]["eligible"] is False
    assert result["promotion_assessment"]["metrics"]["comparisons"] == 1
    assert result["required_before_live_activation"]


def test_model_contract_gate_reports_mismatch_and_rejection() -> None:
    result = _model_contract_gate([
        {
            "id": "wrong-track",
            "llm_status": "accepted",
            "comparison": {"status": "mismatch"},
            "deterministic_contract_ok": True,
        },
        {
            "id": "missing-schema",
            "llm_status": "rejected",
            "comparison": None,
            "deterministic_contract_ok": True,
        },
    ])

    assert result["model_contract_passed"] is False
    assert result["live_activation_allowed"] is False
    assert "wrong-track: model plan disagreed with deterministic interpretation" in result["blockers"]
    assert "missing-schema: model plan was not validator-accepted" in result["blockers"]


def test_failure_kind_separates_schema_and_contract_rejections() -> None:
    assert _failure_kind("accepted", "") is None
    assert _failure_kind("rejected", "The LLM returned an invalid KENN command-plan schema.") == "malformed_or_wrong_schema"
    assert _failure_kind("rejected", "Only a recipe action may contain nested steps") == "validator_contract_rejection"
    assert _failure_kind("rejected", "The LLM device value is outside the current Live capability range") == "capability_rejection"


def test_holdout_cases_have_a_passing_deterministic_contract() -> None:
    snapshot = _fixture_snapshot()
    cases = _load_cases(DEFAULT_CASES)
    assert len(cases) >= 15
    failures = []
    for case in cases:
        intent = parse_request(str(case["query"]), snapshot)
        needs_clarification = bool(intent.get("missing_fields") or intent.get("ambiguity"))
        if intent.get("action") != case.get("expected_action") or needs_clarification != bool(case.get("expects_clarification")):
            failures.append({
                "id": case.get("id"),
                "action": intent.get("action"),
                "expected_action": case.get("expected_action"),
                "needs_clarification": needs_clarification,
                "expected_clarification": case.get("expects_clarification"),
            })
    assert failures == []


def test_natural_language_holdout_is_distinct_and_covers_required_axes() -> None:
    root = Path(__file__).resolve().parents[5]
    natural_path = root / "tooling" / "data" / "natural_holdout.jsonl"
    cases = _load_cases(natural_path)
    training_path = root / "apps" / "backend" / "src" / "kenn" / "training" / "ableton_command_training.jsonl"
    training_queries = {
        str(item.get("query", ""))
        for item in _load_cases(training_path)
    }

    assert len(cases) >= 20
    assert {str(item.get("category", "")) for item in cases} >= {
        "incomplete",
        "colloquial",
        "ambiguous",
        "multi_intent",
        "mid_sentence_correction",
    }
    assert all(item.get("source_kind") == "curated_requirement_seed" for item in cases)
    assert not ({str(item.get("query", "")) for item in cases} & training_queries)
