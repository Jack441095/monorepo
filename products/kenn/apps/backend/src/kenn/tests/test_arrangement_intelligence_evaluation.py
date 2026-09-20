from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[5] / "tooling" / "scripts" / "evaluate_arrangement_intelligence.py"
module = importlib.util.module_from_spec(spec := importlib.util.spec_from_file_location("arrangement_intelligence_eval", SCRIPT))
assert spec.loader
spec.loader.exec_module(module)


def test_sealed_arrangement_intelligence_evaluation_passes() -> None:
    report = module.evaluate()

    assert report["schema"] == "kenn.arrangement_intelligence_evaluation.v1"
    assert report["all_cases_passed"] is True, report
    assert report["passed_case_count"] == report["case_count"] == 4
    assert report["execution_authorized"] is False
