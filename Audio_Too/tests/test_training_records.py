"""Tests for KENN ML-ready record export helpers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "studio" / "kenn"))
sys.path.insert(0, str(ROOT / "scripts"))

import pytest  # noqa: E402

import export_creative_repair_training as creative_repair_export  # noqa: E402
from kenn.training.training_records import (  # noqa: E402
    JsonlParseError,
    answer_record,
    iter_jsonl_raw,
    read_jsonl,
    write_jsonl,
)


def test_answer_record_has_stable_training_schema() -> None:
    case = {
        "id": "mix-order",
        "question": "what order should I mix in",
        "topics_must_include": ["mixing"],
        "source_must_include": ["mixing-chain-order"],
    }
    payload = {
        "question": case["question"],
        "route": "production",
        "intent": "explain",
        "topics": ["mixing"],
        "confidence": "high",
        "source_quality": "high",
        "intent_guard": "not_needed",
        "weak_match": False,
        "found": True,
        "grounding_mode": "strong",
        "grounding": {"score": 91, "warnings": []},
        "answer_self_check": {"score": 88, "warnings": []},
        "sources": [
            {
                "source": "mixing-chain-order.md",
                "label": "Mixing Chain Order (mixing-chain-order.md)",
                "kind": "note",
                "score": 12.5,
            }
        ],
        "answer": "A practical order is balance, EQ, dynamics, tone, space, automation.",
    }

    record = answer_record(case, payload, [])

    assert record["schema"] == "kenn.answer_record.v1"
    assert record["case_id"] == "mix-order"
    assert record["route"] == "production"
    assert record["top_source"] == "mixing-chain-order.md"
    assert record["top_source_score"] == 12.5
    assert record["grounding_mode"] == "strong"
    assert record["grounding_score"] == 91
    assert record["answer_self_check_score"] == 88
    assert record["eval_passed"] is True


def test_write_jsonl_writes_records(tmp_path) -> None:
    path = write_jsonl(tmp_path / "records.jsonl", [{"schema": "test", "value": 1}])

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert rows == [{"schema": "test", "value": 1}]


def test_creative_repair_export_filters_reviewed_records(tmp_path) -> None:
    raw = tmp_path / "creative_lab_repair_records.jsonl"
    reviews = {
        "version": 1,
        "reviews": {
            "r1": {"decision": "approved", "note": "Good."},
            "r2": {"decision": "needs_work", "note": "Thin answer."},
        },
    }
    raw.write_text(
        "\n".join(
            [
                json.dumps({"schema": "kenn.creative_repair_record.v1", "record_id": "r1", "label": "good_repair"}),
                json.dumps({"schema": "kenn.creative_repair_record.v1", "record_id": "r2", "label": "needs_repair"}),
                "not-json",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    review_path = tmp_path / "reviews.json"
    review_path.write_text(json.dumps(reviews), encoding="utf-8")

    records, skipped = creative_repair_export.read_jsonl(raw)
    loaded_reviews = creative_repair_export.load_reviews(review_path)
    selected = creative_repair_export.reviewed_records(records, loaded_reviews, "approved")
    summary = creative_repair_export.summarize(records, loaded_reviews)

    assert skipped == 1
    assert len(records) == 2
    assert selected[0]["record_id"] == "r1"
    assert selected[0]["review_decision"] == "approved"
    assert summary["review_counts"] == {"approved": 1, "needs_work": 1}
    assert summary["label_counts"] == {"good_repair": 1, "needs_repair": 1}


def test_creative_repair_export_manifest_summarizes_dataset(tmp_path) -> None:
    records = [
        {"record_id": "r1", "label": "good_repair"},
        {"record_id": "r2", "label": "needs_repair"},
    ]
    reviews = {
        "r1": {"decision": "approved"},
        "r2": {"decision": "rejected"},
    }
    selected = creative_repair_export.reviewed_records(records, reviews, "approved")
    manifest = creative_repair_export.build_manifest(
        raw_path=tmp_path / "raw.jsonl",
        reviews_path=tmp_path / "reviews.json",
        output_path=tmp_path / "approved.jsonl",
        decision="approved",
        records=records,
        selected=selected,
        skipped=1,
        reviews=reviews,
    )
    path = creative_repair_export.write_manifest(tmp_path / "manifest.json", manifest)
    saved = json.loads(path.read_text(encoding="utf-8"))

    assert saved["schema"] == "kenn.creative_repair_dataset_manifest.v1"
    assert saved["raw_records"] == 2
    assert saved["selected_records"] == 1
    assert saved["skipped_rows"] == 1
    assert saved["review_counts"] == {"approved": 1, "rejected": 1}
    assert saved["selected_label_counts"] == {"good_repair": 1}


def test_creative_repair_export_validation_accepts_matching_manifest(tmp_path) -> None:
    output = tmp_path / "approved.jsonl"
    manifest_path = tmp_path / "manifest.json"
    records = [{"record_id": "r1", "label": "good_repair", "review_decision": "approved"}]
    creative_repair_export.write_jsonl(output, records)
    creative_repair_export.write_manifest(
        manifest_path,
        {
            "schema": "kenn.creative_repair_dataset_manifest.v1",
            "decision": "approved",
            "selected_records": 1,
        },
    )

    ok, errors = creative_repair_export.validate_export(output, manifest_path)

    assert ok is True
    assert errors == []


def test_creative_repair_export_validation_rejects_mismatched_manifest(tmp_path) -> None:
    output = tmp_path / "approved.jsonl"
    manifest_path = tmp_path / "manifest.json"
    creative_repair_export.write_jsonl(output, [{"record_id": "r1", "review_decision": "needs_work"}])
    creative_repair_export.write_manifest(
        manifest_path,
        {
            "schema": "kenn.creative_repair_dataset_manifest.v1",
            "decision": "approved",
            "selected_records": 2,
        },
    )

    ok, errors = creative_repair_export.validate_export(output, manifest_path)

    assert ok is False
    assert any("selected_records=2" in error for error in errors)
    assert any("not marked approved" in error for error in errors)


# --- Canonical read_jsonl / iter_jsonl_raw (shared across KENN training/eval tooling) ---


def test_read_jsonl_happy_path_returns_parsed_rows(tmp_path) -> None:
    path = tmp_path / "rows.jsonl"
    path.write_text(
        "\n".join([json.dumps({"a": 1}), json.dumps({"b": 2})]) + "\n",
        encoding="utf-8",
    )

    rows = read_jsonl(path)

    assert rows == [{"a": 1}, {"b": 2}]


def test_read_jsonl_missing_file_returns_empty_list_by_default(tmp_path) -> None:
    assert read_jsonl(tmp_path / "does-not-exist.jsonl") == []
    assert read_jsonl(None) == []


def test_read_jsonl_missing_file_raises_when_missing_ok_is_false(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        read_jsonl(tmp_path / "does-not-exist.jsonl", missing_ok=False)


def test_read_jsonl_empty_file_returns_empty_list(tmp_path) -> None:
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")

    assert read_jsonl(path) == []


def test_read_jsonl_skips_blank_and_whitespace_only_lines(tmp_path) -> None:
    path = tmp_path / "blank.jsonl"
    path.write_text('{"a": 1}\n\n   \n{"a": 2}\n', encoding="utf-8")

    assert read_jsonl(path) == [{"a": 1}, {"a": 2}]


def test_read_jsonl_raises_jsonl_parse_error_on_malformed_line(tmp_path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text('{"a": 1}\nnot-json\n{"a": 3}\n', encoding="utf-8")

    with pytest.raises(JsonlParseError) as exc_info:
        read_jsonl(path)

    message = str(exc_info.value)
    assert str(path) in message
    assert ":2:" in message


def test_read_jsonl_raises_on_non_object_json_line(tmp_path) -> None:
    path = tmp_path / "nonobj.jsonl"
    path.write_text('{"a": 1}\n[1, 2, 3]\n', encoding="utf-8")

    with pytest.raises(JsonlParseError, match="row must be a JSON object"):
        read_jsonl(path)


def test_iter_jsonl_raw_reports_line_numbers_and_errors_without_raising(tmp_path) -> None:
    path = tmp_path / "mixed.jsonl"
    path.write_text('{"ok": 1}\nnot-json\n[1]\n{"ok": 2}\n', encoding="utf-8")

    results = list(iter_jsonl_raw(path))

    assert [r[0] for r in results] == [1, 2, 3, 4]
    assert results[0][2] == {"ok": 1} and results[0][3] is None
    assert results[1][2] is None and "invalid JSON" in results[1][3]
    assert results[2][2] is None and "row must be a JSON object" in results[2][3]
    assert results[3][2] == {"ok": 2} and results[3][3] is None


def test_iter_jsonl_raw_yields_nothing_for_missing_file(tmp_path) -> None:
    assert list(iter_jsonl_raw(tmp_path / "missing.jsonl")) == []


def test_write_jsonl_overwrites_rather_than_appends(tmp_path) -> None:
    path = tmp_path / "records.jsonl"
    write_jsonl(path, [{"first": True}])
    write_jsonl(path, [{"second": True}])

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert rows == [{"second": True}]


def test_write_jsonl_sort_keys_option(tmp_path) -> None:
    path = tmp_path / "sorted.jsonl"
    write_jsonl(path, [{"z": 1, "a": 2}], sort_keys=True)

    assert path.read_text(encoding="utf-8") == '{"a": 2, "z": 1}\n'
