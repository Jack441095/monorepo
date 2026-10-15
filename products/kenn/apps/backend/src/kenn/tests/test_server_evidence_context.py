from __future__ import annotations

import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def _masking_result() -> dict:
    return {
        "schema": "kenn.mix_review_masking_analysis.v1",
        "ok": True,
        "stems": ["01_Kick", "08_Bass"],
        "activity": {
            "schema": "kenn.stem_masking.activity.v1",
            "active_floor_dbfs": -50,
            "frame_count": 100,
            "sources": [
                {"name": "01_Kick", "active_frame_count": 60},
                {"name": "08_Bass", "active_frame_count": 60},
            ],
            "pairs": [{"stems": ["01_Kick", "08_Bass"], "simultaneously_active_frame_count": 50}],
        },
        "findings": [{
            "fault_family": "masking",
            "detected": True,
            "stems": ["01_Kick", "08_Bass"],
            "band": "bass",
            "evidence": {
                "competing_frame_fraction": 0.454,
                "active_floor_dbfs": -50,
                "competing_within_db": 6,
            },
        }],
        "evidence": {
            "schema": "kenn.evidence.v1",
            "source": "stem_masking_analysis",
            "captured_at_age_seconds": None,
            "facts": [{
                "name": "masking_highest_competing_frame_fraction",
                "value": 0.454,
                "unit": "ratio",
                "source": "stem_masking_analysis",
                "confidence": "measured_proxy",
            }],
            "limitations": ["Not a perceptual masking model."],
        },
    }


def test_stem_masking_result_can_be_reused_as_typed_chat_evidence() -> None:
    from kenn.server import _attach_stem_masking_evidence, _stem_masking_context_turn

    context = _masking_result()
    turn = _stem_masking_context_turn(context)
    assert turn is not None
    assert turn["role"] == "user"
    assert turn["content"].startswith("KENN_EVIDENCE_PACKET_V1:")
    encoded = json.loads(turn["content"].split(":", 1)[1])
    assert encoded["source"] == "stem_masking_analysis"
    encoded_facts = {fact["name"]: fact["value"] for fact in encoded["facts"]}
    assert encoded_facts["masking_highest_competing_frame_fraction"] == 0.454
    assert encoded_facts["masking_highest_pair"] == "01_Kick + 08_Bass"

    response: dict = {}
    _attach_stem_masking_evidence(response, context)
    assert response["stem_masking_evidence"]["schema"] == "kenn.evidence.v1"
    assert response["stem_masking_evidence"]["source"] == "stem_masking_analysis"
    response_facts = {fact["name"]: fact["value"] for fact in response["stem_masking_evidence"]["facts"]}
    assert response_facts["masking_highest_pair"] == "01_Kick + 08_Bass"


def test_invalid_stem_masking_context_is_not_admitted() -> None:
    from kenn.server import _attach_stem_masking_evidence, _stem_masking_context_turn

    invalid = {"schema": "kenn.mix_review_masking_analysis.v1", "ok": True, "evidence": {}}
    assert _stem_masking_context_turn(invalid) is None
    response: dict = {}
    _attach_stem_masking_evidence(response, invalid)
    assert response == {}


def test_forged_stem_masking_source_or_limitations_are_not_admitted() -> None:
    from kenn.server import _stem_masking_context_turn

    wrong_source = _masking_result()
    wrong_source["evidence"]["source"] = "plugin_bus_snapshot"
    assert _stem_masking_context_turn(wrong_source) is None

    wrong_limitations = _masking_result()
    wrong_limitations["evidence"]["limitations"] = "not-a-list"
    assert _stem_masking_context_turn(wrong_limitations) is None


def test_quiet_stem_masking_receipt_cannot_reuse_cached_scalar_findings() -> None:
    from kenn.server import _attach_stem_masking_evidence, _stem_masking_context_turn

    # A stale cached fraction cannot override a receipt whose measured pair is silent.
    quiet = _masking_result()
    quiet["activity"]["sources"] = [
        {"name": "01_Kick", "active_frame_count": 0},
        {"name": "08_Bass", "active_frame_count": 0},
    ]
    quiet["activity"]["pairs"][0]["simultaneously_active_frame_count"] = 0
    quiet["evidence"]["facts"].append({
        "name": "masking_highest_competing_frame_fraction",
        "value": 0.454,
        "unit": "ratio",
        "source": "stem_masking_analysis",
        "confidence": "measured_proxy",
    })

    turn = _stem_masking_context_turn(quiet)
    assert turn is not None
    packet = json.loads(turn["content"].split(":", 1)[1])
    assert not any(fact["name"].startswith("masking_") for fact in packet["facts"])
    assert any("measurements and recommendations are withheld" in item for item in packet["limitations"])
    response: dict = {}
    _attach_stem_masking_evidence(response, quiet)
    published = response["stem_masking_evidence"]
    assert not any(fact["name"].startswith("masking_") for fact in published["facts"])


def test_audio_classification_result_can_be_reused_as_typed_chat_evidence() -> None:
    from kenn.server import _audio_classification_context_turn, _attach_audio_classification_evidence

    context = {
        "schema": "kenn.audio_classification.v1",
        "status": "completed",
        "audio_sha256": "sha256:" + "a" * 64,
        "model_id": "slo-export-v1",
        "model_sha256": "sha256:" + "b" * 64,
        "label_map_sha256": "sha256:" + "c" * 64,
        "inference_version": "1",
        "audio_only": [{"label": "kick", "probability": 0.9}],
        "metadata_assisted": [{"label": "kick", "probability": 0.95}],
        "selected_label": "kick",
        "selected_source": "audio_only",
        "confidence_band": "high",
        "out_of_distribution": {"status": "in_distribution", "score": 0.1},
        "evidence_used": ["audio_only"],
        "latency_ms": 4,
        "limitations": ["advisory only"],
    }
    turn = _audio_classification_context_turn(context)
    assert turn is not None
    assert turn["content"].startswith("KENN_EVIDENCE_PACKET_V1:")
    response: dict = {}
    _attach_audio_classification_evidence(response, context)
    assert response["audio_classification_evidence"]["source"] == "audio_classification"
    assert response["audio_classification_evidence"]["facts"][0]["value"] == "kick"
