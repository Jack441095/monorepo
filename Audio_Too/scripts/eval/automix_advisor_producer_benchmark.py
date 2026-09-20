#!/usr/bin/env python3
"""Benchmark the deterministic, retrieval-grounded AutoMix advisor producer."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
AUDIO_ANALYSIS_ROOT = ROOT / "studio" / "audio_analysis"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(AUDIO_ANALYSIS_ROOT) not in sys.path:
    sys.path.insert(0, str(AUDIO_ANALYSIS_ROOT))

from audio_analysis.integration.kenn_advisor import (  # noqa: E402
    evaluate_supplied_proposal_shadow,
    get_kenn_adjustments,
)
from audio_analysis.mixdown.mix_decision_engine import generate_mix_plan  # noqa: E402
from audio_analysis.mixdown.stem_classifier import StemProfile  # noqa: E402

REPORT_SCHEMA = "audio-too.kenn-advisor-producer-benchmark/v1"
_MUTATION_KEYS = {"stem_id", "gain_offset_db", "compressor_ratio"}


def _profiles(raw: Any) -> list[StemProfile]:
    if not isinstance(raw, list) or not raw:
        raise ValueError("profiles must be a non-empty list")
    allowed = {item.name for item in fields(StemProfile)}
    result = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"profiles[{index}] must be an object")
        unknown = set(item) - allowed
        if unknown:
            raise ValueError(f"profiles[{index}] has unknown keys: {sorted(unknown)}")
        result.append(StemProfile(**item))
    return result


def _mutate_plan(plan, mutations: Any) -> None:
    if not isinstance(mutations, list):
        raise ValueError("mutations must be a list")
    stems = {stem.stem_name: stem for stem in plan.stems}
    for index, mutation in enumerate(mutations):
        if not isinstance(mutation, dict) or set(mutation) - _MUTATION_KEYS:
            raise ValueError(f"mutations[{index}] is malformed")
        stem_id = str(mutation.get("stem_id", ""))
        if stem_id not in stems:
            raise ValueError(f"mutations[{index}] names unknown stem {stem_id!r}")
        stem = stems[stem_id]
        if "gain_offset_db" in mutation:
            stem.gain_db += float(mutation["gain_offset_db"])
        if "compressor_ratio" in mutation:
            if stem.compressor is None:
                raise ValueError(f"mutations[{index}] targets a missing compressor")
            stem.compressor["ratio"] = float(mutation["compressor_ratio"])


def _operation_signature(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, dict):
        return []
    return [
        {
            "stem_id": operation["stem_id"],
            "operation": operation["operation"],
            "value": float(operation["value"]),
            "evidence_source_ids": list(operation["evidence_source_ids"]),
        }
        for operation in raw.get("operations", [])
    ]


def _matches_expected(actual: list[dict], expected: Any) -> bool:
    if not isinstance(expected, list) or len(actual) != len(expected):
        return False
    actual_by_key = {(item["stem_id"], item["operation"]): item for item in actual}
    for item in expected:
        key = (item.get("stem_id"), item.get("operation"))
        candidate = actual_by_key.get(key)
        if candidate is None or abs(candidate["value"] - float(item["value"])) > 1e-3:
            return False
        source_prefix = str(item.get("evidence_source_prefix", ""))
        if source_prefix and not all(
            source_id.startswith(source_prefix) for source_id in candidate["evidence_source_ids"]
        ):
            return False
    return True


def run_benchmark(cases: list[dict[str, Any]]) -> dict[str, Any]:
    results = []
    for index, case in enumerate(cases):
        case_id = str(case.get("id", "")).strip()
        if not case_id:
            raise ValueError(f"cases[{index}].id must be non-empty")
        genre = str(case.get("genre", "pop"))
        target_lufs = float(case.get("target_lufs", -14.0))
        profiles = _profiles(case.get("profiles"))
        plan = generate_mix_plan(
            profiles,
            masking_results=None,
            genre=genre,
            target_lufs=target_lufs,
        )
        _mutate_plan(plan, case.get("mutations", []))
        correlation_id = f"automix-producer-benchmark:{case_id}"
        proposal = get_kenn_adjustments(
            plan,
            profiles,
            genre,
            target_lufs,
            correlation_id=correlation_id,
        )
        receipt = evaluate_supplied_proposal_shadow(
            plan,
            proposal,
            correlation_id=correlation_id,
        )
        actual = _operation_signature(proposal)
        expected_status = str(case.get("expected_status", ""))
        status_match = receipt["status"] == expected_status
        operations_match = _matches_expected(actual, case.get("expected_operations", []))
        results.append(
            {
                "id": case_id,
                "genre": genre,
                "status": receipt["status"],
                "expected_status": expected_status,
                "status_match": status_match,
                "operations_match": operations_match,
                "passed": status_match and operations_match,
                "operations": actual,
                "rejection_reason": receipt["rejection_reason"],
                "latency_ms": receipt["latency_ms"],
            }
        )
    proposal_results = [item for item in results if item["status"] != "no_proposal"]
    return {
        "schema": REPORT_SCHEMA,
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": {
            "cases": len(results),
            "passed": sum(item["passed"] for item in results),
            "pass_rate": sum(item["passed"] for item in results) / len(results),
            "proposals": len(proposal_results),
            "schema_valid_rate": (
                sum(item["status"] == "valid" for item in proposal_results)
                / len(proposal_results)
                if proposal_results
                else None
            ),
            "provider_errors": sum(item["status"] == "provider_error" for item in results),
            "unexpected_rejections": sum(item["status"] == "rejected" for item in results),
        },
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.suite.read_text(encoding="utf-8"))
    cases = payload.get("cases") if isinstance(payload, dict) else None
    if not isinstance(cases, list) or not cases:
        raise ValueError("suite must contain a non-empty cases list")
    report = run_benchmark(cases)
    rendered = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return int(report["summary"]["pass_rate"] < 1.0)


if __name__ == "__main__":
    raise SystemExit(main())
