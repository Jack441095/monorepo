from __future__ import annotations

import math

from kenn.core.session_context import build_session_context, validate_session_context


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
