"""Tests for the KENN readiness report."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "eval"))

import kenn_readiness  # noqa: E402
from kenn.retrieval.index_store import promote_index  # noqa: E402


def test_build_report_reads_index_training_and_audit(tmp_path, monkeypatch) -> None:
    root = tmp_path
    kenn = root / "KENN"
    index = kenn / "data" / "index"
    notes = kenn / "Training_Data_Notes"
    pdfs = kenn / "Training_Data_PDF"
    transcripts = kenn / "Training_Data_Transcripts"
    evals = kenn / "evals"
    training = kenn / "artifacts" / "training"
    audits = kenn / "artifacts" / "audits"
    for path in (index, notes, pdfs, transcripts, evals, training, audits):
        path.mkdir(parents=True)

    (index / "chunks.jsonl").write_text('{"id":"a"}\n{"id":"b"}\n', encoding="utf-8")
    (index / "terms.json").write_text(json.dumps({"version": 2, "total_docs": 2}), encoding="utf-8")
    (notes / "gain.md").write_text("# Gain\n", encoding="utf-8")
    (pdfs / "manual.pdf").write_bytes(b"%PDF-1.4\n")
    (transcripts / "lesson.txt").write_text("lesson", encoding="utf-8")
    (evals / "questions.json").write_text(json.dumps({"cases": [{"id": "one"}, {"id": "two"}]}), encoding="utf-8")
    (training / "creative_lab_repair_records.jsonl").write_text('{"record_id":"r1","label":"bad"}\n', encoding="utf-8")
    (training / "creative_lab_repair_reviews.json").write_text(
        json.dumps({"reviews": {"r1": {"decision": "approved"}}}),
        encoding="utf-8",
    )
    (training / "creative_lab_repair_records.approved.jsonl").write_text(
        '{"record_id":"r1","review_decision":"approved"}\n',
        encoding="utf-8",
    )
    (training / "creative_lab_repair_records.approved.manifest.json").write_text(
        json.dumps({"schema": "kenn.creative_repair_dataset_manifest.v1", "selected_records": 1}),
        encoding="utf-8",
    )
    (audits / "ableton_audit_20260617T120000Z.json").write_text(json.dumps({"status": "pass"}), encoding="utf-8")

    monkeypatch.setattr(kenn_readiness, "ROOT", root)
    monkeypatch.setattr(kenn_readiness, "KENN", kenn)
    monkeypatch.setattr(kenn_readiness, "INDEX_DIR", index)
    monkeypatch.setattr(kenn_readiness, "CHUNKS_PATH", index / "chunks.jsonl")
    monkeypatch.setattr(kenn_readiness, "TERMS_PATH", index / "terms.json")
    monkeypatch.setattr(kenn_readiness, "NOTES_DIR", notes)
    monkeypatch.setattr(kenn_readiness, "PDF_DIR", pdfs)
    monkeypatch.setattr(kenn_readiness, "EVAL_SUITE", evals / "questions.json")
    monkeypatch.setattr(kenn_readiness, "TRAINING_DIR", training)
    monkeypatch.setattr(kenn_readiness, "AUDITS_DIR", audits)
    monkeypatch.setattr(kenn_readiness, "port_open", lambda port, host="127.0.0.1": port == 8090)

    report = kenn_readiness.build_report()

    assert report["status"] == "ready"
    assert report["services"]["kenn_8090"] is True
    assert report["services"]["website_8080"] is False
    assert report["sources"] == {
        "notes": 1,
        "approved_notes": 0,
        "pdfs": 1,
        "reference_only_pdfs": 0,
        "transcripts": 1,
        "eval_cases": 2,
        "held_out_eval_cases": 2,
    }
    assert report["index"]["counts_match"] is True
    assert report["index"]["storage"] == "legacy"
    assert report["index"]["manifest_valid"] is False
    assert report["index"]["manifest_schema_version"] == 0
    assert report["repair_training"]["approved_records"] == 1
    assert report["repair_training"]["manifest_ok"] is True
    assert report["latest_audit"]["status"] == "pass"
    assert not report["issues"]
    assert report["warnings"] == ["Website service is offline on :8080; run ./audio-too start --no-open before demos."]


def test_index_summary_resolves_and_validates_promoted_version(tmp_path, monkeypatch) -> None:
    chunks = [{"id": "one", "source": "one.md", "text": "one", "kind": "note"}]
    terms = {
        "version": 3,
        "total_docs": 1,
        "lengths": [1],
        "term_counts": [{"one": 1}],
        "idf": {"one": 1.0},
    }
    version = promote_index(chunks, terms, index_dir=tmp_path)
    monkeypatch.setattr(kenn_readiness, "INDEX_DIR", tmp_path)
    monkeypatch.setattr(kenn_readiness, "CHUNKS_PATH", tmp_path / "chunks.jsonl")
    monkeypatch.setattr(kenn_readiness, "TERMS_PATH", tmp_path / "terms.json")

    summary = kenn_readiness.index_summary()

    assert summary["chunks"] == 1
    assert summary["counts_match"] is True
    assert summary["storage"] == "versioned"
    assert summary["active_version"] == version
    assert summary["manifest_valid"] is True
    assert summary["manifest_schema_version"] == 1
    assert summary["content_sha256"]
