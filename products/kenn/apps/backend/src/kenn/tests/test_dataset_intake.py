from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from kenn.training.dataset_intake import DatasetManifestError, audit_manifest, load_manifest


def test_huggingface_candidate_manifest_is_quarantined_and_lane_bound() -> None:
    payload = load_manifest()
    report = audit_manifest(payload)

    assert report["candidate_count"] == 7
    assert report["external_count"] == 7
    assert report["download_allowed_count"] == 0
    assert report["training_allowed_count"] == 0
    assert report["control_supervision_allowed"] is False
    assert report["lanes"] == {"evaluation": 1, "knowledge": 2, "perception": 2, "symbolic": 2}


def test_dataset_manifest_is_repository_owned_json() -> None:
    path = Path(__file__).parents[1] / "training" / "huggingface_dataset_candidates.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema"] == "kenn.huggingface_dataset_manifest.v1"
    assert all(row["hub_url"].startswith("https://huggingface.co/datasets/") for row in payload["candidates"])


def test_external_control_supervision_is_rejected() -> None:
    payload = load_manifest()
    candidate = copy.deepcopy(payload["candidates"][0])
    candidate["control_supervision"] = True
    with pytest.raises(DatasetManifestError, match="cannot provide Ableton control supervision"):
        audit_manifest({**payload, "candidates": [candidate]})


def test_unknown_terms_are_blocked() -> None:
    payload = load_manifest()
    candidate = copy.deepcopy(payload["candidates"][0])
    candidate["underlying_terms"] = ""
    with pytest.raises(DatasetManifestError, match="underlying_terms must be explicit"):
        audit_manifest({**payload, "candidates": [candidate]})


def test_evaluation_lane_cannot_be_used_as_training() -> None:
    payload = load_manifest()
    candidate = copy.deepcopy(payload["candidates"][5])
    candidate["use_classification"] = "research_only"
    with pytest.raises(DatasetManifestError, match="evaluation lane must be evaluation_only"):
        audit_manifest({**payload, "candidates": [candidate]})

