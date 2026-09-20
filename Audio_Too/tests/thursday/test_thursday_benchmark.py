"""Release-gate tests for Thursday's held-out routing benchmark."""

from __future__ import annotations

from dataclasses import replace

import pytest

from thursday.evals.benchmark import (
    MIN_CRITICAL_ACCURACY,
    MIN_OVERALL_ACCURACY,
    MIN_TARGET_ACCURACY,
    evaluate,
)
from thursday.evals.corpus import final_release_holdout_cases, held_out_cases


@pytest.fixture(autouse=True)
def _force_deterministic_routing(monkeypatch):
    """This module's docstring and evaluate()'s own says "deterministic held-
    out routing" -- it must exercise the regex router only, never the LLM
    brain, regardless of ambient environment. Without this, KENN's
    `llm_rewrite.load_env()` (triggered by some import elsewhere in the
    suite) applies THURSDAY_BRAIN_ENABLED from .env into os.environ for the
    rest of the pytest process, so a handful of the 500+ held-out cases get
    answered by the real local model instead of the deterministic router,
    silently dropping target_accuracy below this release gate's threshold.
    Same class of ambient-env-leak bug already fixed once in this codebase
    for KENN_LM_ENABLED -- see tests/kenn/test_kenn_grounding_parity.py.
    """
    monkeypatch.delenv("AUDIO_TOO_LLM_ENABLED", raising=False)
    monkeypatch.delenv("THURSDAY_BRAIN_ENABLED", raising=False)


def test_held_out_corpus_is_large_unique_and_covers_required_language() -> None:
    cases = final_release_holdout_cases()
    assert len(cases) >= 500
    assert len({case.case_id for case in cases}) == len(cases)
    tags = {tag for case in cases for tag in case.tags}
    assert {
        "addressed_final",
        "final_release_holdout",
        "polite_final",
        "voice_final",
    } <= tags
    assert sum(case.critical for case in cases) >= 200


def test_held_out_routing_release_gate_passes() -> None:
    summary, records = evaluate()
    assert len(records) == summary["total_cases"]
    assert summary["overall_accuracy"] >= MIN_OVERALL_ACCURACY
    assert summary["critical_accuracy"] >= MIN_CRITICAL_ACCURACY
    assert summary["target_accuracy"] >= MIN_TARGET_ACCURACY
    assert summary["passed"] is True


def test_benchmark_detects_an_expected_route_regression() -> None:
    case = next(case for case in final_release_holdout_cases() if case.critical)
    broken = replace(case, expected_intent="definitely_wrong")
    summary, records = evaluate([broken])
    assert records[0]["intent_correct"] is False
    assert summary["passed"] is False


def test_development_corpus_retains_adversarial_categories() -> None:
    cases = held_out_cases()
    tags = {tag for case in cases for tag in case.tags}
    assert {"ambiguous", "compound", "followup", "typo", "voice_transcript"} <= tags
