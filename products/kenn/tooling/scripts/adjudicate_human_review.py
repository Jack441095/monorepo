#!/usr/bin/env python3
"""Validate and summarize two independent KENN human-review score files.

Reviewer files use this small format and must be created independently::

    {"reviews": [{"case_id": "...", "scores": {
        "intent_correctness": 2, "technical_correctness": 2,
        "evidence_use": 1, "ableton_practicality": 2,
        "uncertainty": 2, "citation_support": 2, "clarity": 2,
        "completeness": 1, "safety": 2, "overclaiming_control": 2
    }, "notes": "..."}]}

This tool validates completeness and calculates agreement; it does not invent
scores, adjudicate disagreements, or approve a release.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_PACKET = Path(__file__).resolve().parents[2] / "docs" / "ABLETON_ASSISTANT_HUMAN_REVIEW_PACKET_2026-09-08.json"
DEFAULT_RELEASE_THRESHOLDS = {
    "minimum_overall_combined_mean": 1.7,
    "minimum_critical_criterion_mean": 1.8,
    "critical_criteria": ["technical_correctness", "evidence_use", "safety", "overclaiming_control"],
    "minimum_category_combined_mean": 1.5,
}


class ReviewInputError(ValueError):
    """Raised when a packet or reviewer file is incomplete or malformed."""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_decision_template(
    *,
    packet_path: Path,
    reviewer_a_path: Path,
    reviewer_b_path: Path,
    case_count: int,
) -> dict[str, Any]:
    """Create a blank human decision bound to the exact reviewed inputs."""
    return {
        "schema": "kenn.human_review_decision.v1",
        "status": "pending_adjudication",
        "release_decision": None,
        "adjudicator_id": "",
        "disagreements_reviewed": False,
        "packet_sha256": file_sha256(packet_path),
        "reviewer_a_sha256": file_sha256(reviewer_a_path),
        "reviewer_b_sha256": file_sha256(reviewer_b_path),
        "case_count": int(case_count),
        "adjudicator_notes": "",
        "instructions": (
            "After reviewing disagreements and notes, set status to 'adjudicated' "
            "and release_decision to 'approved_for_internal_beta' or 'not_approved'."
        ),
    }


def _review_rows(data: Any, reviewer: str) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        rows = data.get("reviews")
    else:
        rows = data
    if not isinstance(rows, list):
        raise ReviewInputError(f"{reviewer}: expected a top-level 'reviews' list")
    if any(not isinstance(row, dict) for row in rows):
        raise ReviewInputError(f"{reviewer}: every review must be an object")
    return rows


def _reviewer_identity(data: Any, reviewer: str, expected_slot: str) -> str:
    if not isinstance(data, dict):
        raise ReviewInputError(f"{reviewer}: reviewer metadata is required")
    if data.get("schema") != "kenn.human_review_form.v1":
        raise ReviewInputError(f"{reviewer}: reviewer form schema is invalid")
    if str(data.get("reviewer_slot") or "").strip().casefold() != expected_slot:
        raise ReviewInputError(f"{reviewer}: reviewer_slot must be {expected_slot!r}")
    identity = str(data.get("reviewer_id") or "").strip()
    if not identity:
        raise ReviewInputError(f"{reviewer}: reviewer_id is required")
    if data.get("independent_review_confirmed") is not True:
        raise ReviewInputError(f"{reviewer}: independent review must be explicitly confirmed")
    return identity


def _validated_scores(packet: dict[str, Any], data: Any, reviewer: str) -> dict[str, dict[str, int]]:
    criteria = [str(item) for item in packet.get("criteria", [])]
    expected_ids = [str(case.get("case_id")) for case in packet.get("cases", []) if isinstance(case, dict)]
    if not criteria or not expected_ids or len(set(expected_ids)) != len(expected_ids):
        raise ReviewInputError("packet must contain unique case_id values and a non-empty criteria list")
    rows = _review_rows(data, reviewer)
    by_id: dict[str, dict[str, int]] = {}
    for row in rows:
        case_id = str(row.get("case_id") or "").strip()
        if case_id in by_id:
            raise ReviewInputError(f"{reviewer}: duplicate case_id {case_id!r}")
        scores = row.get("scores")
        if not case_id or not isinstance(scores, dict):
            raise ReviewInputError(f"{reviewer}: every row needs case_id and scores")
        if set(scores) != set(criteria):
            missing = sorted(set(criteria) - set(scores))
            extra = sorted(set(scores) - set(criteria))
            raise ReviewInputError(f"{reviewer}: {case_id!r} criteria mismatch; missing={missing}, extra={extra}")
        normalized: dict[str, int] = {}
        for criterion in criteria:
            value = scores[criterion]
            if isinstance(value, bool) or not isinstance(value, int) or value not in (0, 1, 2):
                raise ReviewInputError(f"{reviewer}: {case_id!r}/{criterion} must be an integer 0, 1, or 2")
            normalized[criterion] = value
        by_id[case_id] = normalized
    if set(by_id) != set(expected_ids):
        raise ReviewInputError(
            f"{reviewer}: case coverage mismatch; missing={sorted(set(expected_ids) - set(by_id))[:10]}, "
            f"unexpected={sorted(set(by_id) - set(expected_ids))[:10]}"
        )
    return by_id


def adjudicate(packet: dict[str, Any], reviewer_a: Any, reviewer_b: Any) -> dict[str, Any]:
    reviewer_a_id = _reviewer_identity(reviewer_a, "reviewer_a", "a")
    reviewer_b_id = _reviewer_identity(reviewer_b, "reviewer_b", "b")
    if reviewer_a_id.casefold() == reviewer_b_id.casefold():
        raise ReviewInputError("reviewer_a and reviewer_b must identify distinct reviewers")
    criteria = [str(item) for item in packet.get("criteria", [])]
    cases = [case for case in packet.get("cases", []) if isinstance(case, dict)]
    scores_a = _validated_scores(packet, reviewer_a, "reviewer_a")
    scores_b = _validated_scores(packet, reviewer_b, "reviewer_b")
    outcome_report = None
    if packet.get("schema") == "kenn_chat_human_review_packet.v2":
        digest = hashlib.sha256(json.dumps(packet, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        for form in (reviewer_a, reviewer_b):
            if form.get("packet_id") != packet.get("packet_id") or form.get("packet_content_sha256") != digest:
                raise ReviewInputError("Reviewer packet mismatch")
        outcome_report = review_progress(packet, reviewer_a, reviewer_b)
        if outcome_report["partial"] or outcome_report["unreviewed"]:
            raise ReviewInputError("Incomplete outcome reviews")
    categories = {str(case.get("case_id")): str(case.get("category") or "uncategorized") for case in cases}

    all_differences = []
    exact_cells = 0
    total_cells = len(scores_a) * len(criteria)
    per_criterion: dict[str, dict[str, float]] = {}
    category_values: dict[str, list[float]] = defaultdict(list)
    for case_id in scores_a:
        combined_case_values: list[float] = []
        for criterion in criteria:
            left = scores_a[case_id][criterion]
            right = scores_b[case_id][criterion]
            difference = abs(left - right)
            all_differences.append(difference)
            exact_cells += difference == 0
            combined = (left + right) / 2.0
            combined_case_values.append(combined)
            bucket = per_criterion.setdefault(criterion, {"reviewer_a_mean": 0.0, "reviewer_b_mean": 0.0, "combined_mean": 0.0, "exact_agreement_rate": 0.0})
            bucket["reviewer_a_mean"] += left
            bucket["reviewer_b_mean"] += right
            bucket["combined_mean"] += combined
            bucket["exact_agreement_rate"] += difference == 0
        category_values[categories[case_id]].append(statistics.mean(combined_case_values))

    for bucket in per_criterion.values():
        count = len(scores_a)
        bucket["reviewer_a_mean"] = round(bucket["reviewer_a_mean"] / count, 4)
        bucket["reviewer_b_mean"] = round(bucket["reviewer_b_mean"] / count, 4)
        bucket["combined_mean"] = round(bucket["combined_mean"] / count, 4)
        bucket["exact_agreement_rate"] = round(bucket["exact_agreement_rate"] / count, 4)
    category_summary = {
        category: {"cases": len(values), "combined_mean": round(statistics.mean(values), 4)}
        for category, values in sorted(category_values.items())
    }
    policy = packet.get("release_thresholds")
    using_default_policy = policy is None
    if using_default_policy:
        policy = DEFAULT_RELEASE_THRESHOLDS
    if not isinstance(policy, dict):
        raise ReviewInputError("packet release_thresholds must be an object")
    try:
        overall_floor = float(policy["minimum_overall_combined_mean"])
        critical_floor = float(policy["minimum_critical_criterion_mean"])
        category_floor = float(policy["minimum_category_combined_mean"])
        critical_criteria = [str(item) for item in policy["critical_criteria"]]
    except (KeyError, TypeError, ValueError) as exc:
        raise ReviewInputError("packet release_thresholds are incomplete or invalid") from exc
    if not 0 <= overall_floor <= 2 or not 0 <= critical_floor <= 2 or not 0 <= category_floor <= 2:
        raise ReviewInputError("packet release thresholds must be between 0 and 2")
    if using_default_policy:
        critical_criteria = [name for name in critical_criteria if name in criteria] or list(criteria)
    if not critical_criteria or not set(critical_criteria).issubset(criteria):
        raise ReviewInputError("packet critical criteria must be a non-empty subset of criteria")
    overall_mean = round(statistics.mean(
        bucket["combined_mean"] for bucket in per_criterion.values()
    ), 4)
    threshold_results = {
        "overall_combined_mean": overall_mean,
        "minimum_overall_combined_mean": overall_mean >= overall_floor,
        "minimum_critical_criterion_mean": all(
            per_criterion[name]["combined_mean"] >= critical_floor for name in critical_criteria
        ),
        "minimum_category_combined_mean": all(
            bucket["combined_mean"] >= category_floor for bucket in category_summary.values()
        ) and bool(category_summary),
    }
    threshold_results["qualified"] = all(
        value is True for key, value in threshold_results.items()
        if key != "overall_combined_mean"
    )
    if outcome_report:
        # Averaged scores cannot erase a wrong answer or an unresolved outcome disagreement.
        threshold_results["correctness_at_least_95_percent"] = outcome_report["correct"] / len(cases) >= 0.95
        threshold_results["zero_wrong"] = outcome_report["wrong"] == 0
        threshold_results["qualified"] &= threshold_results["correctness_at_least_95_percent"] and threshold_results["zero_wrong"] and outcome_report["disagreements"] == 0
    return {
        "schema": "kenn.human_review_adjudication.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "evidence_kind": "human_review",
        "status": "complete_for_adjudication",
        "human_review": "two independent score sets validated; adjudication and release decision still required",
        "case_count": len(scores_a),
        "criteria": criteria,
        "reviewers": ["reviewer_a", "reviewer_b"],
        "agreement": {
            "total_cells": total_cells,
            "exactly_agreeing_cells": exact_cells,
            "exact_agreement_rate": round(exact_cells / total_cells, 4) if total_cells else 0.0,
            "mean_absolute_difference": round(statistics.mean(all_differences), 4) if all_differences else 0.0,
        },
        "by_criterion": per_criterion,
        "by_category": category_summary,
        "outcomes": outcome_report,
        "release_threshold_policy": {
            "minimum_overall_combined_mean": overall_floor,
            "minimum_critical_criterion_mean": critical_floor,
            "critical_criteria": critical_criteria,
            "minimum_category_combined_mean": category_floor,
        },
        "thresholds": threshold_results,
        "limitations": [
            "Agreement statistics do not resolve disagreements or establish technical correctness.",
            "This report does not approve a release; an adjudicator must review notes and disagreements.",
        ],
    }


def review_progress(packet: dict, reviewer_a: dict, reviewer_b: dict) -> dict:
    """Count partial review without allowing an unfinished form to qualify."""
    maps = []
    digest = hashlib.sha256(json.dumps(packet, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    expected = [row["case_id"] for row in packet["cases"]]
    if len(set(expected)) != len(expected):
        raise ReviewInputError("Duplicate packet IDs")
    for form in (reviewer_a, reviewer_b):
        if packet.get("schema") == "kenn_chat_human_review_packet.v2" and (form.get("packet_id") != packet.get("packet_id") or form.get("packet_content_sha256") != digest):
            raise ReviewInputError("Reviewer packet mismatch")
        rows = _review_rows(form, "review progress")
        mapping = {}
        for row in rows:
            identity = row.get("case_id")
            scores = row.get("scores")
            if not isinstance(identity, str) or not isinstance(scores, dict) or set(scores) != set(packet["criteria"]):
                raise ReviewInputError("Review IDs and exact criteria are required")
            if any(value is not None and (type(value) is not int or value not in (0, 1, 2)) for value in scores.values()):
                raise ReviewInputError("Scores must be blank or integers 0, 1, 2")
            mapping[identity] = row
        if len(mapping) != len(rows) or not set(mapping).issubset(expected):
            raise ReviewInputError("Duplicate or foreign review IDs")
        maps.append(mapping)
    counts = {"denominator": len(expected), "correct": 0, "clarify": 0, "wrong": 0, "partial": 0, "unreviewed": 0, "disagreements": 0, "score_disagreements": 0, "by_family": {}}
    for case in packet["cases"]:
        reviews = [mapping.get(case["case_id"], {}) for mapping in maps]
        outcomes = [row.get("outcome") for row in reviews]
        complete_scores = [bool(row.get("scores")) and all(value is not None for value in row["scores"].values()) for row in reviews]
        has_score = any(value is not None for row in reviews for value in row.get("scores", {}).values())
        if any(outcome not in {None, "correct", "clarify", "wrong"} for outcome in outcomes):
            raise ReviewInputError("Outcome must be correct, clarify or wrong")
        if outcomes == [None, None] and not has_score:
            verdict = "unreviewed"
        elif None in outcomes or not all(complete_scores):
            verdict = "partial"
        elif outcomes[0] != outcomes[1]:
            verdict = "wrong" if "wrong" in outcomes else "clarify"
        else:
            verdict = outcomes[0]
        counts[verdict] += 1
        # Count disagreements even while other criteria remain blank; partial review still carries evidence.
        outcome_disagreement = bool(all(outcomes) and outcomes[0] != outcomes[1])
        score_disagreement = any(
            reviews[0].get("scores", {}).get(criterion) is not None
            and reviews[1].get("scores", {}).get(criterion) is not None
            and reviews[0]["scores"][criterion] != reviews[1]["scores"][criterion]
            for criterion in packet["criteria"]
        )
        counts["disagreements"] += outcome_disagreement
        counts["score_disagreements"] += score_disagreement
        family = str(case.get("category") or "uncategorized")
        bucket = counts["by_family"].setdefault(family, {"denominator": 0, "correct": 0, "clarify": 0, "wrong": 0, "partial": 0, "unreviewed": 0, "disagreements": 0, "score_disagreements": 0})
        bucket["denominator"] += 1
        bucket[verdict] += 1
        bucket["disagreements"] += outcome_disagreement
        bucket["score_disagreements"] += score_disagreement
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, default=DEFAULT_PACKET)
    parser.add_argument("--reviewer-a", type=Path, required=True)
    parser.add_argument("--reviewer-b", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--decision-template", type=Path)
    parser.add_argument("--progress", action="store_true", help="report unfinished outcomes without qualifying")
    args = parser.parse_args()
    if args.progress and args.decision_template:
        parser.error("An unfinished progress report cannot create an adjudication decision")
    try:
        packet = json.loads(args.packet.expanduser().read_text(encoding="utf-8"))
        reviewer_a = json.loads(args.reviewer_a.expanduser().read_text(encoding="utf-8"))
        reviewer_b = json.loads(args.reviewer_b.expanduser().read_text(encoding="utf-8"))
        expected_hash = file_sha256(args.packet.expanduser())
        for form in (reviewer_a, reviewer_b):
            if form.get("packet_sha256") != expected_hash:
                raise ReviewInputError("Reviewer file is bound to a different packet")
        result = review_progress(packet, reviewer_a, reviewer_b) if args.progress else adjudicate(packet, reviewer_a, reviewer_b)
    except (OSError, json.JSONDecodeError, ReviewInputError) as exc:
        parser.error(str(exc))
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.expanduser().resolve().write_text(rendered, encoding="utf-8")
    if args.decision_template:
        decision_path = args.decision_template.expanduser().resolve()
        if decision_path.exists():
            parser.error(f"refusing to overwrite existing decision template: {decision_path}")
        template = build_decision_template(
            packet_path=args.packet.expanduser().resolve(),
            reviewer_a_path=args.reviewer_a.expanduser().resolve(),
            reviewer_b_path=args.reviewer_b.expanduser().resolve(),
            case_count=result["case_count"],
        )
        decision_path.write_text(json.dumps(template, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
