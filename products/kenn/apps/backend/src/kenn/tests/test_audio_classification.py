from __future__ import annotations

import pytest

from kenn.core.audio_classification import AudioClassificationAdapter, AudioClassificationError, SCHEMA, normalize


def _sha(seed: str) -> str:
    return "sha256:" + (seed * 64)[:64]


def _payload() -> dict:
    return {
        "schema": SCHEMA, "audio_sha256": _sha("a"), "model_id": "slo-export-v1",
        "model_sha256": _sha("b"), "label_map_sha256": _sha("c"), "inference_version": "1",
        "audio_only": [{"label": "kick", "probability": 0.91}],
        "metadata_assisted": [{"label": "kick", "probability": 0.94}],
        "selected_label": "kick", "selected_source": "audio_only", "confidence_band": "high",
        "out_of_distribution": {"status": "in_distribution", "score": 0.04},
        "evidence_used": ["audio_only", "metadata_assisted"], "latency_ms": 12,
        "limitations": ["advisory only"],
    }


def test_adapter_is_disabled_by_default_without_calling_backend() -> None:
    def backend(_digest: str) -> dict:
        raise AssertionError("disabled adapter must not call a backend")
    result = AudioClassificationAdapter(backend).classify(_sha("a"))
    assert result == {"schema": SCHEMA, "status": "disabled", "audio_sha256": _sha("a"), "advisory_only": True, "live_mutation_authorized": False}


def test_completed_result_preserves_evidence_streams_and_is_never_action_authority() -> None:
    result = AudioClassificationAdapter(lambda _digest: _payload(), enabled=True).classify(_sha("a"))
    assert result["status"] == "completed"
    assert result["audio_only"] == [{"label": "kick", "probability": 0.91}]
    assert result["metadata_assisted"] == [{"label": "kick", "probability": 0.94}]
    assert result["advisory_only"] is True and result["live_mutation_authorized"] is False


def test_ood_and_metadata_conflicts_cannot_silently_force_a_label() -> None:
    payload = _payload()
    payload["out_of_distribution"] = {"status": "out_of_distribution", "score": 0.99}
    with pytest.raises(AudioClassificationError, match="must not force"):
        normalize(payload)
    payload["selected_source"] = "unknown"; payload["selected_label"] = "Unknown"
    result = normalize(payload)
    assert result["selected_source"] == "unknown"
