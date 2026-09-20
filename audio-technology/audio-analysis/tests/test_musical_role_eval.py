"""Labelled MusicalRole evaluation-gate tests."""

from scripts.eval.musical_role_eval import DEFAULT_CASES, evaluate_cases


def test_labelled_role_contract_gate_is_complete_and_exact() -> None:
    report = evaluate_cases(DEFAULT_CASES)

    assert report["case_schema"] == "audio-too.musical-role-eval.v1"
    assert report["summary"]["cases"] >= 16
    assert report["summary"]["exact_contract_accuracy"] == 1.0
    assert all(result["passed"] for result in report["results"])
