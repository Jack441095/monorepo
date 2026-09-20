from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).with_name("build_label_free_cluster_review_queue.py")
SPEC = importlib.util.spec_from_file_location("build_label_free_cluster_review_queue", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _manifest(path: Path) -> None:
    path.write_text(json.dumps({
        "record_type": "slo_label_free_cluster_manifest",
        "safety": {"read_only": True, "semantic_labels_created": False,
                    "rename_actions": False, "source_audio_modified": False},
        "rows": [
            {"path": "a.wav", "cluster_id": 1, "cluster_size": 2,
             "distance_to_cluster_centroid": 0.01, "semantic_label": None},
            {"path": "b.wav", "cluster_id": 1, "cluster_size": 2,
             "distance_to_cluster_centroid": 0.02, "semantic_label": None},
            {"path": "c.wav", "cluster_id": -1, "cluster_size": 1,
             "distance_to_cluster_centroid": None, "semantic_label": None},
        ],
    }), encoding="utf-8")


def test_build_queue_is_read_only_and_bounded(tmp_path: Path):
    source = tmp_path / "clusters.json"
    _manifest(source)
    out = tmp_path / "queue.json"
    result = MODULE.build(source, out, limit=1)
    assert result["n_source_clusters"] == 2
    assert result["n_queued_clusters"] == 1
    assert result["rows"][0]["discovery_status"] == "noise_review"
    assert result["rows"][0]["semantic_label"] is None


def test_rejects_mutating_manifest(tmp_path: Path):
    source = tmp_path / "clusters.json"
    _manifest(source)
    payload = json.loads(source.read_text())
    payload["safety"]["semantic_labels_created"] = True
    source.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="read-only"):
        MODULE.build(source, tmp_path / "out.json")
