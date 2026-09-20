from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "eval"))

import kenn_promote_feedback_evals as promote  # noqa: E402


def write_suite(path: Path, cases: list[dict]) -> None:
    path.write_text(json.dumps({"version": 1, "description": "test", "cases": cases}) + "\n", encoding="utf-8")


def test_promote_preview_does_not_write(tmp_path) -> None:
    draft = tmp_path / "draft.json"
    suite = tmp_path / "questions.json"
    write_suite(draft, [{"id": "feedback-a", "question": "A?", "answer_must_include": ["a"]}])
    write_suite(suite, [])

    report = promote.promote_cases(draft_path=draft, suite_path=suite, ids=["feedback-a"])

    assert report["preview_count"] == 1
    assert report["promoted_count"] == 0
    assert json.loads(suite.read_text(encoding="utf-8"))["cases"] == []


def test_promote_selected_case_writes_and_removes_from_draft(tmp_path) -> None:
    draft = tmp_path / "draft.json"
    suite = tmp_path / "questions.json"
    write_suite(
        draft,
        [
            {"id": "feedback-a", "question": "A?", "answer_must_include": ["a"]},
            {"id": "feedback-b", "question": "B?", "answer_must_include": ["b"]},
        ],
    )
    write_suite(suite, [{"id": "existing", "question": "Existing?"}])

    report = promote.promote_cases(
        draft_path=draft,
        suite_path=suite,
        ids=["feedback-a"],
        write=True,
        remove_promoted=True,
    )

    suite_cases = json.loads(suite.read_text(encoding="utf-8"))["cases"]
    draft_cases = json.loads(draft.read_text(encoding="utf-8"))["cases"]
    assert report["promoted_count"] == 1
    assert suite_cases[-1]["id"] == "feedback-a"
    assert suite_cases[-1]["category"] == "feedback"
    assert "feedback" in suite_cases[-1]["tags"]
    assert [case["id"] for case in draft_cases] == ["feedback-b"]


def test_promote_skips_duplicates(tmp_path) -> None:
    draft = tmp_path / "draft.json"
    suite = tmp_path / "questions.json"
    write_suite(draft, [{"id": "feedback-a", "question": "A?"}])
    write_suite(suite, [{"id": "feedback-a", "question": "A?"}])

    report = promote.promote_cases(draft_path=draft, suite_path=suite, ids=["feedback-a"], write=True)

    assert report["duplicate_ids"] == ["feedback-a"]
    assert report["promoted_count"] == 0


def test_promote_reports_missing_ids(tmp_path) -> None:
    draft = tmp_path / "draft.json"
    suite = tmp_path / "questions.json"
    write_suite(draft, [])
    write_suite(suite, [])

    report = promote.promote_cases(draft_path=draft, suite_path=suite, ids=["missing"], write=True)

    assert report["ok"] is False
    assert report["missing_ids"] == ["missing"]
