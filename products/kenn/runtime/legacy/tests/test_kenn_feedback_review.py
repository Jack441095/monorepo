from __future__ import annotations

import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "eval"))

import kenn_feedback_review  # noqa: E402


def test_run_review_summarizes_and_exports(monkeypatch) -> None:
    fake = types.SimpleNamespace()
    fake.training_records_snapshot = lambda limit=500: {
        "summary": {"total": 2, "reviewed": 1, "should_fallback": 1, "source_incorrect": 0},
        "diagnostics": {"issue_count": 1},
        "path": "records.jsonl",
        "review_path": "reviews.json",
        "reviewed_export_path": "reviewed.jsonl",
        "hard_negatives_path": "hard.jsonl",
        "route_memory_path": "route.jsonl",
    }
    fake.improvement_queue = lambda limit=12: {
        "total": 1,
        "items": [{"source": "feedback", "source_id": "fb1", "question": "Bad answer?"}],
    }
    fake.demo_feedback_summary = lambda limit=12: {"needs_work": 1}
    fake.repair_plan = lambda **kwargs: {"items": [{"title": "Repair", "command": "./audio-too eval"}]}
    fake.export_reviewed_training = lambda: {"ok": True, "count": 2}
    fake.export_hard_negatives = lambda: {"ok": True, "count": 1}
    fake.export_route_memory = lambda: {"ok": True, "count": 1}
    fake.draft_eval_from_feedback = lambda feedback_id: {
        "ok": True,
        "case": {"id": f"feedback-{feedback_id}"},
        "path": "draft_feedback_cases.json",
    }
    monkeypatch.setattr(kenn_feedback_review, "_load_improvement_module", lambda: fake)

    payload = kenn_feedback_review.run_review(export=True, draft_feedback_evals=True, limit=5)

    assert payload["training_summary"]["total"] == 2
    assert payload["exports"]["hard_negatives"]["count"] == 1
    assert payload["drafted_eval_cases"][0]["case_id"] == "feedback-fb1"


def test_main_prints_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        kenn_feedback_review,
        "run_review",
        lambda **kwargs: {"ok": True, "training_summary": {"total": 0}, "queue_items": []},
    )
    monkeypatch.setattr(sys, "argv", ["kenn_feedback_review.py", "--json"])

    assert kenn_feedback_review.main() == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
