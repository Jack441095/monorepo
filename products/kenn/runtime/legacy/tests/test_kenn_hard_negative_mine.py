from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "eval"))

import kenn_hard_negative_mine as mine  # noqa: E402


def test_mine_candidates_finds_near_miss_lower_sources() -> None:
    records = [
        {
            "id": "case-1",
            "question": "How do I fix muddy bass?",
            "eval_failures": [],
            "topics": ["bass", "eq"],
            "source_labels": [
                "Bass Processing Basics (bass-processing-basics.md)",
                "Sub Bass Saturation (sub-bass-saturation.md)",
                "Podcast Dialogue Edit (podcast-dialogue-edit.md)",
            ],
        }
    ]

    rows = mine.mine_candidates(records, min_score=0.1, limit=10)

    assert len(rows) == 1
    assert rows[0]["candidate_source_label"].startswith("Sub Bass Saturation")
    assert rows[0]["review_decision"] == "pending"


def test_mine_writes_jsonl(tmp_path) -> None:
    benchmark = tmp_path / "benchmark.jsonl"
    output = tmp_path / "candidates.jsonl"
    benchmark.write_text(
        json.dumps(
            {
                "id": "case-1",
                "question": "How do I fix harsh vocals?",
                "eval_failures": [],
                "topics": ["vocals", "eq"],
                "source_labels": [
                    "Harsh Vocal Fix (harsh-vocal-fix.md)",
                    "Harsh Vocal Compression (harsh-vocal-compression.md)",
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = mine.mine(benchmark_jsonl=benchmark, output=output, min_score=0.1)

    assert report["ok"] is True
    assert report["candidates"] == 1
    assert output.exists()
    assert json.loads(output.read_text(encoding="utf-8").strip())["schema"] == "kenn.hard_negative_candidate.v1"
