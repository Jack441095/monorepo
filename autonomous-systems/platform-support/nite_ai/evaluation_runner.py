"""Deterministic evaluation runner (Phase 5C).

Executes EvaluationSuites against a caller-supplied deterministic evaluator
function. No LLM judge, no network, structured export.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from nite_ai._serialization import dataclass_to_dict
from nite_ai.evaluation import (
    EvaluationCase,
    EvaluationResult,
    EvaluationSuite,
    ObservedOutcome,
)


Evaluator = Callable[[EvaluationCase], ObservedOutcome]


@dataclass(frozen=True)
class SuiteRunReport:
    suite_id: str
    total: int
    passed: int
    failed: int
    duration_ms: float
    results: tuple[EvaluationResult, ...]

    @property
    def all_passed(self) -> bool:
        return self.failed == 0 and self.total > 0

    def to_dict(self) -> dict:
        return dataclass_to_dict(self)

    def export_json(self, sort_keys: bool = True) -> str:
        import json

        return json.dumps(self.to_dict(), sort_keys=sort_keys)


def run_suite(suite: EvaluationSuite, evaluator: Evaluator) -> SuiteRunReport:
    results: list[EvaluationResult] = []
    started = time.perf_counter()
    for case in suite.cases:
        try:
            observed = evaluator(case)
        except Exception as exc:  # evaluator crash == failed case, never aborts the run
            results.append(
                EvaluationResult(
                    case_id=case.case_id,
                    passed=False,
                    failure_reason=f"evaluator error: {exc}",
                )
            )
            continue
        results.append(case.evaluate(observed))
    duration_ms = (time.perf_counter() - started) * 1000.0
    passed = sum(1 for r in results if r.passed)
    return SuiteRunReport(
        suite_id=suite.suite_id,
        total=len(results),
        passed=passed,
        failed=len(results) - passed,
        duration_ms=duration_ms,
        results=tuple(results),
    )


def meets_threshold(report: SuiteRunReport, min_pass_ratio: float) -> bool:
    if report.total == 0:
        return False
    return (report.passed / report.total) >= min_pass_ratio


__all__ = ["Evaluator", "SuiteRunReport", "meets_threshold", "run_suite"]
