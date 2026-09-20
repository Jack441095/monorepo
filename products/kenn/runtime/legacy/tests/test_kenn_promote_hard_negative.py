from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "eval"))

import kenn_promote_hard_negative as promote_hn  # noqa: E402


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def fixture_paths(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    candidates = tmp_path / "candidates.jsonl"
    target = tmp_path / "curated.jsonl"
    suite = tmp_path / "questions.json"
    notes = tmp_path / "notes"
    notes.mkdir()
    (notes / "wrong-source.md").write_text("Status: Approved\n", encoding="utf-8")
    suite.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "case-1",
                        "question": "Why did KENN pick the wrong source?",
                        "route": "game_audio",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    write_jsonl(
        candidates,
        [
            {
                "schema": "kenn.hard_negative_candidate.v1",
                "case_id": "case-1",
                "question": "Why did KENN pick the wrong source?",
                "route": "game_audio",
                "topics": ["wwise", "game_audio"],
                "positive_source_label": "Right Source (right-source.md)",
                "candidate_source_label": "Wrong Source (wrong-source.md)",
                "candidate_rank": 2,
            }
        ],
    )
    target.write_text("", encoding="utf-8")
    return candidates, target, suite, notes


def test_promote_hard_negative_preview_does_not_write(tmp_path: Path) -> None:
    candidates, target, suite, notes = fixture_paths(tmp_path)

    report = promote_hn.promote(
        case_id="case-1",
        candidate_rank=2,
        candidates_path=candidates,
        target_path=target,
        suite=suite,
        notes_dir=notes,
        write=False,
    )

    assert report["ok"] is True
    assert report["write"] is False
    assert target.read_text(encoding="utf-8") == ""
    assert report["row"]["negative_source"] == "wrong-source.md"


def test_promote_hard_negative_write_appends_validated_row(tmp_path: Path) -> None:
    candidates, target, suite, notes = fixture_paths(tmp_path)

    report = promote_hn.promote(
        case_id="case-1",
        source_label="Wrong Source (wrong-source.md)",
        candidates_path=candidates,
        target_path=target,
        suite=suite,
        notes_dir=notes,
        reason="true hard negative: reviewed source overlap but wrong diagnosis",
        write=True,
    )

    rows = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()]
    assert report["ok"] is True
    assert rows[0]["schema"] == "kenn.hard_negative.v1"
    assert rows[0]["negative_source_label"] == "Wrong Source"
    assert report["validation"]["ok"] is True


def test_promote_hard_negative_rejects_duplicate(tmp_path: Path) -> None:
    candidates, target, suite, notes = fixture_paths(tmp_path)
    kwargs = {
        "case_id": "case-1",
        "candidate_rank": 2,
        "candidates_path": candidates,
        "target_path": target,
        "suite": suite,
        "notes_dir": notes,
        "write": True,
    }
    assert promote_hn.promote(**kwargs)["ok"] is True

    report = promote_hn.promote(**kwargs)

    assert report["ok"] is False
    assert "already exists" in report["error"]


def test_promotable_candidates_filters_topic_and_existing_labels(tmp_path: Path) -> None:
    candidates, target, _suite, _notes = fixture_paths(tmp_path)
    write_jsonl(
        target,
        [
            {
                "schema": "kenn.hard_negative.v1",
                "case_id": "already-curated",
                "question": "Already curated",
                "negative_source": "wrong-source.md",
                "negative_source_label": "Wrong Source",
                "reason": "true hard negative: already tracked",
                "route": "game_audio",
                "topics": ["wwise", "game_audio"],
            }
        ],
    )
    write_jsonl(
        candidates,
        [
            {
                "case_id": "already-curated",
                "question": "Already curated",
                "route": "game_audio",
                "topics": ["wwise", "game_audio"],
                "positive_source_label": "Right Source (right-source.md)",
                "candidate_source_label": "Wrong Source (wrong-source.md)",
                "candidate_rank": 2,
                "candidate_overlap_score": 0.9,
            },
            {
                "case_id": "next-case",
                "question": "Next Wwise case",
                "route": "game_audio",
                "topics": ["wwise", "game_audio"],
                "positive_source_label": "Right Source (right-source.md)",
                "candidate_source_label": "Wrong Source (wrong-source.md)",
                "candidate_rank": 3,
                "candidate_overlap_score": 0.8,
            },
            {
                "case_id": "mix-case",
                "question": "Mix case",
                "route": "production",
                "topics": ["mixing"],
                "positive_source_label": "Right Source (right-source.md)",
                "candidate_source_label": "Wrong Source (wrong-source.md)",
                "candidate_rank": 2,
                "candidate_overlap_score": 1.0,
            },
        ],
    )

    report = promote_hn.promotable_candidates(candidates_path=candidates, target_path=target, topic="game_audio")

    assert report["total_promotable"] == 1
    assert report["items"][0]["case_id"] == "next-case"
    assert "promote-hard-negative" in report["items"][0]["promote_command"]
