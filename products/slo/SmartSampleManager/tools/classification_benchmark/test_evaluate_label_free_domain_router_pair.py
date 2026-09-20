from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("evaluate_label_free_domain_router_pair.py")
SPEC = importlib.util.spec_from_file_location("evaluate_label_free_domain_router_pair", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _receipt(path: Path, rows: list[dict[str, object]], source: str) -> None:
    header = {"record_type": "slo_label_free_domain_router_receipt",
              "schema_version": "1.0.0", "prompt_bank_source": source}
    path.write_text("\n".join(json.dumps(row) for row in [header, *rows]) + "\n", encoding="utf-8")


def test_pair_evaluation_counts_expected_domain_and_changes(tmp_path: Path):
    labels = tmp_path / "labels.csv"
    with labels.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["label", "path"])
        writer.writeheader()
        writer.writerow({"label": "Kick", "path": "/x/sample_pack_testing/a.wav"})
        writer.writerow({"label": "Snare", "path": "/x/sample_pack_testing/b.wav"})
    baseline = tmp_path / "v1.jsonl"
    candidate = tmp_path / "v2.jsonl"
    _receipt(baseline, [
        {"path": "/remote/sample_pack_testing/a.wav", "domain_suggestion": "music_sample", "status": "suggest"},
        {"path": "/remote/sample_pack_testing/b.wav", "domain_suggestion": "environment_sfx", "status": "review"},
    ], "built_in_v1")
    _receipt(candidate, [
        {"path": "/stage/sample_pack_testing/a.wav", "domain_suggestion": "environment_sfx", "status": "review"},
        {"path": "/stage/sample_pack_testing/b.wav", "domain_suggestion": "music_sample", "status": "suggest"},
    ], "v2")
    out = tmp_path / "out.json"
    result = MODULE.evaluate(labels, baseline, candidate, out)
    assert result["n_paired_files"] == 2
    assert result["baseline"]["expected_domain_count"] == 1
    assert result["candidate"]["expected_domain_count"] == 1
    assert result["paired"]["candidate_improved_count"] == 1
    assert result["paired"]["candidate_worsened_count"] == 1
    assert result["safety"]["read_only"] is True
