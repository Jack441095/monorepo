from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).with_name("merge_taxonomy_gap_adjudication_manifest.py")
SPEC = importlib.util.spec_from_file_location("slo_merge_taxonomy_gap", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _decision(audio: Path, label: str = "Synth") -> dict:
    return {
        "sample_id": "q1", "path": str(audio),
        "sha256": hashlib.sha256(audio.read_bytes()).hexdigest(),
        "filename": audio.name, "expected_subcategory": label,
        "ood": label == "OOD", "label_authority": "OWNER_ADJUDICATION",
    }


def test_merge_assigns_fresh_ids_and_blocks_duplicate_content(tmp_path: Path):
    base_audio = tmp_path / "base.wav"; base_audio.write_bytes(b"same")
    duplicate_audio = tmp_path / "base_alias.wav"; duplicate_audio.write_bytes(b"same")
    new_audio = tmp_path / "new.wav"; new_audio.write_bytes(b"new")
    base = [{"sample_id": 4, "path": str(base_audio),
             "sha256": hashlib.sha256(base_audio.read_bytes()).hexdigest(),
             "expected_subcategory": "Kick", "ood": False}]
    decisions = [_decision(duplicate_audio), _decision(new_audio, "OOD")]
    base_path = tmp_path / "base.json"; base_path.write_text(json.dumps(base))
    decision_path = tmp_path / "decisions.json"; decision_path.write_text(json.dumps(decisions))
    out = tmp_path / "merged.json"
    receipt = MODULE.merge_manifests(base_path, decision_path, out)
    merged = json.loads(out.read_text())
    assert len(merged) == 2
    assert merged[-1]["sample_id"] == 5
    assert merged[-1]["expected_subcategory"] == "OOD"
    assert receipt["accepted_rows"] == 1
    assert receipt["blocked_reason_counts"] == {"duplicate_content_existing": 1}


def test_merge_rejects_non_owner_decision(tmp_path: Path):
    audio = tmp_path / "sample.wav"; audio.write_bytes(b"audio")
    base_path = tmp_path / "base.json"; base_path.write_text("[]")
    bad = _decision(audio); bad["label_authority"] = "MODEL"
    decision_path = tmp_path / "decisions.json"; decision_path.write_text(json.dumps([bad]))
    with pytest.raises(ValueError, match="not owner-authorized"):
        MODULE.merge_manifests(base_path, decision_path, tmp_path / "out.json")
