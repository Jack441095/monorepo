from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[5] / "tooling" / "scripts" / "evaluate_slo_adapter.py"
spec = importlib.util.spec_from_file_location("evaluate_slo_adapter", SCRIPT)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def _classification(label: str, *, ood: str = "in_distribution") -> dict:
    digest = "sha256:" + "a" * 64
    selected = label if ood == "in_distribution" else "Unknown"
    source = "audio_only" if ood == "in_distribution" else "unknown"
    return {
        "schema": "kenn.audio_classification.v1", "audio_sha256": digest,
        "model_id": "slo-v1", "model_sha256": "sha256:" + "b" * 64,
        "label_map_sha256": "sha256:" + "c" * 64, "inference_version": "1",
        "audio_only": [{"label": label, "probability": 0.9}],
        "metadata_assisted": [{"label": label, "probability": 0.9}],
        "selected_label": selected, "selected_source": source, "confidence_band": "high",
        "out_of_distribution": {"status": ood, "score": 0.1},
        "evidence_used": ["audio_only"], "latency_ms": 5, "limitations": ["advisory only"],
    }


def test_slo_adapter_evaluation_separates_audio_only_and_metadata_results() -> None:
    report = module.evaluate_rows([
        {"case_id": "a", "project_bucket": "p1", "expected_label": "kick", "expected_ood_status": "in_distribution", "classification": _classification("kick")},
        {"case_id": "b", "project_bucket": "p2", "expected_label": "snare", "expected_ood_status": "in_distribution", "classification": _classification("kick")},
    ])

    assert report["status"] == "evaluated"
    assert report["audio_only"]["accuracy"] == 0.5
    assert report["audio_only"]["per_class"]["kick"]["recall"] == 1.0
    assert report["project_bucket_count"] == 2
    assert report["artifact_identity"]["model_id"] == "slo-v1"
    assert report["selective_prediction"] == {"accepted_case_count": 2, "abstained_case_count": 0, "accuracy": 0.5}
    assert report["latency_ms"] == {"mean": 5.0, "p95": 5.0}
    assert report["promotion_eligible"] is False


def test_slo_adapter_evaluation_rejects_malformed_cases() -> None:
    report = module.evaluate_rows([{"case_id": "", "expected_label": "kick", "expected_ood_status": "in_distribution"}])
    assert report["status"] == "invalid"
    assert "project_bucket" in report["errors"][0]


def test_slo_adapter_evaluation_rejects_mixed_artifact_identities() -> None:
    second = _classification("snare")
    second["model_sha256"] = "sha256:" + "d" * 64
    report = module.evaluate_rows([
        {"case_id": "a", "project_bucket": "p1", "expected_label": "kick", "expected_ood_status": "in_distribution", "classification": _classification("kick")},
        {"case_id": "b", "project_bucket": "p2", "expected_label": "snare", "expected_ood_status": "in_distribution", "classification": second},
    ])

    assert report["status"] == "invalid"
    assert report["artifact_identity"] is None
    assert "more than one model" in report["errors"][-1]


def test_slo_adapter_evaluation_measures_unknown_and_ood_rejection() -> None:
    unknown = _classification("kick", ood="unknown")
    out_of_distribution = _classification("snare", ood="out_of_distribution")
    report = module.evaluate_rows([
        {"case_id": "unknown", "project_bucket": "p1", "expected_ood_status": "unknown", "classification": unknown},
        {"case_id": "ood", "project_bucket": "p2", "expected_ood_status": "out_of_distribution", "classification": out_of_distribution},
    ])

    assert report["status"] == "evaluated"
    assert report["audio_only"] == {"accuracy": None, "macro_f1": None, "per_class": {}}
    assert report["ood_evaluation"] == {
        "unknown": {"case_count": 1, "correct_rejection_count": 1, "correct_rejection_rate": 1.0},
        "out_of_distribution": {"case_count": 1, "correct_rejection_count": 1, "correct_rejection_rate": 1.0},
    }
