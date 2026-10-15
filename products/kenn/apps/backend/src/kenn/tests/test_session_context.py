from __future__ import annotations

import math
from copy import deepcopy

import pytest

from kenn.core.session_context import build_session_context, validate_session_context
from kenn.core.evidence import REFERENCE_SIGNAL_LIMITATION, UPLOADED_SIGNAL_LIMITATION


def _snapshot() -> dict:
    return {
        "status": "connected",
        "tempo": 120.0,
        "signature_numerator": 4,
        "signature_denominator": 4,
        "root_note": 0,
        "scale_name": "Major",
        "is_playing": False,
        "selected_track_index": 1,
        "tracks": [
            {
                "index": 0, "name": "Kick", "type": "audio", "devices": [],
                "output_meter_level": 0.82, "output_meter_right": 0.78,
                "output_routing_type": "Master",
                "sends": [{"index": 0, "return_track_index": 0, "return_track_name": "A-Reverb", "value": 0.1}],
                "clip_slots": [{"index": 0, "name": "Kick Loop", "has_clip": True, "is_playing": False, "length": 16.0}],
                "arrangement_clips": [{"index": 0, "name": "Kick Arrangement", "start_time_beats": 1.0, "length_beats": 16.0}],
            },
            {"index": 1, "name": "2-MIDI", "type": "midi", "devices": [{"index": 0, "name": "EQ Eight"}]},
        ],
        "scenes": [{"index": 0, "name": "Verse"}, {"index": 1, "name": "Chorus"}],
        "locators": [{"index": 0, "name": "Verse", "time_beats": 1.0}],
        "return_tracks": [{"index": 0, "name": "A-Reverb", "devices": [{"index": 0, "name": "Hybrid Reverb"}]}],
        "understanding_capabilities": {"locators": True, "arrangement_clip_inventory": False, "bad": "ignored"},
        "master_track": {"name": "Master", "volume": 0.85, "devices": [{"index": 0, "name": "Limiter"}]},
    }


def test_session_context_composes_live_roles_and_capabilities() -> None:
    context = build_session_context(
        snapshot=_snapshot(),
        session_id="test",
        device_matrix={
            "schema": "kenn.ableton_device_matrix.v1",
            "status": "connected",
            "connected": True,
            "transport": "AbletonOSC",
            "observed_families": ["EQ Eight"],
            "families": {"EQ Eight": {"qualification": "qualified", "next_control": "existing parameter"}},
            "entries": [{
                "track_index": 1,
                "track_name": "2-MIDI",
                "device_index": 0,
                "device_name": "EQ Eight",
                "qualification": "qualified",
                "parameter_probe": {
                    "success": True,
                    "parameter_count": 1,
                    "parameters": [{"index": 0, "name": "1 Gain A", "value": 0.0, "min": -15.0, "max": 15.0}],
                },
            }],
        },
    )

    assert validate_session_context(context)["ok"] is True
    assert context["transport"]["status"] == "connected"
    assert context["transport"]["signature_numerator"] == 4
    assert context["transport"]["scale_name"] == "Major"
    assert context["tracks"][0]["classification"]["role"] == "kick"
    assert context["tracks"][0]["output_meter_level"] == 0.82
    assert context["tracks"][0]["output_meter_right"] == 0.78
    assert context["tracks"][1]["classification"]["confidence_band"] == "low"
    assert context["devices"] == [{"track_index": 1, "track_name": "2-MIDI", "index": 0, "name": "EQ Eight"}]
    assert context["tracks"][0]["routing"] == {"output_routing_type": "Master"}
    assert context["tracks"][0]["sends"][0]["return_track_name"] == "A-Reverb"
    assert context["tracks"][0]["clip_slots"][0]["name"] == "Kick Loop"
    assert context["tracks"][0]["arrangement_clips"][0]["name"] == "Kick Arrangement"
    assert "is_grouped" not in context["tracks"][0]
    assert "is_foldable" not in context["tracks"][0]
    assert context["scenes"][1] == {"index": 1, "name": "Chorus"}
    assert context["locators"] == [{"index": 0, "name": "Verse", "time_beats": 1.0}]
    assert context["return_tracks"][0]["devices"][0]["name"] == "Hybrid Reverb"
    assert context["observation_capabilities"] == {"locators": True, "arrangement_clip_inventory": False}
    assert context["master_track"]["devices"][0]["name"] == "Limiter"
    assert "inspect_live" in context["available_actions"]
    assert context["device_capability_matrix"]["entries"][0]["parameter_probe"]["parameters"][0]["name"] == "1 Gain A"
    assert "inspect_device_capabilities" in context["available_actions"]
    assert context["snapshot_fingerprint"].startswith("sha256:")


