"""Tests for the LLM improvement dashboard helpers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "server" / "app"))

import llm_improvement  # noqa: E402
import demo_feedback  # noqa: E402
import db  # noqa: E402


def test_snapshot_has_dashboard_sections() -> None:
    data = llm_improvement.snapshot()
    assert data["ok"] is True
    assert "gaps" in data
    assert "feedback" in data
    assert "agent_queue" in data
    assert "repair_plan" in data
    assert "recent_queries" in data
    assert data["commands"]["audit"] == "./audio-too audit"


def test_run_command_rejects_unknown() -> None:
    result = llm_improvement.run_command("not-real")
    assert result["ok"] is False
    assert "Unknown" in result["error"]


def test_improvement_queue_ranks_tester_feedback(monkeypatch) -> None:
    monkeypatch.setattr(llm_improvement.lm_gaps, "list_gaps_filtered", lambda **_: [])
    monkeypatch.setattr(
        llm_improvement.demo_feedback,
        "list_feedback",
        lambda **_: [
            {
                "id": "fb1",
                "question": "How do I fix harsh vocals?",
                "rating": "not_useful",
                "comment": "missed de-essing",
                "answer": "Talked about reverb instead.",
                "sources": [{"label": "Reverb note"}],
                "topics": ["vocals"],
                "top_source": "Reverb note",
                "confidence": "medium",
                "source_quality": "low",
            }
        ],
    )
    monkeypatch.setattr(llm_improvement.demo_feedback, "analytics", lambda **_: {"questions": []})
    monkeypatch.setattr(llm_improvement.tips_queries, "list_quality_issues", lambda **_: [])

    queue = llm_improvement.improvement_queue()

    assert queue["total"] == 1
    assert queue["items"][0]["source"] == "feedback"
    assert "harsh vocals" in queue["items"][0]["question"].lower()
    assert "reverb" in queue["items"][0]["answer_preview"].lower()
    assert queue["items"][0]["top_source"] == "Reverb note"


def test_improvement_queue_dedupes_signals(monkeypatch) -> None:
    monkeypatch.setattr(
        llm_improvement.lm_gaps,
        "list_gaps_filtered",
        lambda **_: [
            {
                "id": "gap1",
                "question": "How do I fix harsh vocals?",
                "confidence": "low",
                "topics": ["vocals"],
                "top_source": "",
            }
        ],
    )
    monkeypatch.setattr(
        llm_improvement.demo_feedback,
        "list_feedback",
        lambda **_: [
            {
                "id": "fb1",
                "question": "how do i fix harsh vocals?",
                "rating": "not_useful",
                "comment": "",
                "confidence": "low",
                "source_quality": "low",
            }
        ],
    )
    monkeypatch.setattr(llm_improvement.demo_feedback, "analytics", lambda **_: {"questions": []})
    monkeypatch.setattr(llm_improvement.tips_queries, "list_quality_issues", lambda **_: [])

    queue = llm_improvement.improvement_queue()

    assert queue["total"] == 1
    assert queue["items"][0]["evidence_count"] == 2
    assert queue["items"][0]["topics"] == ["vocals"]


def test_covered_eval_questions_reads_main_suite(tmp_path) -> None:
    suite = tmp_path / "questions.json"
    suite.write_text(
        json.dumps(
            {
                "version": 1,
                "cases": [
                    {"id": "sidechain", "question": "How do I sidechain bass to the kick?"},
                    {"id": "empty", "question": ""},
                ],
            }
        ),
        encoding="utf-8",
    )

    covered = llm_improvement.covered_eval_questions(suite)

    assert "how do i sidechain bass to the kick?" in covered
    assert "" not in covered


def test_improvement_queue_skips_exact_eval_covered_questions(tmp_path, monkeypatch) -> None:
    suite = tmp_path / "questions.json"
    suite.write_text(
        json.dumps(
            {
                "version": 1,
                "cases": [
                    {"id": "wide", "question": "How do I make vocals wide without mud?"},
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(llm_improvement, "MAIN_EVAL_PATH", suite)
    monkeypatch.setattr(llm_improvement.lm_gaps, "list_gaps_filtered", lambda **_: [])
    monkeypatch.setattr(
        llm_improvement.demo_feedback,
        "list_feedback",
        lambda **_: [
            {
                "id": "fb-covered",
                "question": "How do I make vocals wide without mud?",
                "rating": "not_useful",
                "comment": "already covered",
                "confidence": "high",
                "source_quality": "high",
            },
            {
                "id": "fb-open",
                "question": "How do I fix nasal vocals?",
                "rating": "not_useful",
                "comment": "needs a note",
                "confidence": "medium",
                "source_quality": "low",
            },
        ],
    )
    monkeypatch.setattr(llm_improvement.demo_feedback, "analytics", lambda **_: {"questions": []})
    monkeypatch.setattr(llm_improvement.tips_queries, "list_quality_issues", lambda **_: [])

    queue = llm_improvement.improvement_queue()

    assert queue["covered_skipped"] == 1
    assert queue["total"] == 1
    assert queue["items"][0]["question"] == "How do I fix nasal vocals?"


def test_is_fixture_repair_signal_is_narrow() -> None:
    assert llm_improvement.is_fixture_repair_signal(question="Dedupe test question alpha")
    assert llm_improvement.is_fixture_repair_signal(question="Any question", top_source="Test source")
    assert not llm_improvement.is_fixture_repair_signal(question="How do I test my mix translation?")


def test_improvement_queue_skips_fixture_signals(monkeypatch) -> None:
    monkeypatch.setattr(llm_improvement, "covered_eval_questions", lambda: set())
    monkeypatch.setattr(
        llm_improvement.lm_gaps,
        "list_gaps_filtered",
        lambda **_: [
            {
                "id": "fixture-gap",
                "question": "Dedupe test question alpha",
                "confidence": "low",
                "topics": ["mix"],
                "top_source": "",
            }
        ],
    )
    monkeypatch.setattr(
        llm_improvement.demo_feedback,
        "list_feedback",
        lambda **_: [
            {
                "id": "fixture-feedback",
                "question": "test feedback question",
                "rating": "not_useful",
                "comment": "fixture",
                "confidence": "medium",
                "source_quality": "low",
            },
            {
                "id": "real-feedback",
                "question": "How do I test my mix translation?",
                "rating": "not_useful",
                "comment": "real phrasing",
                "confidence": "medium",
                "source_quality": "low",
            },
        ],
    )
    monkeypatch.setattr(
        llm_improvement.demo_feedback,
        "analytics",
        lambda **_: {
            "questions": [
                {
                    "id": "fixture-demo",
                    "question": "some weak demo row",
                    "confidence": "low",
                    "source_quality": "low",
                    "top_source": "Test source",
                }
            ]
        },
    )
    monkeypatch.setattr(llm_improvement.tips_queries, "list_quality_issues", lambda **_: [])

    queue = llm_improvement.improvement_queue()

    assert queue["fixture_skipped"] == 3
    assert queue["total"] == 1
    assert queue["items"][0]["question"] == "How do I test my mix translation?"


def test_create_note_from_feedback_writes_repair_context(tmp_path, monkeypatch) -> None:
    sys.path.insert(0, str(ROOT / "studio" / "kenn"))
    from kenn.training import research  # noqa: E402

    monkeypatch.setattr(research, "NOTES_DIR", tmp_path / "notes")
    monkeypatch.setattr(research, "SOURCES_DIR", tmp_path / "sources")
    monkeypatch.setattr(research, "TRANSCRIPTS_DIR", tmp_path / "transcripts")
    monkeypatch.setattr(research, "SOURCES_PATH", tmp_path / "sources" / "sources.json")
    monkeypatch.setattr(research, "TRANSCRIPT_META_PATH", tmp_path / "sources" / "transcripts.json")
    # Isolate from the real production DB — this used to write straight into
    # data/audio_too.db on every test run, which is how demo_feedback ended up
    # dominated by synthetic test rows (docs/CAPABILITY_IMPROVEMENTS_2026-07-06.md).
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "isolated_feedback.db")

    row = demo_feedback.record_feedback(
        {
            "question": "How do I fix boxy vocals?",
            "rating": "not_useful",
            "comment": "It talked about drums.",
            "answer": "Use drum parallel compression.",
            "sources": [{"label": "Drum Parallel Compression"}],
            "topics": ["vocals", "eq"],
            "confidence": "medium",
            "source_quality": "low",
        }
    )

    result = llm_improvement.create_note_from_feedback(row["id"])

    assert result["ok"] is True
    note = tmp_path / "notes" / result["note"]
    text = note.read_text(encoding="utf-8")
    assert "It talked about drums." in text
    assert "Use drum parallel compression." in text
    assert "Drum Parallel Compression" in text
    updated = demo_feedback.get_feedback(row["id"])
    assert updated is not None
    assert updated["repair_status"] == "drafted"
    assert updated["repair_note"] == result["note"]


def test_repair_validation_requires_repair_note_source() -> None:
    row = {
        "repair_note": "boxy-vocals-repair.md",
        "top_source": "Drum Parallel Compression",
    }
    payload = {
        "confidence": "high",
        "source_quality": "high",
        "sources": [
            {
                "kind": "note",
                "label": "Boxy Vocals Repair (boxy-vocals-repair.md)",
                "source": "boxy-vocals-repair.md",
            }
        ],
    }

    result = llm_improvement.repair_validation(row, payload)

    assert result["resolved"] is True
    assert result["failed_checks"] == []


def test_repair_validation_fails_without_note_backing() -> None:
    row = {
        "repair_note": "boxy-vocals-repair.md",
        "top_source": "Drum Parallel Compression",
    }
    payload = {
        "confidence": "medium",
        "source_quality": "medium",
        "sources": [{"kind": "manual", "label": "live12-manual-en.pdf, page 12"}],
    }

    result = llm_improvement.repair_validation(row, payload)

    assert result["resolved"] is False
    assert "source_quality_ok" in result["failed_checks"]
    assert "repair_note_used" in result["failed_checks"]


def test_retest_feedback_repair_marks_needs_review(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "isolated_feedback.db")
    row = demo_feedback.record_feedback(
        {
            "question": "How do I fix boxy vocals?",
            "rating": "not_useful",
            "comment": "wrong",
            "answer": "old bad answer",
            "sources": [{"label": "Drum Parallel Compression"}],
            "confidence": "medium",
            "source_quality": "low",
        }
    )
    demo_feedback.mark_repair_status(row["id"], "drafted", note_file="boxy-vocals-repair.md")

    class FakeAbletonBridge:
        @staticmethod
        def ask(*_args, **_kwargs):
            return {
                "answer": "still weak",
                "confidence": "low",
                "source_quality": "low",
                "sources": [{"kind": "manual", "label": "live12-manual-en.pdf"}],
            }

    monkeypatch.setitem(sys.modules, "ableton_bridge", FakeAbletonBridge)

    result = llm_improvement.retest_feedback_repair(row["id"])

    assert result["ok"] is True
    assert result["status"] == "needs_review"
    updated = demo_feedback.get_feedback(row["id"])
    assert updated is not None
    assert updated["repair_status"] == "needs_review"
    assert updated["repair_last_answer"] == "still weak"


def test_draft_eval_from_feedback_writes_review_suite(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(llm_improvement, "DRAFT_EVAL_PATH", tmp_path / "draft_feedback_cases.json")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "isolated_feedback.db")
    row = demo_feedback.record_feedback(
        {
            "question": "How do I make vocals wide without mud?",
            "rating": "not_useful",
            "comment": "It answered about de-essing instead.",
            "answer": "Use a de-esser.",
            "sources": [{"label": "Vocal De-Essing And Sibilance"}],
            "topics": ["vocals", "stereo_width"],
            "confidence": "high",
            "source_quality": "high",
        }
    )

    result = llm_improvement.draft_eval_from_feedback(row["id"])

    assert result["ok"] is True
    data = json.loads((tmp_path / "draft_feedback_cases.json").read_text(encoding="utf-8"))
    assert len(data["cases"]) == 1
    case = data["cases"][0]
    assert case["question"] == "How do I make vocals wide without mud?"
    assert case["source_kinds_any"] == ["note"]
    assert "stereo_width" in case["topics_must_include"]
    assert "wide" in case["answer_must_include"]


def test_training_records_snapshot_merges_reviews(tmp_path, monkeypatch) -> None:
    artifacts = tmp_path / "artifacts"
    records_path = artifacts / "benchmarks" / "kenn_answer_records_test.jsonl"
    records_path.parent.mkdir(parents=True)
    records_path.write_text(
        json.dumps(
            {
                "schema": "kenn.answer_record.v1",
                "case_id": "case-wide-vocals",
                "question": "How do I make vocals wide without mud?",
                "route": "production",
                "intent": "troubleshooting",
                "confidence": "high",
                "source_quality": "high",
                "top_source_label": "Vocal Width Without Mud",
                "top_source_kind": "note",
                "eval_passed": True,
                "eval_failures": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(llm_improvement, "ARTIFACTS", artifacts)
    monkeypatch.setattr(llm_improvement, "TRAINING_REVIEW_PATH", artifacts / "training" / "kenn_review_labels.json")
    monkeypatch.setattr(
        llm_improvement,
        "REVIEWED_TRAINING_PATH",
        artifacts / "training" / "kenn_reviewed_answer_records.jsonl",
    )

    saved = llm_improvement.save_training_review(
        {
            "id": "case-wide-vocals",
            "route_correct": True,
            "intent_correct": False,
            "top_source_correct": True,
            "answer_policy": "should_answer",
            "notes": "Intent was too broad.",
        }
    )
    snapshot = llm_improvement.training_records_snapshot()

    assert saved["ok"] is True
    assert snapshot["summary"]["total"] == 1
    assert snapshot["summary"]["reviewed"] == 1
    assert snapshot["summary"]["intent_incorrect"] == 1
    assert snapshot["items"][0]["review"]["notes"] == "Intent was too broad."
    assert "route disputed" not in snapshot["items"][0]["review_priority"]["reasons"]
    assert "intent disputed" in snapshot["items"][0]["review_priority"]["reasons"]


def test_export_reviewed_training_writes_jsonl(tmp_path, monkeypatch) -> None:
    artifacts = tmp_path / "artifacts"
    records_path = artifacts / "training" / "kenn_answer_records.jsonl"
    records_path.parent.mkdir(parents=True)
    records_path.write_text(
        json.dumps(
            {
                "schema": "kenn.answer_record.v1",
                "case_id": "case-off-topic",
                "question": "Can you write my tax return?",
                "route": "out_of_scope",
                "intent": "fallback",
                "confidence": "low",
                "source_quality": "low",
                "top_source_label": "",
                "top_source_kind": "",
                "eval_passed": False,
                "eval_failures": ["should fallback"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(llm_improvement, "ARTIFACTS", artifacts)
    monkeypatch.setattr(llm_improvement, "TRAINING_REVIEW_PATH", artifacts / "training" / "kenn_review_labels.json")
    monkeypatch.setattr(
        llm_improvement,
        "REVIEWED_TRAINING_PATH",
        artifacts / "training" / "kenn_reviewed_answer_records.jsonl",
    )
    llm_improvement.save_training_review(
        {
            "id": "case-off-topic",
            "route_correct": True,
            "intent_correct": True,
            "top_source_correct": False,
            "answer_policy": "should_fallback",
        }
    )

    result = llm_improvement.export_reviewed_training()

    assert result["ok"] is True
    output = artifacts / "training" / "kenn_reviewed_answer_records.jsonl"
    exported = json.loads(output.read_text(encoding="utf-8").strip())
    assert exported["case_id"] == "case-off-topic"
    assert exported["review"]["answer_policy"] == "should_fallback"
    assert exported["review"]["top_source_correct"] is False


def test_training_diagnostics_and_hard_negatives(tmp_path, monkeypatch) -> None:
    artifacts = tmp_path / "artifacts"
    records_path = artifacts / "training" / "kenn_answer_records.jsonl"
    records_path.parent.mkdir(parents=True)
    records_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "schema": "kenn.answer_record.v1",
                        "case_id": "case-wrong-source",
                        "question": "How do I make vocals wide?",
                        "route": "production",
                        "intent": "troubleshooting",
                        "topics": ["vocals", "stereo_width"],
                        "confidence": "high",
                        "source_quality": "high",
                        "top_source": "vocal-deessing-and-sibilance.md",
                        "top_source_label": "Vocal De-Essing And Sibilance",
                        "top_source_kind": "note",
                        "eval_passed": True,
                        "eval_failures": [],
                    }
                ),
                json.dumps(
                    {
                        "schema": "kenn.answer_record.v1",
                        "case_id": "case-fallback",
                        "question": "Can you do my tax return?",
                        "route": "out_of_scope",
                        "intent": "out_of_scope",
                        "topics": [],
                        "confidence": "low",
                        "source_quality": "low",
                        "top_source": "",
                        "top_source_label": "",
                        "top_source_kind": "",
                        "eval_passed": True,
                        "eval_failures": [],
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(llm_improvement, "ARTIFACTS", artifacts)
    monkeypatch.setattr(llm_improvement, "TRAINING_REVIEW_PATH", artifacts / "training" / "kenn_review_labels.json")
    monkeypatch.setattr(
        llm_improvement,
        "REVIEWED_TRAINING_PATH",
        artifacts / "training" / "kenn_reviewed_answer_records.jsonl",
    )
    monkeypatch.setattr(llm_improvement, "HARD_NEGATIVES_PATH", artifacts / "training" / "kenn_hard_negatives.jsonl")
    monkeypatch.setattr(llm_improvement, "ROUTE_MEMORY_PATH", artifacts / "training" / "kenn_route_memory.jsonl")
    llm_improvement.save_training_review(
        {
            "id": "case-wrong-source",
            "route_correct": True,
            "intent_correct": True,
            "top_source_correct": False,
            "answer_policy": "should_answer",
        }
    )
    llm_improvement.save_training_review(
        {
            "id": "case-fallback",
            "route_correct": True,
            "intent_correct": True,
            "top_source_correct": True,
            "answer_policy": "should_fallback",
        }
    )

    snapshot = llm_improvement.training_records_snapshot()
    result = llm_improvement.export_hard_negatives()

    assert snapshot["diagnostics"]["issue_count"] == 2
    assert snapshot["diagnostics"]["issue_topics"][0]["label"] == "stereo_width"
    assert result["ok"] is True
    assert result["count"] == 1
    exported = json.loads((artifacts / "training" / "kenn_hard_negatives.jsonl").read_text(encoding="utf-8").strip())
    assert exported["case_id"] == "case-wrong-source"
    assert exported["negative_source"] == "vocal-deessing-and-sibilance.md"
    assert exported["reason"] == "wrong top source"


def test_export_route_memory_writes_fallback_records(tmp_path, monkeypatch) -> None:
    artifacts = tmp_path / "artifacts"
    records_path = artifacts / "training" / "kenn_answer_records.jsonl"
    records_path.parent.mkdir(parents=True)
    records_path.write_text(
        json.dumps(
            {
                "schema": "kenn.answer_record.v1",
                "case_id": "case-tax",
                "question": "best tax setup for a music business",
                "route": "production",
                "intent": "general",
                "topics": ["mixing"],
                "confidence": "high",
                "source_quality": "high",
                "top_source": "deliver-final-mix-to-client.md",
                "top_source_label": "Deliver Final Mix To Client",
                "top_source_kind": "note",
                "eval_passed": True,
                "eval_failures": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(llm_improvement, "ARTIFACTS", artifacts)
    monkeypatch.setattr(llm_improvement, "TRAINING_REVIEW_PATH", artifacts / "training" / "kenn_review_labels.json")
    monkeypatch.setattr(
        llm_improvement,
        "REVIEWED_TRAINING_PATH",
        artifacts / "training" / "kenn_reviewed_answer_records.jsonl",
    )
    monkeypatch.setattr(llm_improvement, "HARD_NEGATIVES_PATH", artifacts / "training" / "kenn_hard_negatives.jsonl")
    monkeypatch.setattr(llm_improvement, "ROUTE_MEMORY_PATH", artifacts / "training" / "kenn_route_memory.jsonl")
    llm_improvement.save_training_review(
        {
            "id": "case-tax",
            "route_correct": False,
            "intent_correct": False,
            "top_source_correct": False,
            "answer_policy": "should_fallback",
        }
    )

    snapshot = llm_improvement.training_records_snapshot()
    result = llm_improvement.export_route_memory()

    assert snapshot["diagnostics"]["route_confusion"][0]["label"] == "production -> fallback"
    assert result["ok"] is True
    assert result["count"] == 1
    exported = json.loads((artifacts / "training" / "kenn_route_memory.jsonl").read_text(encoding="utf-8").strip())
    assert exported["case_id"] == "case-tax"
    assert exported["target_route"] == "out_of_scope"
    assert exported["reason"] == "should fallback"


def test_repair_plan_prioritizes_training_labels() -> None:
    plan = llm_improvement.repair_plan(
        gaps={"open": 2, "drafted": 1},
        feedback={"needs_work": 1},
        agent_queue={"total": 1, "items": [{"question": "How do I make vocals wide?"}]},
        quality_queue={"total": 1, "items": [{"question": "Why is this answer weak?"}]},
        training={
            "summary": {
                "source_incorrect": 2,
                "should_fallback": 1,
                "route_incorrect": 1,
                "intent_incorrect": 0,
            },
            "diagnostics": {
                "issue_topics": [{"label": "vocals", "count": 3}],
            },
        },
    )

    titles = [item["title"] for item in plan["items"]]
    assert titles[0] == "Train retrieval away from bad matches"
    assert "Tighten routing and fallback behaviour" in titles
    assert "Repair the top live weak answer" in titles
    assert plan["items"][0]["command"] == "./audio-too eval"
