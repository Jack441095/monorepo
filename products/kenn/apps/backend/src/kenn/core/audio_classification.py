"""Read-only, model-neutral boundary for optional audio classification.

KENN deliberately does not import an SLO checkpoint or training code.  When a
separately qualified classifier is available, its backend may supply the
versioned payload validated here.  The adapter is disabled by default and its
output is advisory context only; it has no connection to the Live mutation
boundary.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any


SCHEMA = "kenn.audio_classification.v1"
_HEX64 = frozenset("0123456789abcdef")
_BANDS = frozenset({"low", "medium", "high"})
_OOD_STATUS = frozenset({"in_distribution", "unknown", "out_of_distribution"})


class AudioClassificationError(ValueError):
    """Raised for malformed or unsafe classifier output."""


def _sha(value: Any, field: str) -> str:
    text = str(value or "").lower().removeprefix("sha256:")
    if len(text) != 64 or any(char not in _HEX64 for char in text):
        raise AudioClassificationError(f"{field} must be a SHA-256 digest")
    return "sha256:" + text


def _text(value: Any, field: str, *, limit: int = 128) -> str:
    result = str(value or "").strip()
    if not result or len(result) > limit:
        raise AudioClassificationError(f"{field} must be non-empty and bounded")
    return result


def _predictions(value: Any, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value or len(value) > 8:
        raise AudioClassificationError(f"{field} must contain 1–8 predictions")
    result: list[dict[str, Any]] = []
    labels: set[str] = set()
    previous = 1.1
    for item in value:
        if not isinstance(item, Mapping):
            raise AudioClassificationError(f"{field} prediction must be an object")
        label = _text(item.get("label"), f"{field}.label", limit=96)
        probability = item.get("probability")
        if isinstance(probability, bool) or not isinstance(probability, (int, float)) or not 0.0 <= float(probability) <= 1.0:
            raise AudioClassificationError(f"{field}.probability must be in [0, 1]")
        if label in labels or float(probability) > previous:
            raise AudioClassificationError(f"{field} must have unique labels in descending probability order")
        labels.add(label); previous = float(probability)
        result.append({"label": label, "probability": float(probability)})
    return result


def normalize(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and bound a classification observation for planner context."""
    if not isinstance(payload, Mapping) or payload.get("schema") != SCHEMA:
        raise AudioClassificationError("unexpected classification schema")
    audio_only = _predictions(payload.get("audio_only"), "audio_only")
    metadata_assisted = _predictions(payload.get("metadata_assisted"), "metadata_assisted")
    selected_label = _text(payload.get("selected_label"), "selected_label", limit=96)
    selected_source = payload.get("selected_source")
    if selected_source not in {"audio_only", "metadata_assisted", "unknown"}:
        raise AudioClassificationError("selected_source is invalid")
    if selected_source == "audio_only" and selected_label not in {item["label"] for item in audio_only}:
        raise AudioClassificationError("selected audio-only label is absent from audio-only predictions")
    if selected_source == "metadata_assisted" and selected_label not in {item["label"] for item in metadata_assisted}:
        raise AudioClassificationError("selected metadata-assisted label is absent from metadata-assisted predictions")
    ood = payload.get("out_of_distribution")
    if not isinstance(ood, Mapping) or ood.get("status") not in _OOD_STATUS:
        raise AudioClassificationError("out_of_distribution status is invalid")
    score = ood.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0.0 <= float(score) <= 1.0:
        raise AudioClassificationError("out_of_distribution score must be in [0, 1]")
    if ood["status"] != "in_distribution" and selected_source != "unknown":
        raise AudioClassificationError("Unknown/OOD output must not force a class")
    if selected_source == "unknown" and selected_label.lower() != "unknown":
        raise AudioClassificationError("unknown selection must use the Unknown label")
    band = payload.get("confidence_band")
    if band not in _BANDS:
        raise AudioClassificationError("confidence_band is invalid")
    latency = payload.get("latency_ms")
    if isinstance(latency, bool) or not isinstance(latency, (int, float)) or float(latency) < 0:
        raise AudioClassificationError("latency_ms must be non-negative")
    evidence = payload.get("evidence_used")
    limitations = payload.get("limitations")
    if not isinstance(evidence, list) or not evidence or any(not isinstance(item, str) or not item.strip() or len(item) > 96 for item in evidence):
        raise AudioClassificationError("evidence_used must be a bounded non-empty string list")
    if not isinstance(limitations, list) or any(not isinstance(item, str) or not item.strip() or len(item) > 256 for item in limitations):
        raise AudioClassificationError("limitations must be a bounded string list")
    return {
        "schema": SCHEMA,
        "audio_sha256": _sha(payload.get("audio_sha256"), "audio_sha256"),
        "model_id": _text(payload.get("model_id"), "model_id"),
        "model_sha256": _sha(payload.get("model_sha256"), "model_sha256"),
        "label_map_sha256": _sha(payload.get("label_map_sha256"), "label_map_sha256"),
        "inference_version": _text(payload.get("inference_version"), "inference_version"),
        "audio_only": audio_only,
        "metadata_assisted": metadata_assisted,
        "selected_label": selected_label,
        "selected_source": selected_source,
        "confidence_band": band,
        "out_of_distribution": {"status": str(ood["status"]), "score": float(score)},
        "evidence_used": list(evidence),
        "latency_ms": float(latency),
        "limitations": list(limitations),
        "advisory_only": True,
        "live_mutation_authorized": False,
    }


class AudioClassificationAdapter:
    """Disabled-by-default adapter for a separately qualified backend."""

    def __init__(self, backend: Callable[[str], Mapping[str, Any]] | None = None, *, enabled: bool = False) -> None:
        self._backend = backend
        self._enabled = bool(enabled)

    def classify(self, audio_sha256: str) -> dict[str, Any]:
        digest = _sha(audio_sha256, "audio_sha256")
        if not self._enabled:
            return {"schema": SCHEMA, "status": "disabled", "audio_sha256": digest, "advisory_only": True, "live_mutation_authorized": False}
        if self._backend is None:
            return {"schema": SCHEMA, "status": "unavailable", "audio_sha256": digest, "advisory_only": True, "live_mutation_authorized": False}
        result = normalize(self._backend(digest))
        if result["audio_sha256"] != digest:
            raise AudioClassificationError("backend result does not match requested audio")
        return {"status": "completed", **result}
