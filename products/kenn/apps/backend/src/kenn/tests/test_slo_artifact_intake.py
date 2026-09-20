from __future__ import annotations

from kenn.core.slo_artifact_intake import ADAPTER_SCHEMA, EVALUATION_SCHEMA, MANIFEST_SCHEMA, validate_intake


def _sha(character: str) -> str:
    return "sha256:" + character * 64


def _manifest() -> dict:
    return {
        "schema": MANIFEST_SCHEMA, "contract_schema": ADAPTER_SCHEMA,
        "model_id": "slo-v3", "inference_version": "runner-v1",
        "model": {"sha256": _sha("a")}, "label_map": {"sha256": _sha("b")},
        "preprocessing": {"sha256": _sha("d")}, "calibration": {"sha256": _sha("e")},
        "evaluation_receipt": {"sha256": _sha("c")},
        "allow_advisory_integration": True,
    }


def _evaluation() -> dict:
    return {
        "schema": EVALUATION_SCHEMA, "status": "evaluated", "case_count": 120, "project_bucket_count": 3,
        "artifact_identity": {"model_id": "slo-v3", "model_sha256": _sha("a"), "label_map_sha256": _sha("b"), "inference_version": "runner-v1"},
        "audio_only": {"accuracy": 0.886, "macro_f1": 0.893, "per_class": {"kick": {"support": 40, "precision": 0.9, "recall": 0.9, "f1": 0.9}}},
        "calibration": {"audio_only_ece": 0.04, "bin_count": 10},
        "ood_evaluation": {
            "unknown": {"case_count": 5, "correct_rejection_count": 5, "correct_rejection_rate": 1.0},
            "out_of_distribution": {"case_count": 5, "correct_rejection_count": 5, "correct_rejection_rate": 1.0},
        },
        "latency_ms": {"p95": 41.0}, "errors": [],
    }


def test_intake_requires_matching_artifact_identity_and_evidence() -> None:
    result = validate_intake(_manifest(), model_sha256=_sha("a"), label_map_sha256=_sha("b"), preprocessing_sha256=_sha("d"), calibration_sha256=_sha("e"), evaluation=_evaluation(), evaluation_sha256=_sha("c"))

    assert result["status"] == "ready"
    assert result["advisory_eligible"] is True
    assert result["activation"] == "manual_registration_required"


def test_intake_fails_closed_for_model_hash_mismatch() -> None:
    result = validate_intake(_manifest(), model_sha256=_sha("f"), label_map_sha256=_sha("b"), preprocessing_sha256=_sha("d"), calibration_sha256=_sha("e"), evaluation=_evaluation(), evaluation_sha256=_sha("c"))

    assert result["status"] == "invalid"
    assert result["advisory_eligible"] is False
    assert "model hash does not match the manifest" in result["errors"]


def test_intake_requires_calibrated_unknown_and_ood_rejection_evidence() -> None:
    evaluation = _evaluation()
    evaluation["ood_evaluation"]["unknown"]["correct_rejection_rate"] = 0.8
    evaluation["calibration"]["audio_only_ece"] = 0.2
    result = validate_intake(_manifest(), model_sha256=_sha("a"), label_map_sha256=_sha("b"), preprocessing_sha256=_sha("d"), calibration_sha256=_sha("e"), evaluation=evaluation, evaluation_sha256=_sha("c"))

    assert result["advisory_eligible"] is False
    assert "audio-only calibration ECE is missing or exceeds 0.15" in result["errors"]
    assert "evaluation needs 5+ unknown cases with correct rejection rate >= 0.9" in result["errors"]


def test_intake_rejects_evaluation_receipt_hash_mismatch() -> None:
    result = validate_intake(
        _manifest(), model_sha256=_sha("a"), label_map_sha256=_sha("b"),
        preprocessing_sha256=_sha("d"), calibration_sha256=_sha("e"),
        evaluation=_evaluation(), evaluation_sha256=_sha("f"),
    )

    assert result["advisory_eligible"] is False
    assert "evaluation-report hash does not match the manifest" in result["errors"]
