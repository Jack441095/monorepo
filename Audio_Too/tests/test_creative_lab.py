"""Tests for Creative Lab session, feedback, and Mix Review handoff helpers."""

from __future__ import annotations

import io
import json
import math
import struct
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server" / "app"))

import creative_lab  # noqa: E402
from creative_lab import eval as creative_lab_eval  # noqa: E402
from creative_lab import portfolio as creative_lab_portfolio  # noqa: E402
from creative_lab import repair as creative_lab_repair  # noqa: E402
from creative_lab import storage as creative_lab_storage  # noqa: E402
from creative_lab import training as creative_lab_training  # noqa: E402
import db  # noqa: E402


def tiny_wav_bytes(seconds: float = 0.1, sample_rate: int = 8000) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for index in range(int(seconds * sample_rate)):
            sample = int(0.2 * 32767 * math.sin(2 * math.pi * 220 * index / sample_rate))
            wav.writeframes(struct.pack("<h", sample))
    return out.getvalue()


def test_record_session_event_creates_and_updates_session(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(creative_lab_storage, "DATA_PATH", tmp_path / "creative_lab_sessions.json")

    first = creative_lab.record_session_event(
        {
            "title": "Dark garage idea",
            "type": "kenn",
            "question": "How should I start?",
            "answer": "Start sparse.",
        }
    )
    second = creative_lab.record_session_event(
        {
            "session_id": first["session"]["id"],
            "type": "audiogen_loop",
            "prompt": "Generate a dark loop",
            "emotion": "fear",
            "src": "/portfolio/audio/test.wav",
        }
    )
    snapshot = creative_lab.snapshot()

    assert first["ok"] is True
    assert second["session"]["id"] == first["session"]["id"]
    assert snapshot["counts"]["sessions"] == 1
    assert len(snapshot["sessions"][0]["events"]) == 2
    assert snapshot["metrics"]["generated_audio"] == 1


def test_snapshot_surfaces_quality_repair_and_prompt_leaderboard(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(creative_lab_storage, "DATA_PATH", tmp_path / "creative_lab_sessions.json")
    monkeypatch.setattr(creative_lab.demo_feedback, "record_feedback", lambda payload: {"ok": True, **payload})
    session = creative_lab.record_session_event(
        {
            "title": "Useful prompt",
            "type": "audiogen_loop",
            "prompt": "Generate a warm chorus loop",
            "emotion": "love",
            "src": "/portfolio/audio/love.wav",
        }
    )
    creative_lab.record_feedback(
        {
            "session_id": session["session"]["id"],
            "rating": "useful_generation_prompt",
            "target": "audiogen",
            "prompt": "Generate a warm chorus loop",
            "emotion": "love",
            "src": "/portfolio/audio/love.wav",
        }
    )
    creative_lab.record_feedback(
        {
            "session_id": session["session"]["id"],
            "rating": "wrong_direction",
            "target": "kenn",
            "question": "How should I widen vocals?",
            "answer": "Unhelpful answer.",
        }
    )

    snapshot = creative_lab.snapshot()

    assert snapshot["metrics"]["positive_feedback"] == 1
    assert snapshot["metrics"]["negative_feedback"] == 1
    assert snapshot["metrics"]["repair_open"] == 1
    assert snapshot["repair_recommendations"][0]["title"] == "Create a repair draft"
    assert snapshot["repair_queue"][0]["priority"] == "answer repair"
    assert snapshot["prompt_leaderboard"][0]["prompt"] == "Generate a warm chorus loop"
    assert snapshot["prompt_leaderboard"][0]["useful_votes"] == 1


def test_session_replay_returns_session_with_feedback(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(creative_lab_storage, "DATA_PATH", tmp_path / "creative_lab_sessions.json")
    session = creative_lab.record_session_event({"type": "kenn", "question": "What next?", "answer": "Try a contrast."})
    creative_lab.record_feedback(
        {
            "session_id": session["session"]["id"],
            "rating": "good_idea",
            "target": "kenn",
            "question": "What next?",
        }
    )

    replay = creative_lab.session_replay(session["session"]["id"])

    assert replay["ok"] is True
    assert replay["session"]["events"][0]["type"] == "kenn"
    assert replay["feedback"][0]["rating"] == "good_idea"


def test_create_repair_artifacts_from_negative_feedback(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(creative_lab_storage, "DATA_PATH", tmp_path / "creative_lab_sessions.json")
    monkeypatch.setattr(creative_lab_repair, "KENN_NOTES_DIR", tmp_path / "KENN" / "Training_Data_Notes")
    monkeypatch.setattr(creative_lab_eval, "CREATIVE_DRAFT_EVAL_PATH", tmp_path / "KENN" / "evals" / "draft_creative_lab_cases.json")
    monkeypatch.setattr(creative_lab_repair, "CREATIVE_DRAFT_EVAL_PATH", tmp_path / "KENN" / "evals" / "draft_creative_lab_cases.json")
    monkeypatch.setattr(creative_lab.demo_feedback, "record_feedback", lambda payload: {"ok": True, **payload})
    feedback = creative_lab.record_feedback(
        {
            "rating": "bad_source",
            "target": "kenn",
            "question": "How do I make vocals wide without mud?",
            "answer": "Use unrelated de-essing advice.",
            "comment": "Answered the wrong topic.",
        }
    )["feedback"]

    result = creative_lab.create_repair_artifacts(feedback["id"])
    repeat = creative_lab.create_repair_artifacts(feedback["id"])
    note_path = tmp_path / "KENN" / "Training_Data_Notes" / result["note"]
    eval_path = tmp_path / "KENN" / "evals" / "draft_creative_lab_cases.json"
    eval_data = __import__("json").loads(eval_path.read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert result["note"].endswith("-creative-repair.md")
    assert "Status: Draft" in note_path.read_text(encoding="utf-8")
    assert eval_data["cases"][0]["id"] == result["eval_case_id"]
    assert eval_data["cases"][0]["question"] == "How do I make vocals wide without mud?"
    assert repeat["already_exists"] is True
    assert creative_lab.snapshot()["repair_queue"][0]["repair_status"] == "drafted"


def test_promote_repair_approves_note_and_records_eval(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(creative_lab_storage, "DATA_PATH", tmp_path / "creative_lab_sessions.json")
    monkeypatch.setattr(creative_lab_repair, "KENN_NOTES_DIR", tmp_path / "KENN" / "Training_Data_Notes")
    monkeypatch.setattr(creative_lab_eval, "CREATIVE_DRAFT_EVAL_PATH", tmp_path / "KENN" / "evals" / "draft_creative_lab_cases.json")
    monkeypatch.setattr(creative_lab_repair, "CREATIVE_DRAFT_EVAL_PATH", tmp_path / "KENN" / "evals" / "draft_creative_lab_cases.json")
    monkeypatch.setattr(creative_lab.demo_feedback, "record_feedback", lambda payload: {"ok": True, **payload})
    monkeypatch.setattr(creative_lab_repair, "_build_index", lambda: {"ok": True, "returncode": 0, "output": "built"})
    monkeypatch.setattr(
        creative_lab_repair,
        "_evaluate_repair_case",
        lambda case: {
            "ok": True,
            "passed": True,
            "failures": [],
            "answer": "Use vocal doubles and filtered side reverb without muddy low mids.",
            "confidence": "high",
            "source_quality": "high",
            "sources": [{"label": "how-do-i-make-vocals-wide-without-mud-creative-repair.md", "kind": "note", "score": 9.5}],
        },
    )
    feedback = creative_lab.record_feedback(
        {
            "rating": "wrong_direction",
            "target": "kenn",
            "question": "How do I make vocals wide without mud?",
            "answer": "Use unrelated de-essing advice.",
        }
    )["feedback"]
    draft = creative_lab.create_repair_artifacts(feedback["id"])

    result = creative_lab.promote_repair(feedback["id"])
    note_text = (tmp_path / "KENN" / "Training_Data_Notes" / draft["note"]).read_text(encoding="utf-8")
    queue_item = creative_lab.snapshot()["repair_queue"][0]

    assert result["ok"] is True
    assert result["eval"]["passed"] is True
    assert "Status: Approved" in note_text
    assert queue_item["repair_status"] == "promoted_passed"
    assert queue_item["last_eval_passed"] is True
    assert result["run"]["source_ranking"]["repair_note_rank"] == 1
    assert result["run"]["source_ranking"]["repair_note_in_top_three"] is True
    metrics = creative_lab.snapshot()["metrics"]
    assert metrics["repair_attempts"] == 1
    assert metrics["repair_pass_rate"] == 100
    assert metrics["repair_top_three_rate"] == 100


def test_promote_repair_eval_case_adds_main_regression_case(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(creative_lab_storage, "DATA_PATH", tmp_path / "creative_lab_sessions.json")
    monkeypatch.setattr(creative_lab_repair, "KENN_NOTES_DIR", tmp_path / "KENN" / "Training_Data_Notes")
    monkeypatch.setattr(creative_lab_eval, "CREATIVE_DRAFT_EVAL_PATH", tmp_path / "KENN" / "evals" / "draft_creative_lab_cases.json")
    monkeypatch.setattr(creative_lab_repair, "CREATIVE_DRAFT_EVAL_PATH", tmp_path / "KENN" / "evals" / "draft_creative_lab_cases.json")
    monkeypatch.setattr(creative_lab_repair, "MAIN_EVAL_PATH", tmp_path / "KENN" / "evals" / "questions.json")
    monkeypatch.setattr(creative_lab.demo_feedback, "record_feedback", lambda payload: {"ok": True, **payload})
    monkeypatch.setattr(creative_lab_repair, "_build_index", lambda: {"ok": True, "returncode": 0, "output": "built"})
    monkeypatch.setattr(
        creative_lab_repair,
        "_evaluate_repair_case",
        lambda case: {
            "ok": True,
            "passed": True,
            "failures": [],
            "answer": "Use doubles and filtered widening effects.",
            "confidence": "high",
            "source_quality": "high",
            "sources": [{"label": "how-do-i-make-vocals-wide-without-mud-creative-repair.md", "kind": "note", "score": 9.5}],
        },
    )
    feedback = creative_lab.record_feedback(
        {
            "rating": "wrong_direction",
            "target": "kenn",
            "question": "How do I make vocals wide without mud?",
            "answer": "Use unrelated de-essing advice.",
        }
    )["feedback"]
    creative_lab.create_repair_artifacts(feedback["id"])
    creative_lab.promote_repair(feedback["id"])

    result = creative_lab.promote_repair_eval_case(feedback["id"])
    repeat = creative_lab.promote_repair_eval_case(feedback["id"])
    suite = __import__("json").loads((tmp_path / "KENN" / "evals" / "questions.json").read_text(encoding="utf-8"))
    comparison = creative_lab.repair_comparison(feedback["id"])

    assert result["ok"] is True
    assert result["case"]["id"].startswith("creative-")
    assert len(suite["cases"]) == 1
    assert repeat["ok"] is True
    assert len(__import__("json").loads((tmp_path / "KENN" / "evals" / "questions.json").read_text(encoding="utf-8"))["cases"]) == 1
    assert comparison["main_eval_promoted_at"]
    assert creative_lab.snapshot()["repair_queue"][0]["repair_status"] == "regression_added"
    assert creative_lab.snapshot()["metrics"]["repair_regressions_added"] == 1


def test_repair_comparison_returns_original_and_latest_answers(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(creative_lab_storage, "DATA_PATH", tmp_path / "creative_lab_sessions.json")
    monkeypatch.setattr(creative_lab_repair, "KENN_NOTES_DIR", tmp_path / "KENN" / "Training_Data_Notes")
    monkeypatch.setattr(creative_lab_eval, "CREATIVE_DRAFT_EVAL_PATH", tmp_path / "KENN" / "evals" / "draft_creative_lab_cases.json")
    monkeypatch.setattr(creative_lab_repair, "CREATIVE_DRAFT_EVAL_PATH", tmp_path / "KENN" / "evals" / "draft_creative_lab_cases.json")
    monkeypatch.setattr(creative_lab.demo_feedback, "record_feedback", lambda payload: {"ok": True, **payload})
    monkeypatch.setattr(creative_lab_repair, "_build_index", lambda: {"ok": True, "returncode": 0, "output": "built"})
    monkeypatch.setattr(
        creative_lab_repair,
        "_evaluate_repair_case",
        lambda case: {
            "ok": True,
            "passed": False,
            "failures": ["missing answer terms: ['wide']"],
            "answer": "Use filtered delays and doubles.",
            "confidence": "medium",
            "source_quality": "high",
            "sources": [{"label": "how-do-i-make-vocals-wide-without-mud-creative-repair.md", "kind": "note", "score": 8.1}],
        },
    )
    feedback = creative_lab.record_feedback(
        {
            "rating": "bad_source",
            "target": "kenn",
            "question": "How do I make vocals wide without mud?",
            "answer": "Use unrelated de-essing advice.",
            "comment": "Wrong source.",
        }
    )["feedback"]
    creative_lab.create_repair_artifacts(feedback["id"])
    creative_lab.promote_repair(feedback["id"])

    comparison = creative_lab.repair_comparison(feedback["id"])

    assert comparison["ok"] is True
    assert comparison["original"]["answer"] == "Use unrelated de-essing advice."
    assert comparison["latest"]["answer"] == "Use filtered delays and doubles."
    assert comparison["latest"]["passed"] is False
    assert comparison["latest"]["sources"][0]["label"] == "how-do-i-make-vocals-wide-without-mud-creative-repair.md"
    assert len(comparison["history"]) == 1
    assert comparison["history"][0]["eval_passed"] is False
    assert comparison["history"][0]["source_ranking"]["repair_note_rank"] == 1
    assert creative_lab.snapshot()["repair_queue"][0]["repair_attempts"] == 1


def test_repair_recommendations_follow_repair_state(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(creative_lab_storage, "DATA_PATH", tmp_path / "creative_lab_sessions.json")
    monkeypatch.setattr(creative_lab_repair, "KENN_NOTES_DIR", tmp_path / "KENN" / "Training_Data_Notes")
    monkeypatch.setattr(creative_lab_eval, "CREATIVE_DRAFT_EVAL_PATH", tmp_path / "KENN" / "evals" / "draft_creative_lab_cases.json")
    monkeypatch.setattr(creative_lab_repair, "CREATIVE_DRAFT_EVAL_PATH", tmp_path / "KENN" / "evals" / "draft_creative_lab_cases.json")
    monkeypatch.setattr(creative_lab.demo_feedback, "record_feedback", lambda payload: {"ok": True, **payload})
    feedback = creative_lab.record_feedback(
        {
            "rating": "bad_source",
            "target": "kenn",
            "question": "How do I make vocals wide without mud?",
            "answer": "Use unrelated de-essing advice.",
        }
    )["feedback"]
    assert creative_lab.snapshot()["repair_recommendations"][0]["title"] == "Create a repair draft"

    creative_lab.create_repair_artifacts(feedback["id"])
    assert creative_lab.snapshot()["repair_recommendations"][0]["title"] == "Promote and test the repair"

    data = creative_lab._load()
    item = data["feedback"][0]
    item["repair_history"] = [
        {
            "eval_passed": True,
            "failures": [],
            "source_ranking": {"repair_note_in_top_three": False},
        }
    ]
    item["last_eval_passed"] = True
    creative_lab._save(data)
    assert creative_lab.snapshot()["repair_recommendations"][0]["title"] == "Improve repair-note ranking"

    data = creative_lab._load()
    data["feedback"][0]["repair_history"][0]["source_ranking"]["repair_note_in_top_three"] = True
    creative_lab._save(data)
    assert creative_lab.snapshot()["repair_recommendations"][0]["title"] == "Add passing case to regression suite"


def test_run_repair_recommendation_executes_safe_steps(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(creative_lab_storage, "DATA_PATH", tmp_path / "creative_lab_sessions.json")
    monkeypatch.setattr(creative_lab_repair, "KENN_NOTES_DIR", tmp_path / "KENN" / "Training_Data_Notes")
    monkeypatch.setattr(creative_lab_eval, "CREATIVE_DRAFT_EVAL_PATH", tmp_path / "KENN" / "evals" / "draft_creative_lab_cases.json")
    monkeypatch.setattr(creative_lab_repair, "CREATIVE_DRAFT_EVAL_PATH", tmp_path / "KENN" / "evals" / "draft_creative_lab_cases.json")
    monkeypatch.setattr(creative_lab.demo_feedback, "record_feedback", lambda payload: {"ok": True, **payload})
    feedback = creative_lab.record_feedback(
        {
            "rating": "bad_source",
            "target": "kenn",
            "question": "How do I make vocals wide without mud?",
            "answer": "Use unrelated de-essing advice.",
        }
    )["feedback"]

    result = creative_lab.run_repair_recommendation(feedback["id"])

    assert result["ok"] is True
    assert result["workflow_kind"] == "create_draft"
    assert creative_lab.snapshot()["repair_queue"][0]["repair_status"] == "drafted"


def test_run_repair_recommendation_reports_manual_steps(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(creative_lab_storage, "DATA_PATH", tmp_path / "creative_lab_sessions.json")
    monkeypatch.setattr(creative_lab_repair, "KENN_NOTES_DIR", tmp_path / "KENN" / "Training_Data_Notes")
    monkeypatch.setattr(creative_lab_eval, "CREATIVE_DRAFT_EVAL_PATH", tmp_path / "KENN" / "evals" / "draft_creative_lab_cases.json")
    monkeypatch.setattr(creative_lab_repair, "CREATIVE_DRAFT_EVAL_PATH", tmp_path / "KENN" / "evals" / "draft_creative_lab_cases.json")
    monkeypatch.setattr(creative_lab.demo_feedback, "record_feedback", lambda payload: {"ok": True, **payload})
    feedback = creative_lab.record_feedback(
        {
            "rating": "wrong_direction",
            "target": "kenn",
            "question": "How do I make vocals wide without mud?",
            "answer": "Use unrelated de-essing advice.",
        }
    )["feedback"]
    creative_lab.create_repair_artifacts(feedback["id"])
    data = creative_lab._load()
    data["feedback"][0]["repair_history"] = [{"eval_passed": False, "failures": ["missing answer terms"]}]
    creative_lab._save(data)

    result = creative_lab.run_repair_recommendation(feedback["id"])

    assert result["ok"] is False
    assert result["manual_required"] is True
    assert result["recommendation"]["kind"] == "manual_fix"


def test_export_repair_training_records_writes_jsonl(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(creative_lab_storage, "DATA_PATH", tmp_path / "creative_lab_sessions.json")
    monkeypatch.setattr(creative_lab_repair, "KENN_NOTES_DIR", tmp_path / "KENN" / "Training_Data_Notes")
    monkeypatch.setattr(creative_lab_eval, "CREATIVE_DRAFT_EVAL_PATH", tmp_path / "KENN" / "evals" / "draft_creative_lab_cases.json")
    monkeypatch.setattr(creative_lab_repair, "CREATIVE_DRAFT_EVAL_PATH", tmp_path / "KENN" / "evals" / "draft_creative_lab_cases.json")
    monkeypatch.setattr(creative_lab_training, "CREATIVE_REPAIR_RECORDS_PATH", tmp_path / "KENN" / "artifacts" / "training" / "creative_lab_repair_records.jsonl")
    monkeypatch.setattr(creative_lab.demo_feedback, "record_feedback", lambda payload: {"ok": True, **payload})
    monkeypatch.setattr(creative_lab_repair, "_build_index", lambda: {"ok": True, "returncode": 0, "output": "built"})
    feedback = creative_lab.record_feedback(
        {
            "rating": "bad_source",
            "target": "kenn",
            "question": "How do I make vocals wide without mud?",
            "answer": "Use unrelated de-essing advice.",
            "comment": "Wrong source.",
        }
    )["feedback"]
    draft = creative_lab.create_repair_artifacts(feedback["id"])
    monkeypatch.setattr(
        creative_lab_repair,
        "_evaluate_repair_case",
        lambda case: {
            "ok": True,
            "passed": True,
            "failures": [],
            "answer": "Use short filtered delays and keep the dry vocal centered.",
            "confidence": "high",
            "source_quality": "high",
            "sources": [{"label": draft["note"], "kind": "note", "score": 9.4}],
        },
    )
    creative_lab.promote_repair(feedback["id"])

    result = creative_lab.export_repair_training_records()
    lines = creative_lab_training.CREATIVE_REPAIR_RECORDS_PATH.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[0])

    assert result["ok"] is True
    assert result["count"] == 1
    assert record["schema"] == "kenn.creative_repair_record.v1"
    assert record["record_id"]
    assert record["question"] == "How do I make vocals wide without mud?"
    assert record["original_answer"] == "Use unrelated de-essing advice."
    assert record["eval_passed"] is True
    assert record["repair_note_rank"] == 1
    assert record["needs_rerank_training"] is False
    assert record["label"] == "good_repair"


def test_repair_training_export_snapshot_loads_records_and_skips_bad_rows(tmp_path, monkeypatch) -> None:
    export_path = tmp_path / "KENN" / "artifacts" / "training" / "creative_lab_repair_records.jsonl"
    export_path.parent.mkdir(parents=True)
    export_path.write_text(
        "\n".join(
            [
                json.dumps({"schema": "kenn.creative_repair_record.v1", "question": "First", "label": "needs_repair"}),
                "not-json",
                json.dumps({"schema": "kenn.creative_repair_record.v1", "question": "Latest", "label": "good_repair"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(creative_lab_training, "CREATIVE_REPAIR_RECORDS_PATH", export_path)

    snapshot = creative_lab.repair_training_export_snapshot(limit=1)

    assert snapshot["ok"] is True
    assert snapshot["exists"] is True
    assert snapshot["count"] == 2
    assert snapshot["skipped"] == 1
    assert snapshot["records"][0]["question"] == "Latest"
    assert snapshot["records"][0]["record_id"] == ":"


def test_review_repair_training_record_persists_label(tmp_path, monkeypatch) -> None:
    export_path = tmp_path / "KENN" / "artifacts" / "training" / "creative_lab_repair_records.jsonl"
    review_path = tmp_path / "KENN" / "artifacts" / "training" / "creative_lab_repair_reviews.json"
    export_path.parent.mkdir(parents=True)
    export_path.write_text(
        json.dumps(
            {
                "schema": "kenn.creative_repair_record.v1",
                "record_id": "fb1:2026-06-16 10:00:00",
                "question": "How should I widen vocals?",
                "label": "good_repair",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(creative_lab_training, "CREATIVE_REPAIR_RECORDS_PATH", export_path)
    monkeypatch.setattr(creative_lab_training, "CREATIVE_REPAIR_REVIEW_PATH", review_path)

    result = creative_lab.review_repair_training_record("fb1:2026-06-16 10:00:00", "approved", "Good example.")
    snapshot = creative_lab.repair_training_export_snapshot()

    assert result["ok"] is True
    assert result["review"]["decision"] == "approved"
    assert snapshot["review_counts"]["approved"] == 1
    assert snapshot["records"][0]["review"]["note"] == "Good example."
    assert json.loads(review_path.read_text(encoding="utf-8"))["reviews"]["fb1:2026-06-16 10:00:00"]["decision"] == "approved"


def test_export_approved_repair_training_records_filters_reviewed_records(tmp_path, monkeypatch) -> None:
    export_path = tmp_path / "KENN" / "artifacts" / "training" / "creative_lab_repair_records.jsonl"
    approved_path = tmp_path / "KENN" / "artifacts" / "training" / "creative_lab_repair_records.approved.jsonl"
    manifest_path = tmp_path / "KENN" / "artifacts" / "training" / "creative_lab_repair_records.approved.manifest.json"
    review_path = tmp_path / "KENN" / "artifacts" / "training" / "creative_lab_repair_reviews.json"
    export_path.parent.mkdir(parents=True)
    export_path.write_text(
        "\n".join(
            [
                json.dumps({"schema": "kenn.creative_repair_record.v1", "record_id": "approved-1", "question": "Approved"}),
                json.dumps({"schema": "kenn.creative_repair_record.v1", "record_id": "unreviewed-1", "question": "Unreviewed"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(creative_lab_training, "CREATIVE_REPAIR_RECORDS_PATH", export_path)
    monkeypatch.setattr(creative_lab_training, "CREATIVE_APPROVED_REPAIR_RECORDS_PATH", approved_path)
    monkeypatch.setattr(creative_lab_training, "CREATIVE_APPROVED_REPAIR_MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(creative_lab_training, "CREATIVE_REPAIR_REVIEW_PATH", review_path)
    creative_lab.review_repair_training_record("approved-1", "approved")
    creative_lab.review_repair_training_record("unreviewed-1", "needs_work")

    result = creative_lab.export_approved_repair_training_records()
    records = [json.loads(line) for line in approved_path.read_text(encoding="utf-8").splitlines()]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    snapshot = creative_lab.repair_training_export_snapshot()

    assert result["ok"] is True
    assert result["count"] == 1
    assert result["source_count"] == 2
    assert result["manifest_path"].endswith("creative_lab_repair_records.approved.manifest.json")
    assert records[0]["record_id"] == "approved-1"
    assert records[0]["review_decision"] == "approved"
    assert manifest["schema"] == "kenn.creative_repair_dataset_manifest.v1"
    assert manifest["raw_records"] == 2
    assert manifest["selected_records"] == 1
    assert manifest["review_counts"] == {"approved": 1, "needs_work": 1}
    assert snapshot["approved_manifest"]["exists"] is True
    assert snapshot["approved_manifest"]["manifest"]["selected_records"] == 1


def test_approved_repair_manifest_snapshot_reports_invalid_json(tmp_path, monkeypatch) -> None:
    manifest_path = tmp_path / "KENN" / "artifacts" / "training" / "creative_lab_repair_records.approved.manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text("not-json", encoding="utf-8")
    monkeypatch.setattr(creative_lab_training, "CREATIVE_APPROVED_REPAIR_MANIFEST_PATH", manifest_path)

    snapshot = creative_lab.approved_repair_manifest_snapshot()

    assert snapshot["exists"] is True
    assert "Invalid manifest JSON" in snapshot["error"]
    assert snapshot["manifest"] == {}


def test_validate_approved_repair_training_export_accepts_valid_dataset(tmp_path, monkeypatch) -> None:
    approved_path = tmp_path / "KENN" / "artifacts" / "training" / "creative_lab_repair_records.approved.jsonl"
    manifest_path = tmp_path / "KENN" / "artifacts" / "training" / "creative_lab_repair_records.approved.manifest.json"
    approved_path.parent.mkdir(parents=True)
    approved_path.write_text(json.dumps({"record_id": "r1", "review_decision": "approved"}) + "\n", encoding="utf-8")
    manifest_path.write_text(
        json.dumps(
            {
                "schema": "kenn.creative_repair_dataset_manifest.v1",
                "decision": "approved",
                "selected_records": 1,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(creative_lab_training, "CREATIVE_APPROVED_REPAIR_RECORDS_PATH", approved_path)
    monkeypatch.setattr(creative_lab_training, "CREATIVE_APPROVED_REPAIR_MANIFEST_PATH", manifest_path)

    result = creative_lab.validate_approved_repair_training_export()

    assert result["ok"] is True
    assert result["valid"] is True
    assert result["errors"] == []
    assert result["record_count"] == 1


def test_validate_approved_repair_training_export_reports_errors(tmp_path, monkeypatch) -> None:
    approved_path = tmp_path / "KENN" / "artifacts" / "training" / "creative_lab_repair_records.approved.jsonl"
    manifest_path = tmp_path / "KENN" / "artifacts" / "training" / "creative_lab_repair_records.approved.manifest.json"
    approved_path.parent.mkdir(parents=True)
    approved_path.write_text(json.dumps({"record_id": "r1", "review_decision": "needs_work"}) + "\n", encoding="utf-8")
    manifest_path.write_text(
        json.dumps(
            {
                "schema": "kenn.creative_repair_dataset_manifest.v1",
                "decision": "approved",
                "selected_records": 2,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(creative_lab_training, "CREATIVE_APPROVED_REPAIR_RECORDS_PATH", approved_path)
    monkeypatch.setattr(creative_lab_training, "CREATIVE_APPROVED_REPAIR_MANIFEST_PATH", manifest_path)

    result = creative_lab.validate_approved_repair_training_export()

    assert result["ok"] is True
    assert result["valid"] is False
    assert any("selected_records=2" in error for error in result["errors"])
    assert any("not marked approved" in error for error in result["errors"])


def test_record_feedback_links_bad_kenn_feedback(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(creative_lab_storage, "DATA_PATH", tmp_path / "creative_lab_sessions.json")
    linked = {}

    def fake_record_feedback(payload):
        linked.update(payload)
        return {"id": "fb1", **payload}

    monkeypatch.setattr(creative_lab.demo_feedback, "record_feedback", fake_record_feedback)

    result = creative_lab.record_feedback(
        {
            "rating": "bad_source",
            "target": "kenn",
            "question": "How do I widen vocals?",
            "answer": "Use unrelated advice.",
        }
    )

    assert result["ok"] is True
    assert result["linked_feedback"]["id"] == "fb1"
    assert linked["rating"] == "not_useful"
    assert linked["channel"] == "creative_lab"


def test_review_generated_audio_uses_portfolio_audio(tmp_path, monkeypatch) -> None:
    data_path = tmp_path / "creative_lab_sessions.json"
    audio_root = tmp_path / "Portfolio" / "audio"
    audio_root.mkdir(parents=True)
    wav_path = audio_root / "generated.wav"
    wav_path.write_bytes(tiny_wav_bytes(seconds=0.2))
    monkeypatch.setattr(creative_lab_storage, "DATA_PATH", data_path)
    monkeypatch.setattr(creative_lab_portfolio, "PORTFOLIO_AUDIO", audio_root)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "audio_too.db")
    monkeypatch.setattr(creative_lab.mix_review, "UPLOAD_ROOT", tmp_path / "mix_reviews" / "uploads")
    monkeypatch.setattr(creative_lab.mix_review, "REPORT_ROOT", tmp_path / "mix_reviews" / "reports")
    monkeypatch.setattr(creative_lab.mix_review, "REFERENCE_ROOT", tmp_path / "mix_reviews" / "references")

    result = creative_lab.review_generated_audio(
        {
            "session_id": "session-1",
            "src": "/portfolio/audio/generated.wav",
            "title": "Generated loop",
        }
    )

    assert result["ok"] is True
    assert result["review"]["title"] == "Generated loop"
    assert result["review"]["metrics"]["filename"] == "generated.wav"
    assert creative_lab.snapshot()["counts"]["sessions"] == 1
    assert creative_lab.snapshot()["metrics"]["mix_reviews"] == 1
