"""Labelled Relationship v1 decision-safety gate."""

from scripts.eval.relationship_eval import DEFAULT_CASES, evaluate_cases


def test_labelled_relationship_decision_contract_is_exact() -> None:
    report = evaluate_cases(DEFAULT_CASES)

    assert report["case_schema"] == "audio-too.relationship-eval.v1"
    assert report["summary"]["cases"] >= 10
    assert report["summary"]["exact_contract_accuracy"] == 1.0
    assert "not perceptual magnitude validation" in report["scope"]
    assert all(result["passed"] for result in report["results"])