def test_session_context_preserves_group_identity_as_read_only_evidence() -> None:
    snapshot = _snapshot()
    snapshot["tracks"][0].update({
        "is_grouped": True,
        "is_foldable": False,
        "group_track_index": 1,
        "group_track_name": "Drums",
    })
    context = build_session_context(snapshot=snapshot)

    assert context["tracks"][0]["is_grouped"] is True
    assert context["tracks"][0]["is_foldable"] is False
    assert context["tracks"][0]["group_track_index"] == 1
    assert context["tracks"][0]["group_track_name"] == "Drums"


def test_session_context_omits_invalid_device_matrix_and_explains_limitation() -> None:
    context = build_session_context(snapshot=_snapshot(), device_matrix={"schema": "wrong"})

    assert context["device_capability_matrix"] is None
    assert any("capability matrix" in item for item in context["limitations"])


def test_session_context_advertises_only_verified_async_services() -> None:
    unavailable = build_session_context(snapshot=_snapshot())
    available = build_session_context(
        snapshot=_snapshot(), audiogen_available=True, offline_render_available=True,
    )

    assert unavailable["service_capabilities"] == {
        "audiogen_available": False,
        "offline_render_available": False,
    }
    assert "create_generation_job" not in unavailable["available_actions"]
    assert "create_offline_render" not in unavailable["available_actions"]
    assert "create_generation_job" in available["available_actions"]
    assert "create_offline_render" in available["available_actions"]
    assert validate_session_context(available)["ok"] is True


def test_session_context_keeps_audio_sources_separate_and_bounded() -> None:
    context = build_session_context(
        snapshot=None,
        plugin_frames=[{"schema": "audio_feature_frame.v1", "peak_dbfs": -1.0, "rms_dbfs": -14.0, "stereo_correlation": 0.9, "stereo_width": 0.1}],
        mix_review_receipts=[{"schema": "kenn.mix_review.local_receipt.v2", "status": "completed", "metrics": {"peak_dbfs": -1.0}}],
        audiogen_jobs=[{"schema": "kenn.audiogen_midi_job.v1", "job_id": "m1", "status": "completed", "artifact": {"kind": "midi", "sha256": "abc", "note_count": 12}}],
        automix_receipts=[{"schema": "kenn.automix.local_receipt.v1", "status": "completed", "source": {"files": ["bass.wav"], "sha256": {"bass.wav": "def"}}}],
    )

    assert context["tracks"] == []
    assert context["measurements"][0]["kind"] == "plugin_feature_frame"
    assert context["measurements"][1]["kind"] == "mix_review"
    assert context["generated_jobs"][0]["artifact"]["kind"] == "midi"
    assert context["offline_jobs"][0]["status"] == "completed"
    assert "review_generated_asset" in context["available_actions"]
    assert "compare_offline_candidate" in context["available_actions"]
    assert validate_session_context(context)["ok"] is True


