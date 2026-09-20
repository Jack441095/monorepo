#!/usr/bin/env python3
"""Evaluate Relationship v1 decision safety separately from perceptual mix quality."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "audio_analysis"))

from audio_analysis.mixdown.musical_roles import infer_musical_roles  # noqa: E402
from audio_analysis.mixdown.arrangement import infer_arrangement  # noqa: E402
from audio_analysis.mixdown.relationships import infer_relationships  # noqa: E402
from audio_analysis.mixdown.stem_classifier import StemProfile  # noqa: E402

DEFAULT_CASES = (
    ROOT / "studio" / "audio_analysis" / "audio_analysis" / "evals" /
    "relationship_cases.json"
)


def _profile(payload: dict) -> StemProfile:
    return StemProfile(
        name=payload["name"],
        instrument=payload["instrument"],
        classification_confidence=float(payload["confidence"]),
        classification_method="labelled_eval_fixture",
        sample_rate=1_000,
    )


def _run_case(case: dict) -> list:
    profiles = [_profile(case["first"]), _profile(case["second"])]
    roles = infer_musical_roles(profiles, [])
    ratio = float(case["coactivity"])
    sections = []
    if ratio > 0.0:
        sections.append({
            "section_id": "section-001",
            "start_seconds": 0.0,
            "end_seconds": ratio * 10.0,
            "active_stems": [profile.name for profile in profiles],
        })
    if ratio < 1.0:
        sections.append({
            "section_id": "section-002",
            "start_seconds": ratio * 10.0,
            "end_seconds": 10.0,
            "active_stems": [profiles[0].name],
        })
    first_key = Path(profiles[0].name).stem
    second_key = Path(profiles[1].name).stem
    score = float(case["masking"])
    masking = {"masking_matrix": {
        first_key: {second_key: score},
        second_key: {first_key: score},
    }}
    dynamics = {}
    if treatment := case.get("existing_dynamics"):
        dynamics[treatment["target"]] = {
            "sidechain_detected": True,
            "sidechain_trigger": treatment["trigger"],
            "sidechain_correlation": 0.9,
            "sidechain_mean_dip_db": 8.0,
        }
    return infer_relationships(
        profiles,
        masking,
        roles,
        {"sections": sections},
        existing_dynamics=dynamics,
    )


def _run_group_case(case: dict) -> list:
    sample_rate = 8_000
    window_samples = sample_rate // 2
    profiles = []
    prepared = []
    for stem in case["stems"]:
        profile = StemProfile(
            name=stem["name"],
            instrument=stem["instrument"],
            classification_confidence=0.95,
            classification_method="labelled_eval_fixture",
            sample_rate=sample_rate,
        )
        profiles.append(profile)
        samples = np.zeros(window_samples * 4, dtype=np.float64)
        for window in stem["active_windows"]:
            start = int(window) * window_samples
            time = np.arange(window_samples, dtype=np.float64) / sample_rate
            samples[start:start + window_samples] = (
                0.4 * np.sin(2.0 * np.pi * float(stem["frequency_hz"]) * time)
            )
        prepared.append({
            "name": stem["name"], "samples": samples.tolist(), "sample_rate": sample_rate,
        })
    roles = infer_musical_roles(profiles, prepared)
    arrangement = infer_arrangement(prepared).to_dict()
    return [
        relationship
        for relationship in infer_relationships(profiles, {}, roles, arrangement, prepared)
        if relationship.relationship_type == "cumulative_spectral_buildup"
    ]


def evaluate_cases(path: Path = DEFAULT_CASES) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    results = []
    for case in payload.get("cases", []):
        found = _run_case(case)
        relationship = found[0] if found else None
        emitted = relationship is not None
        actionable = bool(relationship and relationship.intervention_order)
        checks = {
            "emitted": emitted is bool(case["expected_emitted"]),
            "actionable": actionable is bool(case["expected_actionable"]),
        }
        if relationship:
            checks.update({
                "single_relationship": len(found) == 1,
                "status": relationship.status == case["expected_status"],
                "protected_stem": relationship.protected_stem == case.get("expected_protected"),
                "intervention_target": relationship.intervention_target == case.get("expected_target"),
                "advisory_only": relationship.applies_automatically is False,
            })
            if case["expected_actionable"]:
                checks.update({
                    "multiple_candidates": len(relationship.candidate_strategies) >= 3,
                    "candidates_ranked": [
                        candidate.score for candidate in relationship.candidate_strategies
                    ] == sorted(
                        (candidate.score for candidate in relationship.candidate_strategies),
                        reverse=True,
                    ),
                    "candidates_advisory_only": all(
                        candidate.applies_automatically is False
                        for candidate in relationship.candidate_strategies
                    ),
                    "selection_explained": bool(relationship.selection_rationale),
                })
            else:
                checks["no_processor_candidates"] = not relationship.candidate_strategies
        results.append({
            "id": case["id"],
            "passed": all(checks.values()),
            "checks": checks,
            "actual": relationship.to_dict() if relationship else None,
        })
    for case in payload.get("group_cases", []):
        found = _run_group_case(case)
        expected = bool(case["expected_group"])
        relationship = found[0] if found else None
        checks = {
            "group_emitted": bool(found) is expected,
            "single_group": len(found) == 1 if expected else len(found) == 0,
        }
        if relationship:
            checks.update({
                "protected_stem": relationship.protected_stem == case.get("expected_protected"),
                "review_only": relationship.status == "review_required",
                "no_target": relationship.intervention_target is None,
                "no_candidates": not relationship.candidate_strategies,
                "advisory_only": relationship.applies_automatically is False,
            })
        results.append({
            "id": case["id"],
            "passed": all(checks.values()),
            "checks": checks,
            "actual": relationship.to_dict() if relationship else None,
        })
    total = len(results)
    passed = sum(result["passed"] for result in results)
    return {
        "schema": "audio-too.relationship-eval-report.v1",
        "case_schema": payload.get("schema"),
        "scope": payload.get("scope"),
        "summary": {
            "cases": total,
            "passed": passed,
            "exact_contract_accuracy": passed / total if total else 0.0,
        },
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = evaluate_cases(args.cases)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["summary"]["exact_contract_accuracy"] == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
