from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "tooling" / "scripts"))

import pytest

from adjudicate_human_review import ReviewInputError, adjudicate, build_decision_template, file_sha256


CRITERIA = ["intent_correctness", "technical_correctness"]
PACKET = {
    "criteria": CRITERIA,
    "cases": [
        {"case_id": "one", "category": "production"},
        {"case_id": "two", "category": "adversarial"},
    ],
}


def _review(value: int, reviewer_id: str, reviewer_slot: str | None = None) -> dict:
    return {
        "schema": "kenn.human_review_form.v1",
        "reviewer_slot": reviewer_slot or ("a" if reviewer_id.endswith("a") else "b"),
        "reviewer_id": reviewer_id,
        "independent_review_confirmed": True,
        "reviews": [
            {"case_id": "one", "scores": {criterion: value for criterion in CRITERIA}},
            {"case_id": "two", "scores": {criterion: value for criterion in CRITERIA}},
        ]
    }


def test_adjudicator_reports_complete_agreement_and_categories() -> None:
    result = adjudicate(PACKET, _review(2, "engineer-a"), _review(2, "engineer-b"))
    assert result["status"] == "complete_for_adjudication"
    assert result["agreement"]["exact_agreement_rate"] == 1.0
    assert result["by_category"]["production"]["combined_mean"] == 2.0
    assert result["thresholds"]["qualified"] is True


def test_adjudicator_fails_quality_thresholds_for_low_scores() -> None:
    result = adjudicate(PACKET, _review(1, "engineer-a"), _review(1, "engineer-b"))
    assert result["thresholds"]["qualified"] is False
    assert result["thresholds"]["overall_combined_mean"] == 1.0


def test_adjudicator_rejects_incomplete_case_coverage() -> None:
    with pytest.raises(ReviewInputError, match="case coverage mismatch"):
        adjudicate(
            PACKET,
            {"schema": "kenn.human_review_form.v1", "reviewer_slot": "a",
             "reviewer_id": "engineer-a", "independent_review_confirmed": True, "reviews": []},
            _review(2, "engineer-b"),
        )


def test_adjudicator_rejects_unconfirmed_or_duplicate_reviewers() -> None:
    unconfirmed = _review(2, "engineer-a")
    unconfirmed["independent_review_confirmed"] = False
    with pytest.raises(ReviewInputError, match="explicitly confirmed"):
        adjudicate(PACKET, unconfirmed, _review(2, "engineer-b"))

    with pytest.raises(ReviewInputError, match="distinct reviewers"):
        adjudicate(PACKET, _review(2, "same-person", "a"), _review(2, "SAME-PERSON", "b"))

    with pytest.raises(ReviewInputError, match="reviewer_slot"):
        adjudicate(PACKET, _review(2, "engineer-a", "b"), _review(2, "engineer-b", "a"))


def test_decision_template_is_blank_and_bound_to_exact_inputs(tmp_path: Path) -> None:
    packet = tmp_path / "packet.json"
    reviewer_a = tmp_path / "reviewer-a.json"
    reviewer_b = tmp_path / "reviewer-b.json"
    packet.write_text("packet", encoding="utf-8")
    reviewer_a.write_text("review a", encoding="utf-8")
    reviewer_b.write_text("review b", encoding="utf-8")

    decision = build_decision_template(
        packet_path=packet,
        reviewer_a_path=reviewer_a,
        reviewer_b_path=reviewer_b,
        case_count=2,
    )

    assert decision["status"] == "pending_adjudication"
    assert decision["release_decision"] is None
    assert decision["adjudicator_id"] == ""
    assert decision["disagreements_reviewed"] is False
    assert decision["packet_sha256"] == file_sha256(packet)
    assert decision["reviewer_a_sha256"] == file_sha256(reviewer_a)
    assert decision["reviewer_b_sha256"] == file_sha256(reviewer_b)
