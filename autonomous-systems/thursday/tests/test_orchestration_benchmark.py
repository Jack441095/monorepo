"""thursday/evals/orchestration_benchmark.py — THURSDAY_ORCHESTRATION_V1,
the V2-D control-plane benchmark (docs/THURSDAY_ORCHESTRATION_BENCHMARK_V1
.md). Runs standalone (confirmed in docs/EXTRACTION_COUPLING.md's clean-
checkout receipt); this pins that it actually passes, not just imports,
and that the NITE_DSP_ROOT-parameterised workspace path (fixed alongside
the extraction's indentation bug) doesn't break CompanyOrchestrator's
decomposition logic.
"""

from __future__ import annotations

from thursday.evals.orchestration_benchmark import run_benchmark


def test_run_benchmark_passes_standalone() -> None:
    scorecard = run_benchmark()
    assert scorecard["passed"] is True
    assert scorecard["schema"] == "thursday.orchestration_benchmark.v1"


def test_run_benchmark_routing_is_perfect() -> None:
    scorecard = run_benchmark()
    assert scorecard["routing_accuracy"] == 1.0
    assert scorecard["critical_misroutes"] == 0


def test_run_benchmark_decomposition_and_cycle_detection() -> None:
    scorecard = run_benchmark()
    assert scorecard["decomposition_accuracy"] == 1.0
    assert scorecard["critical_task_omissions"] == 0
    assert scorecard["cycle_detection"] == "PASS"
    assert scorecard["dependency_correctness"] == 1.0


def test_run_benchmark_no_security_violations() -> None:
    scorecard = run_benchmark()
    assert scorecard["forbidden_mutations"] == 0
    assert scorecard["ambiguous_ownership_mutations"] == 0
    assert scorecard["unsupported_accepted_claims"] == 0
    assert scorecard["stale_evidence_accepted"] == 0
    assert scorecard["injection_attacks_accepted"] == 0
    assert scorecard["duplicate_side_effects"] == 0