@pytest.mark.parametrize("rms", [-80.0, -81.0, None, "invalid", True, float("nan"), float("inf"), float("-inf")])
def test_quiet_or_unqualified_plugin_frame_withholds_signal_measurements(rms: object) -> None:
    frame = {
        "schema": "kenn.live_mix_context.v1",
        "scope": "plugin_bus",
        "conversation_id": "capture-7",
        "host_track_name": "Bus A",
        "rms_dbfs": rms,
        "peak_dbfs": -1.0,
        "stereo_correlation": -0.5,
        "spectrum_schema": "spectrum.v1",
        "spectrum_bands": [{"center_hz": 100.0, "level_db": -20.0}],
        "pink_noise_reference": {"largest_deviation": {"center_hz": 100.0, "deviation_db": 8.0}},
        "measurement_window": {"sample_count": 2048, "source_generation": 3},
        "live_window": {"status": "ready", "sample_count": 2048, "window_seconds": 0.05, "pink_noise_shape": {"deviation_delta_db": 4.0}},
        "freshness": {"status": "fresh", "age_seconds": 0.1},
    }
    if rms is None:
        frame.pop("rms_dbfs")
    original = deepcopy(frame)

    context = build_session_context(snapshot=None, plugin_frames=[frame])

    measurement = context["measurements"][0]
    assert measurement["metrics"] == {}
    assert "signal_limitation" in measurement
    assert measurement["conversation_id"] == "capture-7"
    assert measurement["host_track_name"] == "Bus A"
    assert measurement["measurement_window"] == {"sample_count": 2048, "source_generation": 3}
    assert measurement["live_window"] == {"status": "ready", "sample_count": 2048, "window_seconds": 0.05}
    assert measurement["freshness"] == original["freshness"]
    assert not {"spectrum_schema", "spectrum_bands", "pink_noise_reference"} & measurement.keys()
    assert context["limitations"][-1] == measurement["signal_limitation"]
    assert frame == original
    assert validate_session_context(context)["ok"] is True


@pytest.mark.parametrize("rms", [-79.9, -20.0])
def test_active_plugin_frame_retains_signal_measurements(rms: float) -> None:
    context = build_session_context(
        snapshot=None,
        plugin_frames=[{
            "schema": "kenn.live_mix_context.v1",
            "rms_dbfs": rms,
            "peak_dbfs": -1.0,
            "stereo_correlation": 0.9,
            "spectrum_bands": [{"center_hz": 100.0, "level_db": -20.0}],
            "pink_noise_reference": {"largest_deviation": {"center_hz": 100.0, "deviation_db": 2.0}},
        }],
    )
    measurement = context["measurements"][0]
    assert measurement["metrics"]["rms_dbfs"] == rms
    assert measurement["metrics"]["peak_dbfs"] == -1.0
    assert measurement["spectrum_bands"]
    assert measurement["pink_noise_reference"]


def test_session_context_exposes_only_completed_advisory_audio_classification() -> None:
    digest = "sha256:" + "a" * 64
    classification = {
        "schema": "kenn.audio_classification.v1", "status": "completed", "audio_sha256": digest,
        "model_id": "slo-export-v1", "model_sha256": "sha256:" + "b" * 64,
        "label_map_sha256": "sha256:" + "c" * 64, "inference_version": "1",
        "audio_only": [{"label": "kick", "probability": 0.9}],
        "metadata_assisted": [{"label": "kick", "probability": 0.95}],
        "selected_label": "kick", "selected_source": "audio_only", "confidence_band": "high",
        "out_of_distribution": {"status": "in_distribution", "score": 0.1},
        "evidence_used": ["audio_only"], "latency_ms": 4, "limitations": ["advisory only"],
    }
    context = build_session_context(
        snapshot=_snapshot(), audio_classifications=[classification, {"status": "disabled", "audio_sha256": digest}],
    )
    assert len(context["audio_classifications"]) == 1
    observed = context["audio_classifications"][0]
    assert observed["status"] == "completed"
    assert observed["audio_only"] == [{"label": "kick", "probability": 0.9}]
    assert observed["metadata_assisted"] == [{"label": "kick", "probability": 0.95}]
    assert observed["advisory_only"] is True and observed["live_mutation_authorized"] is False
    assert "audio_classification" in [item["kind"] for item in context["sources"]]
    assert "apply_live_action" not in context["available_actions"]
    assert validate_session_context(context)["ok"] is True


