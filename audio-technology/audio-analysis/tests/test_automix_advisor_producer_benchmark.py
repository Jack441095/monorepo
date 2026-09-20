"""Grounded advisor producer benchmark regression test."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.eval.automix_advisor_producer_benchmark import run_benchmark


ROOT = Path(__file__).resolve().parents[2]
SUITE = (
    ROOT
    / "studio"
    / "audio_analysis"
    / "audio_analysis"
    / "evals"
    / "advisor_producer_cases.json"
)


def test_official_producer_suite_meets_contract_gate() -> None:
    payload = json.loads(SUITE.read_text(encoding="utf-8"))
    report = run_benchmark(payload["cases"])
    assert report["summary"] == {
        "cases": 11,
        "passed": 11,
        "pass_rate": 1.0,
        "proposals": 7,
        "schema_valid_rate": 1.0,
        "provider_errors": 0,
        "unexpected_rejections": 0,
    }
    assert all(result["passed"] for result in report["results"])
    evidence_ids = [
        source_id
        for result in report["results"]
        for operation in result["operations"]
        for source_id in operation["evidence_source_ids"]
    ]
    assert evidence_ids
    assert all("@index:v-" in source_id for source_id in evidence_ids)
