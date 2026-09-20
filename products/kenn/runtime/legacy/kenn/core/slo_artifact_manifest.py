"""Read-only validation for a separately trained SLO export.

KENN must not import training code or enable a classifier just because a model
file exists.  This validator verifies an exported artifact's immutable
manifest and hashes before a later, explicit advisory-only integration step.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA = "kenn.slo_artifact_manifest.v1"
CONTRACT_SCHEMA = "kenn.audio_classification.v1"
_HEX = frozenset("0123456789abcdef")
_FORMATS = frozenset({"onnx", "torchscript", "safetensors"})


class SLOArtifactManifestError(ValueError):
    """An export lacks the evidence KENN requires to consider it."""


def _sha(value: Any, field: str) -> str:
    result = str(value or "").strip().lower().removeprefix("sha256:")
    if len(result) != 64 or any(char not in _HEX for char in result):
        raise SLOArtifactManifestError(f"{field} must be a SHA-256 digest.")
    return "sha256:" + result


def _text(value: Any, field: str, *, limit: int = 256) -> str:
    result = str(value or "").strip()
    if not result or len(result) > limit:
        raise SLOArtifactManifestError(f"{field} must be a non-empty bounded string.")
    return result


def _fraction(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 <= float(value) <= 1.0:
        raise SLOArtifactManifestError(f"{field} must be a number in [0, 1].")
    return float(value)


def _artifact(value: Any, field: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise SLOArtifactManifestError(f"{field} must be an object.")
    return {
        "path": _text(value.get("path"), f"{field}.path", limit=1_024),
        "sha256": _sha(value.get("sha256"), f"{field}.sha256"),
    }


def validate_manifest(payload: Any) -> dict[str, Any]:
    """Validate the portable manifest structure without reading any artifact."""
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        raise SLOArtifactManifestError(f"Expected {SCHEMA}.")
    contract_schema = _text(payload.get("contract_schema"), "contract_schema", limit=128)
    if contract_schema != CONTRACT_SCHEMA:
        raise SLOArtifactManifestError(f"contract_schema must be {CONTRACT_SCHEMA}.")
    model = _artifact(payload.get("model"), "model")
    model_format = _text((payload.get("model") or {}).get("format"), "model.format", limit=32).lower()
    if model_format not in _FORMATS:
        raise SLOArtifactManifestError("model.format must be one of: onnx, torchscript, safetensors.")
    evaluation = payload.get("evaluation")
    if not isinstance(evaluation, dict):
        raise SLOArtifactManifestError("evaluation must be an object.")
    audio_only = evaluation.get("audio_only")
    if not isinstance(audio_only, dict):
        raise SLOArtifactManifestError("evaluation.audio_only must be an object.")
    result = {
        "schema": SCHEMA,
        "contract_schema": contract_schema,
        "model_id": _text(payload.get("model_id"), "model_id", limit=128),
        "inference_version": _text(payload.get("inference_version"), "inference_version", limit=128),
        "model": {**model, "format": model_format},
        "label_map": _artifact(payload.get("label_map"), "label_map"),
        "preprocessing": _artifact(payload.get("preprocessing"), "preprocessing"),
        "evaluation_receipt": _artifact(payload.get("evaluation_receipt"), "evaluation_receipt"),
        "evaluation": {
            "split_strategy": _text(evaluation.get("split_strategy"), "evaluation.split_strategy", limit=256),
            "audio_only": {
                "accuracy": _fraction(audio_only.get("accuracy"), "evaluation.audio_only.accuracy"),
                "macro_f1": _fraction(audio_only.get("macro_f1"), "evaluation.audio_only.macro_f1"),
            },
        },
        "calibration": _artifact(payload.get("calibration"), "calibration"),
        "limitations": [
            _text(item, "limitations item", limit=256)
            for item in (payload.get("limitations") or [])[:16]
            if isinstance(item, str) and item.strip()
        ],
        "advisory_only": True,
        "live_mutation_authorized": False,
    }
    if not result["limitations"]:
        raise SLOArtifactManifestError("limitations must contain at least one explicit limitation.")
    return result


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def verify_artifact_files(manifest: dict[str, Any], *, manifest_directory: Path) -> dict[str, Any]:
    """Hash listed local files. This reads artifacts but never imports them."""
    rows = []
    for field in ("model", "label_map", "preprocessing", "evaluation_receipt", "calibration"):
        item = manifest[field]
        path = Path(item["path"])
        if not path.is_absolute():
            path = manifest_directory / path
        resolved = path.resolve()
        row = {"field": field, "path": str(resolved), "exists": resolved.is_file(), "sha256_matches": False}
        if resolved.is_file():
            row["sha256_matches"] = _file_sha256(resolved) == item["sha256"]
        rows.append(row)
    return {"files": rows, "all_files_verified": all(row["exists"] and row["sha256_matches"] for row in rows)}


def inspect_manifest_file(path: Path | str, *, verify_files: bool = True) -> dict[str, Any]:
    manifest_path = Path(path).expanduser().resolve()
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = validate_manifest(raw)
        verification = verify_artifact_files(manifest, manifest_directory=manifest_path.parent) if verify_files else {
            "files": [], "all_files_verified": None,
        }
        return {
            "schema": "kenn.slo_artifact_inspection.v1",
            "status": "verified" if verification["all_files_verified"] else "manifest_valid_files_unverified",
            "manifest": manifest,
            **verification,
            "promotion_eligible": False,
            "next_step": "Run KENN's fixed classification and latency evaluation, then enable only through an explicit advisory-only feature flag.",
        }
    except (OSError, ValueError, SLOArtifactManifestError) as exc:
        return {
            "schema": "kenn.slo_artifact_inspection.v1",
            "status": "invalid",
            "error": str(exc),
            "promotion_eligible": False,
        }


__all__ = [
    "CONTRACT_SCHEMA",
    "SCHEMA",
    "SLOArtifactManifestError",
    "inspect_manifest_file",
    "validate_manifest",
    "verify_artifact_files",
]