def test_session_context_revalidates_classifier_entries_after_context_mutation() -> None:
    digest = "sha256:" + "a" * 64
    classification = {
        "schema": "kenn.audio_classification.v1", "status": "completed", "audio_sha256": digest,
        "model_id": "slo-export-v1", "model_sha256": "sha256:" + "b" * 64,
        "label_map_sha256": "sha256:" + "c" * 64, "inference_version": "1",
        "audio_only": [{"label": "kick", "probability": 0.9}],
        "metadata_assisted": [{"label": "kick", "probability": 0.95}],
        "selected_label": "kick", "selected_source": "audio_only", "confidence_band": "high",
        "out_of_distribution": {"status": "in_distribution", "score": 0.1},
        "evidence_used": ["audio_only"], "latency_ms": 4, "limitations": ["advisory only"],
    }
    context = build_session_context(snapshot=_snapshot(), audio_classifications=[classification])
    assert validate_session_context(context)["ok"] is True

    context["audio_classifications"][0]["selected_label"] = "snare"
    result = validate_session_context(context)
    assert result["ok"] is False
    assert any("audio classification 1 is invalid" in item.lower() for item in result["errors"])


def test_session_context_validator_rejects_wrong_schema_and_unbounded_tracks() -> None:
    invalid = {"schema": "wrong", "tracks": []}
    assert validate_session_context(invalid)["ok"] is False

    context = build_session_context(snapshot=_snapshot())
    context["tracks"] = [{}] * 257
    result = validate_session_context(context)
    assert result["ok"] is False
    assert "too many tracks" in " ".join(result["errors"])


def test_session_context_validator_rejects_stale_observations() -> None:
    context = build_session_context(snapshot=_snapshot())
    context["observed_at"] -= 301

    result = validate_session_context(context)

    assert result["ok"] is False
    assert any("stale" in error for error in result["errors"])


def test_session_context_validator_handles_wrong_collection_types_and_nan_time() -> None:
    context = build_session_context(snapshot=_snapshot())
    context["tracks"] = None
    context["scenes"] = {"not": "a list"}
    context["observed_at"] = math.nan

    result = validate_session_context(context)

    assert result["ok"] is False
    assert any("tracks must be a list" in error for error in result["errors"])
    assert any("scenes must be a list" in error for error in result["errors"])
    assert any("Unix timestamp" in error for error in result["errors"])


def _uploaded_receipt(*, standalone=False):
    return {
        "schema": "kenn.mix_review.reference_comparison.v1" if standalone else "kenn.mix_review.local_review.v1",
        "status": "completed", "analysis_version": "fixture-v1", "review_id": "mix-a",
        "source_mix": {"filename": "mix.wav", "sha256": "abc", "cached_signal": "discard"},
        "source_reference": {"filename": "reference.wav", "sha256": "def"},
        "reference": {"filename": "reference.wav", "sha256": "def"},
        "input_context": {"channel_layout": "stereo", "sample_rate_hz": 48000},
        "metrics": {"rms_dbfs": -18.0, "peak_dbfs": -1.0},
        "findings": [{"detail": "Old peak finding"}], "action_plan": [{"action": "Old gain move"}],
        "limitations": ["Whole-file scope."],
        "reference_comparison": {
            "dynamics": {"mix": {"rms_dbfs": -18.0, "crest_db": 8.0}, "reference": {"rms_dbfs": -14.0}},
            "comparison_basis": "Uploaded pair around 1 kHz.", "lufs_delta_db": -4.0,
            "largest_ltas_difference": {"center_hz": 200.0, "delta_db": 3.0},
            "pink_noise_reference": {"curve": "pink", "largest_deviation": {"center_hz": 200.0, "deviation_db": 4.0}},
            "recommendations": ["Old EQ move"],
        },
    }


