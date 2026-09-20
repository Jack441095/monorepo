#!/usr/bin/env python3
"""Offline replay and scoring for anonymized KENN advisor cases."""

from __future__ import annotations

import argparse
import json
import statistics
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
    SHADOW_RECEIPT_SCHEMA,
    evaluate_supplied_proposal_shadow,
)
from audio_analysis.mixdown.mix_decision_engine import (  # noqa: E402
    BusMixConfig,
    MixPlan,
    StemMixConfig,
)

REPLAY_SCHEMA = "audio-too.kenn-advisor-replay/v1"
_RATING_FIELDS = ("usefulness", "audible_improvement", "explanation_quality")


def _strict_dataclass(cls, raw: Any, field: str):
    if not isinstance(raw, dict):
        raise ValueError(f"{field} must be an object")
    allowed = {item.name for item in fields(cls)}
    unknown = set(raw) - allowed
    if unknown:
        raise ValueError(f"{field} has unknown keys: {sorted(unknown)}")
    return cls(**raw)


def plan_from_dict(raw: Any) -> MixPlan:
    if not isinstance(raw, dict):
        raise ValueError("plan must be an object")
    allowed = {item.name for item in fields(MixPlan)}
    if set(raw) - allowed:
        raise ValueError(f"plan has unknown keys: {sorted(set(raw) - allowed)}")
    stems_raw = raw.get("stems")
    if not isinstance(stems_raw, list) or not stems_raw:
        raise ValueError("plan.stems must be a non-empty list")
    stems = [_strict_dataclass(StemMixConfig, item, "plan.stems[]") for item in stems_raw]
    bus = _strict_dataclass(BusMixConfig, raw.get("bus"), "plan.bus")
    return MixPlan(
        stems=stems,
        bus=bus,
        genre=str(raw.get("genre", "")),
        target_lufs=float(raw.get("target_lufs")),
        mix_goal=str(raw.get("mix_goal", "premaster")),
        decisions_log=list(raw.get("decisions_log", [])),
        musical_roles=list(raw.get("musical_roles", [])),
        arrangement=dict(raw.get("arrangement", {})),
        relationships=list(raw.get("relationships", [])),
        automation_preview=dict(raw.get("automation_preview", {})),
    )


def load_cases(path: Path) -> list[dict[str, Any]]:
    if path.suffix == ".jsonl":
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("cases") if isinstance(payload, dict) else payload
    if not isinstance(rows, list) or not rows:
        raise ValueError("replay input must contain at least one case")
    return rows


def _ratings(raw: Any) -> dict[str, float]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("human_ratings must be an object")
    unknown = set(raw) - set(_RATING_FIELDS)
    if unknown:
        raise ValueError(f"human_ratings has unknown keys: {sorted(unknown)}")
    result = {}
    for field in _RATING_FIELDS:
        if field not in raw:
            continue
        value = float(raw[field])
        if not 1.0 <= value <= 5.0:
            raise ValueError(f"human_ratings.{field} must be between 1 and 5")
        result[field] = value
    return result


def replay_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    results = []
    ratings: dict[str, list[float]] = {field: [] for field in _RATING_FIELDS}
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f"cases[{index}] must be an object")
        case_id = str(case.get("id", "")).strip()
        if not case_id:
            raise ValueError(f"cases[{index}].id must be non-empty")
        plan = plan_from_dict(case.get("plan"))
        correlation_id = str(case.get("correlation_id") or f"automix-replay:{case_id}")
        bands_raw = case.get("stem_bands_hz") or {}
        stem_bands = {key: (float(value[0]), float(value[1])) for key, value in bands_raw.items()}
        receipt = evaluate_supplied_proposal_shadow(
            plan,
            case.get("proposal"),
            correlation_id=correlation_id,
            stem_bands_hz=stem_bands,
        )
        expected_status = case.get("expected_status")
        expectation_met = expected_status is None or receipt["status"] == expected_status
        case_ratings = _ratings(case.get("human_ratings"))
        for field, value in case_ratings.items():
            ratings[field].append(value)
        results.append(
            {
                "id": case_id,
                "status": receipt["status"],
                "expected_status": expected_status,
                "expectation_met": expectation_met,
                "operation_count": receipt["operation_count"],
                "would_change": receipt["would_change"],
                "rejection_reason": receipt["rejection_reason"],
                "latency_ms": receipt["latency_ms"],
                "human_ratings": case_ratings,
            }
        )

    proposal_results = [item for item in results if item["status"] != "no_proposal"]
    expected_results = [item for item in results if item["expected_status"] is not None]
    status_counts = {
        status: sum(item["status"] == status for item in results)
        for status in ("valid", "rejected", "provider_error", "no_proposal")
    }
    return {
        "schema": REPLAY_SCHEMA,
        "generated_at": datetime.now(UTC).isoformat(),
        "receipt_schema": SHADOW_RECEIPT_SCHEMA,
        "summary": {
            "cases": len(results),
            "status_counts": status_counts,
            "schema_valid_rate": (
                status_counts["valid"] / len(proposal_results) if proposal_results else None
            ),
            "expected_status_accuracy": (
                sum(item["expectation_met"] for item in expected_results) / len(expected_results)
                if expected_results
                else None
            ),
            "mean_latency_ms": round(statistics.fmean(item["latency_ms"] for item in results), 3),
            "total_operations": sum(item["operation_count"] for item in results),
            "human_rating_coverage": {
                field: len(values) / len(results) for field, values in ratings.items()
            },
            "human_rating_means": {
                field: round(statistics.fmean(values), 3) if values else None
                for field, values in ratings.items()
            },
        },
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Anonymized replay JSON or JSONL")
    parser.add_argument("--output", type=Path, help="Write the full replay report here")
    parser.add_argument("--require-expected-accuracy", type=float, default=1.0)
    args = parser.parse_args()
    report = replay_cases(load_cases(args.input))
    rendered = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    accuracy = report["summary"]["expected_status_accuracy"]
    return int(accuracy is not None and accuracy < args.require_expected_accuracy)


if __name__ == "__main__":
    raise SystemExit(main())
