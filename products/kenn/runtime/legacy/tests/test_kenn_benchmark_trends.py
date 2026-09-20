"""Tests for KENN benchmark trend summaries."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "eval"))

from kenn_benchmark_trends import load_summaries, summarize_trends  # noqa: E402


def test_benchmark_trends_compare_first_and_latest(tmp_path: Path) -> None:
    first = {
        "created_at": "2026-06-01T00:00:00+00:00",
        "total_runs": 10,
        "passed_runs": 9,
        "failed_runs": 1,
        "duration_ms": {"mean": 40, "p95": 100},
    }
    latest = {
        "created_at": "2026-06-02T00:00:00+00:00",
        "total_runs": 12,
        "passed_runs": 12,
        "failed_runs": 0,
        "duration_ms": {"mean": 35, "p95": 80},
        "case_category_counts": {"standard": 10, "refusal": 2},
        "case_category_pass_rates": {"standard": 1.0, "refusal": 1.0},
        "grounding_mode_counts": {"strong": 10, "weak": 2},
    }
    (tmp_path / "ableton_benchmark_20260601T000000Z.json").write_text(
        json.dumps(first),
        encoding="utf-8",
    )
    (tmp_path / "ableton_benchmark_20260602T000000Z.json").write_text(
        json.dumps(latest),
        encoding="utf-8",
    )

    report = summarize_trends(load_summaries(tmp_path, limit=10))

    assert report["ok"] is True
    assert report["count"] == 2
    assert report["first"]["pass_rate"] == 0.9
    assert report["latest"]["pass_rate"] == 1.0
    assert report["delta"]["pass_rate"] == 0.1
    assert report["delta"]["p95_ms"] == -20.0
    assert report["latest"]["category_counts"]["refusal"] == 2
