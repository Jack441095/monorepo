"""Captured delivery verdicts must never become invented human correctness grades."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "tooling/scripts"))
from adjudicate_human_review import ReviewInputError, adjudicate, review_progress
import build_human_review_packet
from build_captured_review_packet import CRITERIA, RELEASE_THRESHOLDS, build_captured
from export_human_review_forms import build_form


def capture():
    return {"schema": "kenn.answer_capture.v1", "provenance": {"model_digest": "synthetic", "source_revision": "fixture"},
            "cases": [{"case_id": f"private-{outcome}", "question": f"Synthetic question {outcome}", "answer": "Synthetic answer",
                       "family": "units", "split": "regression", "delivery": outcome, "evidence": [], "candidate_available": outcome == "accepted"}
                      for outcome in ("accepted", "rejected", "busy", "timeout", "not_attempted")]}


def forms(packet):
    result = [build_form(packet, reviewer_slot=slot, packet_sha256="fixture") for slot in ("a", "b")]
    for slot, form in zip(("a", "b"), result):
        form.update(reviewer_id=f"synthetic-{slot}", independent_review_confirmed=True)
    return result


def test_offline_blinding_preserves_every_delivery_without_exposing_the_key():
    # Accepted/rejected labels bias reviewers; every denominator stays in the separate private key.
    packet, key = build_captured(capture())
    assert packet["human_review"] == "pending" and len(packet["cases"]) == 5
    assert {row["capture"]["delivery"] for row in key["cases"]} == {"accepted", "rejected", "busy", "timeout", "not_attempted"}
    visible = json.dumps(packet)
    assert "model_digest" not in visible and "private-" not in visible and '"delivery"' not in visible
    left, right = forms(packet)
    assert left["reviews"][0]["scores"] == {criterion: None for criterion in packet["criteria"]}
    assert left["reviews"][0]["outcome"] is None
    report = review_progress(packet, left, right)
    assert report["denominator"] == report["unreviewed"] == report["by_family"]["units"]["denominator"] == 5
    assert report["correct"] == 0


@pytest.mark.parametrize("fault", ["duplicate", "build", "split", "missing", "malformed"])
def test_incompatible_or_incomplete_captures_cannot_be_blinded(fault):
    data = capture()
    if fault == "duplicate":
        data["cases"][1]["case_id"] = data["cases"][0]["case_id"]
    elif fault == "build":
        data["cases"][1]["provenance"] = {"source_revision": "different"}
    elif fault == "split":
        data["cases"][1]["split"] = "sealed"
    elif fault == "missing":
        del data["cases"][1]["answer"]
    else:
        data["cases"][1] = None
    with pytest.raises(ValueError):
        build_captured(data)


def test_outcomes_with_blank_scores_are_partial_and_cannot_qualify():
    packet, _ = build_captured(capture())
    left, right = forms(packet)
    for form in (left, right):
        for row in form["reviews"]:
            row["outcome"] = "correct"
    assert review_progress(packet, left, right)["partial"] == 5
    with pytest.raises(ReviewInputError):
        adjudicate(packet, left, right)


def test_accepted_but_wrong_answer_and_disagreement_remain_wrong():
    packet, key = build_captured(capture())
    accepted_id = next(row["case_id"] for row in key["cases"] if row["capture"]["delivery"] == "accepted")
    left, right = forms(packet)
    for form in (left, right):
        for row in form["reviews"]:
            row["scores"] = {criterion: 2 for criterion in packet["criteria"]}
            row["outcome"] = "correct"
    next(row for row in left["reviews"] if row["case_id"] == accepted_id)["outcome"] = "wrong"
    report = adjudicate(packet, left, right)
    assert report["outcomes"]["wrong"] == report["outcomes"]["disagreements"] == 1
    assert report["outcomes"]["by_family"]["units"]["correct"] == 4
    assert report["thresholds"]["qualified"] is False


def test_partial_review_keeps_outcome_and_score_disagreements_in_each_family():
    # A disagreement must not disappear because the reviewers left another criterion blank.
    packet, _ = build_captured(capture())
    left, right = forms(packet)
    left["reviews"][0]["outcome"] = "wrong"
    right["reviews"][0]["outcome"] = "correct"
    criterion = packet["criteria"][0]
    left["reviews"][0]["scores"][criterion] = 0
    right["reviews"][0]["scores"][criterion] = 2
    report = review_progress(packet, left, right)
    assert report["partial"] == report["disagreements"] == report["score_disagreements"] == 1
    assert report["by_family"]["units"]["score_disagreements"] == 1


@pytest.mark.parametrize("fault", ["packet", "content", "duplicate", "foreign", "malformed"])
def test_partial_reports_reject_foreign_or_malformed_forms(fault):
    packet, _ = build_captured(capture())
    left, right = forms(packet)
    if fault == "packet":
        right["packet_id"] = "another"
    elif fault == "content":
        packet["cases"][0]["response"]["answer"] = "changed after export"
    elif fault == "duplicate":
        right["reviews"].append(copy.deepcopy(right["reviews"][0]))
    elif fault == "foreign":
        right["reviews"][0]["case_id"] = "foreign"
    else:
        right["reviews"][0] = None
    with pytest.raises(ReviewInputError):
        review_progress(packet, left, right)


def test_captured_packets_are_scored_on_the_same_criteria_and_bars_as_the_chat_packet():
    # The captured builder keeps its own copy so it never imports the engine; this is what stops the copies drifting.
    assert CRITERIA == build_human_review_packet.CRITERIA
    assert RELEASE_THRESHOLDS == build_human_review_packet.RELEASE_THRESHOLDS
