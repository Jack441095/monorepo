import json
import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("audit_taxonomy_readiness.py")
SPEC = importlib.util.spec_from_file_location("audit_taxonomy_readiness", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_future_labels_never_become_current_production_classes():
    assert MODULE.classify_candidate_label("Bird") == "future_animal"
    assert MODULE.classify_candidate_label("Weather/Nature Atmos") == "current_music_sample"
    assert MODULE.classify_candidate_label("Engine") == "future_mechanical"
    assert MODULE.classify_candidate_label("Kick") == "current_music_sample"


def test_report_is_read_only_and_keeps_unmapped_visible(tmp_path):
    predictions = tmp_path / "predictions.jsonl"
    predictions.write_text(
        json.dumps({"record_type": "slo_full_taxonomy_candidate_predictions"}) + "\n"
        + json.dumps({"full_taxonomy_class": "Kick"}) + "\n"
        + json.dumps({"full_taxonomy_class": "Bird"}) + "\n"
        + json.dumps({"full_taxonomy_class": "Unknown Future Thing"}) + "\n",
        encoding="utf-8",
    )
    taxonomy = tmp_path / "taxonomy.json"
    taxonomy.write_text(json.dumps({"status": "dormant_reference_only"}), encoding="utf-8")
    report = MODULE.build_report(predictions, taxonomy)
    assert report["safety"]["read_only"] is True
    assert report["safety"]["production_taxonomy_changed"] is False
    assert report["summary"]["domain_counts"]["current_music_sample"] == 1
    assert "Unknown Future Thing" in report["summary"]["unmapped_labels"]
