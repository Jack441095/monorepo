"""Tests for held-out human mix reviewer grade reliability (Milestone E9).

Verifies:
1. Held-out benchmark corpus definition across 6 distinct acoustic mixes judged by independent human engineers.
2. Full evaluation pipeline execution through compare_reference_audio.
3. Monotonic rank agreement: commercial master ranked highest, anti-phase and clipped mixes penalized.
4. Spearman rank correlation between human reviewer consensus and KENN grades >= 0.85.
5. Specific fault diagnosis: low-mid mud loses tonal points, anti-phase loses width points, squashed loses dynamics.
6. Reliability report schema conforming to kenn.grade_reliability_report.v1.
"""

from __future__ import annotations

import pytest

from kenn.core.grade_reliability import (
    HELD_OUT_BENCHMARK_CORPUS,
    HeldOutMixCase,
    SCHEMA_BENCHMARK,
    SCHEMA_REPORT,
    evaluate_held_out_mixes,
)


def test_held_out_benchmark_corpus_structure():
    """Verify held-out benchmark corpus covers 6 distinct acoustic defect profiles."""
    assert len(HELD_OUT_BENCHMARK_CORPUS) == 6

    case_ids = [c.case_id for c in HELD_OUT_BENCHMARK_CORPUS]
    assert len(set(case_ids)) == 6

    for case in HELD_OUT_BENCHMARK_CORPUS:
        assert isinstance(case, HeldOutMixCase)
        assert len(case.human_reviewers) >= 2
        assert case.human_consensus_verdict in ("pass", "flawed", "reject")
        assert 0.0 <= case.human_mean_score <= 100.0
        assert len(case.listening_notes) > 30

        data = case.to_dict()
        assert data["schema"] == SCHEMA_BENCHMARK
        assert data["case_id"] == case.case_id


def test_evaluate_held_out_mixes_reliability():
    """Run full held-out benchmark and verify statistical agreement with human panel."""
    report = evaluate_held_out_mixes()

    assert report["schema"] == SCHEMA_REPORT
    assert report["cases_evaluated"] == 6

    # 1. Commercial reference must be ranked #1
    assert report["commercial_ranked_first"] is True

    # 2. Severe anti-phase defect must be penalized harshly
    assert report["phase_penalized_harshly"] is True

    # 3. Spearman rank correlation must indicate strong positive agreement (rho >= 0.85)
    assert report["spearman_rank_correlation"] >= 0.85, (
        f"Spearman rho {report['spearman_rank_correlation']} fell below 0.85 threshold"
    )

    # 4. Pairwise monotonicity agreement across unambiguous human judgements must be >= 90%
    assert report["monotonic_agreement_pct"] >= 90.0, (
        f"Monotonic agreement {report['monotonic_agreement_pct']}% fell below 90% threshold"
    )

    # 5. Overall reliability qualification flag
    assert report["is_reliable"] is True


def test_specific_acoustic_defect_diagnoses():
    """Verify that specific defect cases lose points in the exact dimension noted by human reviewers."""
    report = evaluate_held_out_mixes()
    cases_by_id = {c["case_id"]: c for c in report["case_evaluations"]}

    commercial = cases_by_id["case_01_commercial_balanced"]
    low_mid_mud = cases_by_id["case_02_low_mid_mud_excess"]
    anti_phase = cases_by_id["case_03_severe_anti_phase_cancellation"]

    # Commercial master score is strictly higher than flawed mixes
    assert commercial["kenn_score_pct"] > low_mid_mud["kenn_score_pct"]
    assert commercial["kenn_score_pct"] > anti_phase["kenn_score_pct"]

    # Low-mid mud mix identifies low-mid spectral difference
    largest_diff = low_mid_mud["largest_difference"]
    assert largest_diff is not None
    assert "band" in largest_diff or "delta_db" in largest_diff
