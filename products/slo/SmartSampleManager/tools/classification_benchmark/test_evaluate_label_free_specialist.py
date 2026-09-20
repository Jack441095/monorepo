from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("evaluate_label_free_specialist.py")
SPEC = importlib.util.spec_from_file_location("evaluate_label_free_specialist", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _inputs(tmp_path: Path) -> tuple[Path, Path]:
    receipt = tmp_path / "receipt.jsonl"
    header = {
        "record_type": "slo_label_free_specialist_receipt",
        "specialist_prompt_banks": {"music_sample": {"Kick": ["kick"], "Snare": ["snare"]}},
        "safety": {"read_only": True, "semantic_labels_created": False,
                   "rename_actions": False},
    }
    rows = [
        {"path": "/mnt/sample_pack_testing/Pack/a.wav", "semantic_label": None,
         "domain_suggestion": "music_sample", "specialist_status": "scored",
         "specialist_suggestion": "Kick", "status": "suggest"},
        {"path": "/mnt/sample_pack_testing/Pack/b.wav", "semantic_label": None,
         "domain_suggestion": "music_sample", "specialist_status": "scored",
         "specialist_suggestion": "Kick", "status": "review"},
        {"path": "/mnt/sample_pack_testing/Pack/c.wav", "semantic_label": None,
         "domain_suggestion": "music_sample", "specialist_status": "scored",
         "specialist_suggestion": "Snare", "status": "suggest"},
    ]
    receipt.write_text("\n".join(json.dumps(x) for x in [header, *rows]) + "\n", encoding="utf-8")
    labels = tmp_path / "labels.csv"
    with labels.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["path", "label"])
        writer.writeheader()
        writer.writerows([
            {"path": "/Volumes/library/sample_pack_testing/Pack/a.wav", "label": "Kick"},
            {"path": "/Volumes/library/sample_pack_testing/Pack/b.wav", "label": "Snare"},
            {"path": "/Volumes/library/sample_pack_testing/Pack/c.wav", "label": "Percussion"},
        ])
    return receipt, labels


def test_evaluate_exact_intersection_and_reports_suggestion_precision(tmp_path: Path):
    receipt, labels = _inputs(tmp_path)
    result = MODULE.evaluate(receipt, labels, tmp_path / "out.json")
    assert result["n_path_overlap"] == 3
    assert result["n_unsupported_taxonomy"] == 1
    assert result["n_evaluated"] == 2
    assert result["n_domain_consistent_evaluated"] == 2
    assert result["overall"]["n_correct"] == 1
    assert result["overall"]["n_suggested"] == 1
    assert result["overall"]["suggestion_precision"] == 1.0
    assert result["auto_action_allowed"] is False
    assert result["safety"]["ground_truth_read"] is True


def test_evaluate_rejects_ambiguous_suffixes(tmp_path: Path):
    receipt, labels = _inputs(tmp_path)
    lines = receipt.read_text(encoding="utf-8").splitlines()
    duplicate = json.loads(lines[-1])
    duplicate["path"] = "/other/sample_pack_testing/Pack/a.wav"
    lines.append(json.dumps(duplicate))
    receipt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        MODULE.evaluate(receipt, labels, tmp_path / "out.json")
    except ValueError as exc:
        assert "ambiguous receipt suffix" in str(exc)
    else:
        raise AssertionError("ambiguous suffix was accepted")


def test_evaluate_excludes_conflicting_label_duplicates(tmp_path: Path):
    receipt, labels = _inputs(tmp_path)
    with labels.open("a", encoding="utf-8", newline="") as handle:
        handle.write("/other/sample_pack_testing/Pack/a.wav,Snare\n")
    result = MODULE.evaluate(receipt, labels, tmp_path / "out.json")
    assert result["n_ambiguous_label_keys"] == 1
    assert result["n_evaluated"] == 1
