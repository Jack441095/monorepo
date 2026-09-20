"""Fail-closed provenance gate for an external SLO classifier artifact.

KENN does not load SLO training code or checkpoints.  This module binds an
already-evaluated external artifact to KENN's advisory-only classifier
contract, and rejects mismatched or under-evidenced handoffs.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping


MANIFEST_SCHEMA = "kenn.slo_artifact_manifest.v1"
RECEIPT_SCHEMA = "kenn.slo_artifact_intake_receipt.v1"
ADAPTER_SCHEMA = "kenn.audio_classification.v1"
EVALUATION_SCHEMA = "kenn.slo_adapter_evaluation.v1"
_HEX = frozenset("0123456789abcdef")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _sha(value: Any, field: str, errors: list[str]) -> str:
    text = str(value or "").lower().removeprefix("sha256:")
    if len(text) != 64 or any(char not in _HEX for char in text):
        errors.append(f"{field} must be a SHA-256 digest")
        return ""
    return "sha256:" + text


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def validate_intake(
    manifest: Mapping[str, Any], *, model_sha256: str, label_map_sha256: str,
    preprocessing_sha256: str, calibration_sha256: str, evaluation: Mapping[str, Any],
    evaluation_sha256: str,
) -> dict[str, Any]:
    """Return a sanitised receipt; invalid input is never advisory-ready.

    The evaluation digest is a required input rather than a post-validation
    convenience so callers cannot accidentally validate one parsed receipt
    while reporting provenance for another file.
    """
    errors: list[str] = []
    if not isinstance(manifest, Mapping):
        return {"schema": RECEIPT_SCHEMA, "status": "invalid", "advisory_eligible": False, "errors": ["manifest must be an object"]}
    if manifest.get("schema") != MANIFEST_SCHEMA:
        errors.append("unexpected manifest schema")
    if manifest.get("contract_schema") != ADAPTER_SCHEMA:
        errors.append("manifest must target kenn.audio_classification.v1")
    model_id = str(manifest.get("model_id") or "").strip()
    inference_version = str(manifest.get("inference_version") or "").strip()
    if not model_id or len(model_id) > 128:
        errors.append("model_id must be non-empty and bounded")
    if not inference_version or len(inference_version) > 128:
        errors.append("inference_version must be non-empty and bounded")
    model = manifest.get("model") if isinstance(manifest.get("model"), Mapping) else {}
    label_map = manifest.get("label_map") if isinstance(manifest.get("label_map"), Mapping) else {}
    preprocessing = manifest.get("preprocessing") if isinstance(manifest.get("preprocessing"), Mapping) else {}
    calibration = manifest.get("calibration") if isinstance(manifest.get("calibration"), Mapping) else {}
    evaluation_receipt = manifest.get("evaluation_receipt") if isinstance(manifest.get("evaluation_receipt"), Mapping) else {}
    declared_model_sha = _sha(model.get("sha256"), "model.sha256", errors)
    declared_label_sha = _sha(label_map.get("sha256"), "label_map.sha256", errors)
    declared_preprocessing_sha = _sha(preprocessing.get("sha256"), "preprocessing.sha256", errors)
    declared_calibration_sha = _sha(calibration.get("sha256"), "calibration.sha256", errors)
    declared_evaluation_sha = _sha(evaluation_receipt.get("sha256"), "evaluation_receipt.sha256", errors)
    actual_model_sha = _sha(model_sha256, "actual model_sha256", errors)
    actual_label_sha = _sha(label_map_sha256, "actual label_map_sha256", errors)
    actual_preprocessing_sha = _sha(preprocessing_sha256, "actual preprocessing_sha256", errors)
    actual_calibration_sha = _sha(calibration_sha256, "actual calibration_sha256", errors)
    actual_evaluation_sha = _sha(evaluation_sha256, "actual evaluation_sha256", errors)
    if declared_model_sha and actual_model_sha and declared_model_sha != actual_model_sha:
        errors.append("model hash does not match the manifest")
    if declared_label_sha and actual_label_sha and declared_label_sha != actual_label_sha:
        errors.append("label-map hash does not match the manifest")
    if declared_preprocessing_sha and actual_preprocessing_sha and declared_preprocessing_sha != actual_preprocessing_sha:
        errors.append("preprocessing hash does not match the manifest")
    if declared_calibration_sha and actual_calibration_sha and declared_calibration_sha != actual_calibration_sha:
        errors.append("calibration hash does not match the manifest")
    if declared_evaluation_sha and actual_evaluation_sha and declared_evaluation_sha != actual_evaluation_sha:
        errors.append("evaluation-report hash does not match the manifest")

    if not isinstance(evaluation, Mapping) or evaluation.get("schema") != EVALUATION_SCHEMA:
        errors.append("evaluation receipt has an unexpected schema")
    elif evaluation.get("status") != "evaluated":
        errors.append("evaluation receipt is not evaluated")
    else:
        identity = evaluation.get("artifact_identity") if isinstance(evaluation.get("artifact_identity"), Mapping) else {}
        expected_identity = {
            "model_id": model_id, "model_sha256": declared_model_sha,
            "label_map_sha256": declared_label_sha, "inference_version": inference_version,
        }
        if any(identity.get(key) != value for key, value in expected_identity.items()):
            errors.append("evaluation artifact identity does not match the manifest")
        if int(evaluation.get("case_count") or 0) < 100 or int(evaluation.get("project_bucket_count") or 0) < 3:
            errors.append("evaluation needs at least 100 cases across 3 project buckets")
        audio = evaluation.get("audio_only") if isinstance(evaluation.get("audio_only"), Mapping) else {}
        accuracy, macro_f1 = _number(audio.get("accuracy")), _number(audio.get("macro_f1"))
        if accuracy is None or accuracy < 0.85:
            errors.append("audio-only accuracy is below the 0.85 advisory threshold")
        if macro_f1 is None or macro_f1 < 0.85:
            errors.append("audio-only macro F1 is below the 0.85 advisory threshold")
        per_class = audio.get("per_class")
        if not isinstance(per_class, Mapping) or not per_class:
            errors.append("evaluation needs audio-only per-class metrics")
        calibration_metrics = evaluation.get("calibration") if isinstance(evaluation.get("calibration"), Mapping) else {}
        audio_ece = _number(calibration_metrics.get("audio_only_ece"))
        if audio_ece is None or audio_ece > 0.15:
            errors.append("audio-only calibration ECE is missing or exceeds 0.15")
        ood_evaluation = evaluation.get("ood_evaluation") if isinstance(evaluation.get("ood_evaluation"), Mapping) else {}
        for expected_status in ("unknown", "out_of_distribution"):
            item = ood_evaluation.get(expected_status) if isinstance(ood_evaluation.get(expected_status), Mapping) else {}
            case_count = int(item.get("case_count") or 0)
            rejection_rate = _number(item.get("correct_rejection_rate"))
            if case_count < 5 or rejection_rate is None or rejection_rate < 0.9:
                errors.append(f"evaluation needs 5+ {expected_status} cases with correct rejection rate >= 0.9")
        latency = evaluation.get("latency_ms") if isinstance(evaluation.get("latency_ms"), Mapping) else {}
        p95 = _number(latency.get("p95"))
        if p95 is None or p95 > 1000:
            errors.append("evaluation latency p95 is missing or exceeds 1000 ms")
        if evaluation.get("errors"):
            errors.append("evaluation receipt contains validation errors")

    requested = manifest.get("allow_advisory_integration") is True
    eligible = not errors and requested
    return {
        "schema": RECEIPT_SCHEMA,
        "status": "ready" if eligible else "invalid",
        "advisory_eligible": eligible,
        "activation": "manual_registration_required",
        "artifact_identity": {
            "model_id": model_id, "model_sha256": declared_model_sha,
            "label_map_sha256": declared_label_sha, "inference_version": inference_version,
        },
        "preprocessing_sha256": declared_preprocessing_sha,
        "calibration_sha256": declared_calibration_sha,
        "evaluation_report_sha256": declared_evaluation_sha,
        "errors": errors,
        "limitations": [
            "This validates provenance and evaluation evidence only; it does not load a model or classify audio.",
            "A ready receipt grants advisory-registration eligibility only, never Live mutation authority.",
        ],
    }
