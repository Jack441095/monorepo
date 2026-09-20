#!/usr/bin/env python3
"""Evaluate MusicalRole v1 separately from downstream mix quality."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "audio_analysis"))

from audio_analysis.mixdown.musical_roles import infer_musical_role  # noqa: E402
from audio_analysis.mixdown.stem_classifier import StemProfile  # noqa: E402

DEFAULT_CASES = (
    ROOT / "studio" / "audio_analysis" / "audio_analysis" / "evals" /
    "musical_role_cases.json"
)


def evaluate_cases(path: Path = DEFAULT_CASES) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases", [])
    results = []
    for case in cases:
        profile = StemProfile(
            name=case["name"],
            instrument=case["instrument"],
            classification_confidence=float(case["confidence"]),
            classification_method="labelled_eval_fixture",
            sample_rate=1_000,
        )
        prepared = None
        if "total_windows" in case:
            samples = []
            active = set(case.get("active_windows", []))
            for index in range(int(case["total_windows"])):
                samples.extend(([0.5] if index in active else [0.0]) * 500)
            prepared = {"name": case["name"], "samples": samples, "sample_rate": 1_000}
        role = infer_musical_role(profile, prepared)
        checks = {
            "role": role.role == case["expected_role"],
            "priority": role.priority == case["expected_priority"],
            "ambiguous": role.ambiguous is bool(case["expected_ambiguous"]),
        }
        results.append({
            "id": case["id"],
            "passed": all(checks.values()),
            "checks": checks,
            "actual": role.to_dict(),
        })
    total = len(results)
    passed = sum(result["passed"] for result in results)
    return {
        "schema": "audio-too.musical-role-eval-report.v1",
        "case_schema": payload.get("schema"),
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
