from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "eval"))

import kenn_reranker_export as reranker_export  # noqa: E402


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_examples_from_records_builds_positive_and_negative_pairs() -> None:
    records = [
        {
            "id": "case-1",
            "question": "How do I fix boxy vocals?",
            "eval_failures": [],
            "source_labels": ["Boxy Vocal Correction", "Drum Parallel Compression"],
            "source_kinds": ["note", "note"],
            "route": "production",
            "intent": "troubleshooting",
            "topics": ["vocals"],
        }
    ]

    rows = reranker_export.examples_from_records(records, [])

    assert [row["label"] for row in rows] == [1, 0]
    assert rows[0]["reason"] == "top source on passing eval"
    assert rows[1]["reason"] == "lower-ranked candidate"


def test_export_dataset_writes_manifest_and_torch_guidance(tmp_path) -> None:
    benchmark = tmp_path / "benchmark.jsonl"
    hard = tmp_path / "hard.jsonl"
    curated = tmp_path / "curated.jsonl"
    output = tmp_path / "pairs.jsonl"
    manifest_path = tmp_path / "manifest.json"
    write_jsonl(
        benchmark,
        [
            {
                "id": "case-1",
                "question": "Q",
                "eval_failures": [],
                "source_labels": ["Good Source", "Weak Source"],
                "source_kinds": ["note", "manual"],
            }
        ],
    )
    write_jsonl(
        hard,
        [
            {
                "case_id": "case-2",
                "question": "Bad source question",
                "negative_source_label": "Bad Source",
                "reason": "wrong top source",
            }
        ],
    )
    write_jsonl(
        curated,
        [
            {
                "case_id": "case-3",
                "question": "Curated bad source question",
                "negative_source_label": "Curated Bad Source",
                "reason": "reviewed curated hard negative",
            }
        ],
    )

    manifest = reranker_export.export_dataset(
        benchmark_jsonl=benchmark,
        hard_negatives_path=hard,
        curated_hard_negatives_path=curated,
        output=output,
        manifest_path=manifest_path,
    )

    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert manifest["pairs"] == 4
    assert manifest["positive"] == 1
    assert manifest["negative"] == 3
    assert manifest["curated_hard_negatives_path"] == str(curated)
    assert manifest["torch"]["torch_benefit"] == "not_yet"
    assert len(rows) == 4


def test_torch_guidance_waits_for_enough_labels() -> None:
    assert reranker_export.torch_guidance(50, 25, 25)["torch_benefit"] == "not_yet"
    assert reranker_export.torch_guidance(200, 50, 50)["torch_benefit"] == "yes_later"
