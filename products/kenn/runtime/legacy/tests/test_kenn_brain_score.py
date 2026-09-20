from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "eval"))

import kenn_brain_score as brain_score  # noqa: E402


def test_build_scorecard_from_latest_artifacts(tmp_path) -> None:
    (tmp_path / "ableton_benchmark_20260623T120000Z.json").write_text(
        json.dumps(
            {
                "total_runs": 10,
                "passed_runs": 10,
                "source_diversity_warning_runs": 0,
                "duration_ms": {"p95": 70},
                "source_quality_counts": {"high": 10},
                "case_category_pass_rates": {
                    "adversarial": 1.0,
                    "ambiguity": 1.0,
                    "business": 1.0,
                    "refusal": 1.0,
                },
                "answer_quality_score": {"mean": 0},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "kenn_tester_probe_20260623T120001Z.json").write_text(
        json.dumps(
            {
                "total": 3,
                "passed": 3,
                "rows": [
                    {"id": "pricing-followup", "question": "What should I ask first?", "expected_confidence": "high", "ok": True},
                    {"id": "bread", "question": "How do I bake bread?", "expected_confidence": "low", "ok": True},
                    {"id": "mix", "question": "How do I mix?", "expected_confidence": "high", "ok": True},
                ],
            }
        ),
        encoding="utf-8",
    )

    report = brain_score.build_scorecard(tmp_path)

    assert report["ok"] is True
    assert report["brain_score"] >= 95
    assert report["dimensions"]["routing_judgment"] == 100.0
    assert report["dimensions"]["followup_memory"] == 100.0


def test_scorecard_reports_missing_artifacts(tmp_path) -> None:
    report = brain_score.build_scorecard(tmp_path)

    assert report["ok"] is False
    assert report["brain_score"] == 0.0
    assert report["notes"]
