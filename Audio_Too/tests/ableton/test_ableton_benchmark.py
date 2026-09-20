"""Tests for Audio Tips LLM benchmark summaries."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "eval"))

from ableton_benchmark import summarize  # noqa: E402
from ableton_eval import evaluation_dimensions, validate_suite  # noqa: E402


def test_grounding_dimensions_separate_retrieval_generation_and_abstention() -> None:
    case = {
        "answer_must_include": ["kick", "bass"],
        "answer_must_include_any": ["release", "tempo"],
        "answer_must_not_include": ["always works"],
        "critical_forbidden_claims": ["guaranteed safe"],
        "source_must_include": ["sidechain-bass"],
        "source_kinds_any": ["note"],
        "weak_match": True,
        "max_confidence": "low",
    }
    payload = {
        "answer": "Use the kick to duck the bass and tune the release.",
        "confidence": "low",
        "weak_match": True,
        "sources": [
            {
                "label": "Sidechain Bass (sidechain-bass.md)",
                "source": "sidechain-bass.md",
                "kind": "note",
                "text": "Approved note text",
            }
        ],
    }

    dimensions = evaluation_dimensions(case, payload)

    assert dimensions["required_fact_covered"] == 3
    assert dimensions["structurally_valid_citations"] == 1
    assert dimensions["citation_expectation_matched"] == 1
    assert dimensions["retrieval_ok"] is True
    assert dimensions["generation_ok"] is True
    assert dimensions["abstention_correct"] is True
    assert dimensions["critical_forbidden_claim_hits"] == []


def test_held_out_suite_policy_rejects_accidental_narrowing() -> None:
    import pytest

    with pytest.raises(ValueError, match="100-200"):
        validate_suite([{"id": "only-one", "question": "q", "answer_must_include": ["x"]}])


def test_benchmark_summary_includes_timing_breakdown_and_slowest_runs() -> None:
    records = [
        {
            "id": "fast",
            "question": "fast question",
            "duration_ms": 10.0,
            "confidence": "high",
            "source_quality": "high",
            "route": "production",
            "intent": "steps",
            "category": "standard",
            "case_tags": ["retrieval"],
            "grounding_mode": "strong",
            "source_diversity": {"warnings": []},
            "source_labels": [],
            "timings_ms": {"search_ms": 7.0, "answer_ms": 2.0},
            "eval_failures": [],
        },
        {
            "id": "slow",
            "question": "slow question",
            "duration_ms": 50.0,
            "confidence": "low",
            "source_quality": "low",
            "route": "unknown",
            "intent": "general",
            "category": "adversarial",
            "case_tags": ["refusal"],
            "grounding_mode": "weak",
            "source_diversity": {"warnings": []},
            "source_labels": [],
            "timings_ms": {"search_ms": 45.0, "answer_ms": 3.0},
            "eval_failures": ["missing term"],
        },
    ]

    summary = summarize(records, suite=Path("suite.json"), limit=8, repeat=1, allow_llm=False)

    assert summary["timing_components_ms"]["search_ms"]["mean"] == 26.0
    assert summary["route_counts"]["production"] == 1
    assert summary["intent_counts"]["steps"] == 1
    assert summary["case_category_counts"]["adversarial"] == 1
    assert summary["case_category_failures"]["adversarial"] == 1
    assert summary["case_category_pass_rates"]["standard"] == 1.0
    assert summary["case_tag_counts"]["refusal"] == 1
    assert summary["grounding_mode_counts"]["strong"] == 1
    assert summary["slowest_runs"][0]["id"] == "slow"
    assert summary["failures"][0]["id"] == "slow"
