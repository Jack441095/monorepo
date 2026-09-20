from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "eval"))

import kenn_validate_hard_negatives as validate_hn  # noqa: E402


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_validate_curated_hard_negatives_passes_for_matching_case_and_source(tmp_path: Path) -> None:
    suite = tmp_path / "questions.json"
    notes = tmp_path / "notes"
    hard = tmp_path / "hard.jsonl"
    notes.mkdir()
    (notes / "wrong.md").write_text("Status: Approved\n", encoding="utf-8")
    suite.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "case-1",
                        "question": "Which Wwise source should win?",
                        "route": "game_audio",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    write_jsonl(
        hard,
        [
            {
                "schema": "kenn.hard_negative.v1",
                "case_id": "case-1",
                "question": "Which Wwise source should win?",
                "negative_source": "wrong.md",
                "negative_source_label": "Wrong Source",
                "reason": "true hard negative: overlaps but misses the specific diagnosis",
                "route": "game_audio",
                "topics": ["wwise", "game_audio"],
            }
        ],
    )

    report = validate_hn.validate(hard_negatives=hard, suite=suite, notes_dir=notes)

    assert report["ok"] is True
    assert report["rows"] == 1


def test_validate_curated_hard_negatives_reports_stale_labels(tmp_path: Path) -> None:
    suite = tmp_path / "questions.json"
    notes = tmp_path / "notes"
    hard = tmp_path / "hard.jsonl"
    notes.mkdir()
    suite.write_text(json.dumps({"cases": [{"id": "case-1", "question": "Fresh question"}]}), encoding="utf-8")
    write_jsonl(
        hard,
        [
            {
                "schema": "kenn.hard_negative.v1",
                "case_id": "missing-case",
                "question": "Old question",
                "negative_source": "missing.md",
                "negative_source_label": "Missing Source",
                "reason": "wrong source",
                "route": "game_audio",
                "topics": ["wwise"],
            }
        ],
    )

    report = validate_hn.validate(hard_negatives=hard, suite=suite, notes_dir=notes)

    assert report["ok"] is False
    assert any("case_id not found" in error for error in report["errors"])
    assert any("negative_source note does not exist" in error for error in report["errors"])
