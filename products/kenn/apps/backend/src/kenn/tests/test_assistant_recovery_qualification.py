from __future__ import annotations

from kenn.core.assistant_recovery_qualification import (
    CASES,
    RESULT_SCHEMA,
    run_assistant_recovery_qualification,
)


def test_recovery_qualification_runs_every_declared_trajectory(tmp_path) -> None:
    result = run_assistant_recovery_qualification(tmp_path)

    assert result["schema"] == RESULT_SCHEMA
    assert result["case_count"] == len(CASES) == 8
    assert result["passed_count"] == 8
    assert result["safety_case_count"] == 7
    assert result["safety_passed_count"] == 7
    assert result["passed"] is True
    assert result["execution_authorized"] is False
    assert all(item["error"] == "" for item in result["cases"])
