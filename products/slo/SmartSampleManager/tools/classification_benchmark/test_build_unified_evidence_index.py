from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from build_unified_evidence_index import build_records


def _identity(paths: list[str], hashes: list[str]) -> dict:
    return {"rows": [
        {"path": path, "content_sha256": digest, "size_bytes": 12}
        for path, digest in zip(paths, hashes)
    ]}


def test_builds_one_record_per_content_and_retains_aliases(tmp_path: Path):
    first = str(tmp_path / "a.wav")
    alias = str(tmp_path / "alias.wav")
    other = str(tmp_path / "b.wav")
    duplicate_hash = "a" * 64
    other_hash = "b" * 64
    embedding_index = {
        "model_version": "test_embedding_v1",
        "embedding_dimensions": 4,
        "records": [
            {"content_sha256": duplicate_hash, "embedding_row_indices": [0, 1],
             "paths": [first, alias], "size_bytes": 12},
            {"content_sha256": other_hash, "embedding_row_indices": [2],
             "paths": [other], "size_bytes": 12},
        ],
    }
    records, summary = build_records(
        embedding_index,
        _identity([first, alias, other], [duplicate_hash, duplicate_hash, other_hash]),
        {}, {},
    )
    assert len(records) == 2
    assert summary["n_embedding_paths"] == 3
    assert summary["n_content_ids"] == 2
    assert summary["n_alias_paths"] == 1
    duplicate = next(item for item in records if item["content_id"] == f"sha256:{duplicate_hash}")
    assert duplicate["source_path"] == first
    assert duplicate["metadata"]["aliases"] == sorted([first, alias])
    assert duplicate["duplicate_group"] == f"exact:{duplicate_hash}"
    assert duplicate["metadata"]["embedding"]["row_indices"] == [0, 1]


def test_predictions_and_physics_are_provenance_bearing(tmp_path: Path):
    path = str(tmp_path / "kick.wav")
    digest = "c" * 64
    embedding_index = {
        "model_version": "test_embedding_v1", "embedding_dimensions": 2,
        "records": [{"content_sha256": digest, "embedding_row_indices": [7],
                      "paths": [path], "size_bytes": 10}],
    }
    records, summary = build_records(
        embedding_index,
        _identity([path], [digest]),
        {path: {"fundamental_hz": 55.0, "attack_ms": 2.0}},
        {path: {"path": path, "fused_taxonomy_class": "Kick",
                "fused_taxonomy_confidence": 0.88,
                "fusion_source": "full_taxonomy_audio", "action": "review"}},
    )
    record = records[0]
    assert record["identity"]["value"] == "Kick"
    assert record["family"]["value"] == "Kick"
    assert record["form"]["state"] == "unknown"
    assert record["measurements"]["fundamental_hz"]["unit"] == "Hz"
    assert record["measurements"]["attack_ms"]["unit"] == "milliseconds"
    assert record["metadata"]["prediction"]["source"] == "full_taxonomy_audio"
    assert record["metadata"]["provenance"]["prediction_path"] == path
    assert summary["n_with_predictions"] == 1
    assert summary["n_with_acoustic_measurements"] == 1
    assert record["legacy"]["prediction_present"] is True


def test_out_of_index_inputs_are_reported_not_joined(tmp_path: Path):
    path = str(tmp_path / "known.wav")
    external = str(tmp_path / "external.wav")
    digest = "d" * 64
    embedding_index = {
        "model_version": "test_embedding_v1", "embedding_dimensions": 2,
        "records": [{"content_sha256": digest, "embedding_row_indices": [0],
                      "paths": [path], "size_bytes": 1}],
    }
    records, summary = build_records(
        embedding_index, _identity([path], [digest]),
        {external: {"attack_ms": 2.0}},
        {external: {"path": external, "fused_taxonomy_class": "Kick",
                    "fused_taxonomy_confidence": 1.0}},
    )
    assert len(records) == 1
    assert summary["n_acoustic_paths_outside_embedding_index"] == 1
    assert summary["n_prediction_paths_outside_embedding_index"] == 1
    assert records[0]["measurements"] == {}
    assert records[0]["metadata"].get("prediction") is None