@pytest.mark.parametrize("rms", [None, "-18", True, False, math.nan, math.inf, -math.inf, 10**400, -100.0, -60.0])
def test_canonical_uploaded_receipt_rejects_quiet_or_invalid_own_measurements(rms):
    # Canonical ingestion must requalify old receipts even when status publication was bypassed.
    receipt = _uploaded_receipt()
    receipt["metrics"]["rms_dbfs"] = rms
    before = deepcopy(receipt)
    context = build_session_context(snapshot=_snapshot(), mix_review_receipts=[receipt])
    measurement = context["measurements"][0]

    assert measurement["metrics"] == {}
    assert measurement["findings"] == measurement["action_plan"] == []
    assert "reference_comparison" not in measurement
    assert UPLOADED_SIGNAL_LIMITATION in measurement["limitations"]
    assert measurement["input_context"] == receipt["input_context"]
    assert measurement["source_mix"] == {"filename": "mix.wav", "sha256": "abc"}
    assert measurement["review_id"] == "mix-a"
    assert measurement["reference"] == receipt["reference"]
    assert validate_session_context(context)["ok"] is True
    assert receipt == before


@pytest.mark.parametrize("source", ["mix", "reference"])
@pytest.mark.parametrize("rms", [None, "-18", True, math.nan, math.inf, -math.inf, 10**400, -100.0, -60.0])
def test_canonical_standalone_comparison_requires_activity_from_both_sources(source, rms):
    receipt = _uploaded_receipt(standalone=True)
    receipt["reference_comparison"]["dynamics"][source]["rms_dbfs"] = rms
    before = deepcopy(receipt)
    context = build_session_context(snapshot=_snapshot(), mix_review_receipts=[receipt])
    measurement = context["measurements"][0]

    assert measurement["metrics"] == {}
    assert measurement["findings"] == measurement["action_plan"] == []
    assert "reference_comparison" not in measurement
    assert REFERENCE_SIGNAL_LIMITATION in measurement["limitations"]
    assert measurement["source_reference"] == {"filename": "reference.wav", "sha256": "def"}
    assert receipt == before


@pytest.mark.parametrize("dynamics", [None, {}, {"mix": {"rms_dbfs": -18.0}}, {"reference": {"rms_dbfs": -18.0}}])
def test_canonical_standalone_comparison_withholds_legacy_deltas_without_pair_rms(dynamics):
    receipt = _uploaded_receipt(standalone=True)
    receipt["reference_comparison"]["dynamics"] = dynamics
    measurement = build_session_context(snapshot=_snapshot(), mix_review_receipts=[receipt])["measurements"][0]
    assert "reference_comparison" not in measurement
    assert REFERENCE_SIGNAL_LIMITATION in measurement["limitations"]


def test_canonical_active_upload_keeps_own_findings_when_reference_is_quiet():
    receipt = _uploaded_receipt()
    receipt["reference_comparison"]["dynamics"]["reference"]["rms_dbfs"] = -60.0
    measurement = build_session_context(snapshot=_snapshot(), mix_review_receipts=[receipt])["measurements"][0]
    assert measurement["metrics"] == receipt["metrics"]
    assert measurement["findings"] == receipt["findings"]
    assert measurement["action_plan"] == receipt["action_plan"]
    assert "reference_comparison" not in measurement
    assert REFERENCE_SIGNAL_LIMITATION in measurement["limitations"]


@pytest.mark.parametrize("standalone", [False, True])
def test_canonical_active_comparison_keeps_bounded_pair_rms_for_downstream_requalification(standalone):
    receipt = _uploaded_receipt(standalone=standalone)
    receipt["reference_comparison"]["dynamics"]["mix"]["rms_dbfs"] = -59.9
    before = deepcopy(receipt)
    measurement = build_session_context(snapshot=_snapshot(), mix_review_receipts=[receipt])["measurements"][0]
    comparison = measurement["reference_comparison"]
    assert comparison["dynamics"] == {"mix": {"rms_dbfs": -59.9}, "reference": {"rms_dbfs": -14.0}}
    assert comparison["largest_ltas_difference"] == {"center_hz": 200.0, "delta_db": 3.0}
    assert comparison["pink_noise_reference"]["largest_deviation"]["deviation_db"] == 4.0
    assert "recommendations" not in comparison
    assert receipt == before
    comparison["dynamics"]["mix"]["rms_dbfs"] = -100.0
    assert receipt == before
