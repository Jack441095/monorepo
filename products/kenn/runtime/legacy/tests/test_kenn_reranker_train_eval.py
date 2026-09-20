from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "eval"))

import kenn_reranker_eval  # noqa: E402
import kenn_reranker_train as train  # noqa: E402


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def sample_rows() -> list[dict]:
    return [
        {
            "id": "a-good",
            "case_id": "a",
            "question": "How do I sidechain bass to kick?",
            "source_label": "Sidechain Bass To Kick (sidechain-bass-to-kick.md)",
            "rank": 1,
            "label": 1,
            "topics": ["bass", "compression"],
            "source_kind": "note",
        },
        {
            "id": "a-bad",
            "case_id": "a",
            "question": "How do I sidechain bass to kick?",
            "source_label": "Podcast Dialogue Edit (podcast-dialogue-edit.md)",
            "rank": 2,
            "label": 0,
            "topics": ["bass", "compression"],
            "source_kind": "note",
        },
        {
            "id": "b-good",
            "case_id": "b",
            "question": "How do I clean podcast dialogue?",
            "source_label": "Podcast Dialogue Edit (podcast-dialogue-edit.md)",
            "rank": 1,
            "label": 1,
            "topics": ["podcast"],
            "source_kind": "note",
        },
        {
            "id": "b-bad",
            "case_id": "b",
            "question": "How do I clean podcast dialogue?",
            "source_label": "Sidechain Bass To Kick (sidechain-bass-to-kick.md)",
            "rank": 2,
            "label": 0,
            "topics": ["podcast"],
            "source_kind": "note",
        },
    ]


def test_train_model_writes_model_and_metrics(tmp_path) -> None:
    dataset = tmp_path / "pairs.jsonl"
    model = tmp_path / "model.json"
    metrics = tmp_path / "metrics.json"
    write_jsonl(dataset, sample_rows())

    payload = train.train_model(
        dataset=dataset,
        output=model,
        metrics_path=metrics,
        backend="linear",
        epochs=5,
        validation_ratio=0.5,
    )

    saved = json.loads(model.read_text(encoding="utf-8"))
    assert payload["backend"] == "linear"
    assert payload["total_rows"] == 4
    assert len(saved["weights"]) == len(saved["feature_names"])
    assert "baseline_rank" in payload["validation"]
    assert metrics.exists()


def test_evaluate_model_reads_saved_model(tmp_path) -> None:
    dataset = tmp_path / "pairs.jsonl"
    model = tmp_path / "model.json"
    output = tmp_path / "eval.json"
    write_jsonl(dataset, sample_rows())
    train.train_model(dataset=dataset, output=model, metrics_path=tmp_path / "metrics.json", backend="linear", epochs=5)

    payload = kenn_reranker_eval.evaluate_model(dataset=dataset, model_path=model, output=output)

    assert payload["total_rows"] == 4
    assert payload["all"]["rows"] == 4
    assert "top1" in payload["all"]["ranking"]
    assert "top1_delta" in payload["all"]
    assert output.exists()


def test_torch_backend_reports_missing_when_requested(tmp_path) -> None:
    dataset = tmp_path / "pairs.jsonl"
    write_jsonl(dataset, sample_rows())

    try:
        import torch  # noqa: F401
    except ModuleNotFoundError:
        try:
            train.train_model(dataset=dataset, backend="torch", output=tmp_path / "model.json", metrics_path=tmp_path / "m.json")
        except ModuleNotFoundError:
            return
        raise AssertionError("expected missing torch to raise")
