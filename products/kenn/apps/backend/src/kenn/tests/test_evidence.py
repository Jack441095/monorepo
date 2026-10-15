from __future__ import annotations

from copy import deepcopy
import json

import pytest

from kenn.core.evidence import (
    MARKER,
    TRANSIENT_SIGNAL_LIMITATION,
    STEM_MASKING_SIGNAL_LIMITATION,
    ERB_PREVIEW_LIMITATION,
    qualified_stem_masking_summary,
    stem_masking_has_activity,
    from_ableton_session,
    from_audio_classification_context,
    from_mix_review_context,
    from_plugin_context,
    live_context_has_activity,
    uploaded_metrics_have_activity,
    transient_preservation_has_activity,
    reference_comparison_has_activity,
    plugin_context_for_advice,
    from_realtime_mix_comparison,
    from_stem_masking_context,
    relevant_observations,
    history_turn,
    packets_from_history,
)
from kenn.core.realtime_mix_comparison import build_realtime_mix_comparison


def _transient_summary(*, pre_rms=-18.0, post_rms=-20.0, score=0.0, count=1, profile="clean"):
    return {
        "score": score,
        "matched_event_count": count,
        "profile": profile,
        "activity": {
            "schema": "kenn.transient_preservation.activity.v1",
            "pre_rms_dbfs": pre_rms,
            "post_rms_dbfs": post_rms,
        },
    }


def _erb_summary():
    return {
        "stem_count": 2, "lowest_visibility": 0.0, "lowest_visibility_stem": "Bass",
        "activity": {"schema": "kenn.erb_masking.activity.v1", "active_floor_dbfs": -60.0,
                     "frame_size_samples": 4096,
                     "sources": [{"name": name, "sample_rate": 44100, "frame_count": 16, "active_frame_count": 8} for name in ("Bass", "Kick")],
                     "pairs": [{"stems": ["Bass", "Kick"], "simultaneously_active_frame_count": 4}]},
    }


def _masking_context():
    return {
        "schema": "kenn.mix_review_masking_analysis.v1", "ok": True,
        "activity": {
            "schema": "kenn.stem_masking.activity.v1", "active_floor_dbfs": -50.0, "frame_count": 100,
            "sources": [{"name": "Bass", "active_frame_count": 80}, {"name": "Piano", "active_frame_count": 70}],
            "pairs": [{"stems": ["Bass", "Piano"], "simultaneously_active_frame_count": 60}],
        },
        "findings": [{"fault_family": "masking", "detected": True, "stems": ["Bass", "Piano"], "band": "bass", "evidence": {
            "competing_frame_fraction": 0.454, "active_floor_dbfs": -50.0, "competing_within_db": 6.0,
        }}],
        "evidence": {
            "schema": "kenn.evidence.v1", "source": "stem_masking_analysis",
            "facts": [
                {"name": "stem_count", "value": 2, "unit": "stems"},
                {"name": "sample_rate", "value": 44100, "unit": "Hz"},
                {"name": "analyzed_seconds", "value": 5.0, "unit": "seconds"},
                {"name": "masking_candidate_count", "value": 999},
                {"name": "masking_highest_pair", "value": "Cached wrong pair"},
            ],
            "limitations": ["Not a perceptual masking model."],
        },
    }


def test_stem_masking_evidence_preserves_proxy_limits() -> None:
    packet = from_stem_masking_context(_masking_context())
    assert packet is not None
    assert packet.source == "stem_masking_analysis"
    values = {fact.name: fact.value for fact in packet.facts}
    assert values["masking_highest_competing_frame_fraction"] == 0.454
    assert values["masking_candidate_count"] == 1
    assert values["masking_highest_pair"] == "Bass + Piano"
    assert "perceptual" in packet.limitations[0]


def test_stem_masking_evidence_generates_bounded_follow_up_observation() -> None:
    packet = from_stem_masking_context(_masking_context())
    assert packet is not None
    observations = relevant_observations("what is competing in the low end?", [packet])
    assert any("Bass + Piano" in item and "45.4%" in item for item in observations)
    assert any("not proof of audible masking" in item for item in observations)


def test_active_stem_pair_with_no_candidates_keeps_zero_as_a_measured_result():
    context = _masking_context()
    context["findings"] = []
    packet = from_stem_masking_context(context)
    values = {fact.name: fact.value for fact in packet.facts}
    assert values["masking_candidate_count"] == 0
    assert "masking_highest_pair" not in values
    assert any("no flagged competing pair" in item for item in relevant_observations("check masking", [packet]))


@pytest.mark.parametrize("activity", [None, {}, "old cached activity"])
def test_legacy_masking_scalars_cannot_replace_missing_source_activity(activity):
    # Cached positive/zero facts once reached reasoning without proving either stem was active.
    context = _masking_context()
    context["activity"] = activity
    before = deepcopy(context)
    packet = from_stem_masking_context(context)
    assert {fact.name for fact in packet.facts} == {"stem_count", "sample_rate", "analyzed_seconds"}
    assert any("withheld" in item for item in packet.limitations)
    assert relevant_observations("check masking", [packet]) == []
    assert context == before


@pytest.mark.parametrize("field,value", [
    ("schema", "unknown"), ("active_floor_dbfs", -60.0), ("active_floor_dbfs", True),
    ("active_floor_dbfs", float("nan")), ("frame_count", True), ("frame_count", 0),
    ("frame_count", -1), ("frame_count", 100.0), ("frame_count", float("inf")),
    ("sources", []), ("sources", [{}]), ("pairs", []), ("pairs", None),
])
def test_masking_activity_requires_the_versioned_complete_capture_contract(field, value):
    context = _masking_context()
    context["activity"][field] = value
    packet = from_stem_masking_context(context)
    assert not any(fact.name.startswith("masking_") for fact in packet.facts)
    assert any("withheld" in item for item in packet.limitations)


@pytest.mark.parametrize("count", [True, -1, 101, 1.0, float("nan"), float("inf"), 10**400, "80"])
def test_masking_source_counts_must_be_integer_subsets_of_captured_frames(count):
    context = _masking_context()
    context["activity"]["sources"][0]["active_frame_count"] = count
    packet = from_stem_masking_context(context)
    assert not any(fact.name.startswith("masking_") for fact in packet.facts)


@pytest.mark.parametrize("count", [0, 49, True, -1, 71, 1.0, float("nan"), float("inf"), 10**400])
def test_masking_pair_counts_require_simultaneous_frames_within_both_source_counts(count):
    context = _masking_context()
    context["activity"]["pairs"][0]["simultaneously_active_frame_count"] = count
    packet = from_stem_masking_context(context)
    assert not any(fact.name.startswith("masking_") for fact in packet.facts)


@pytest.mark.parametrize("names", [["Bass", "Unknown"], ["Bass", "Bass"], ["Bass"], ["Bass", []]])
def test_masking_pair_identity_must_name_two_measured_sources(names):
    context = _masking_context()
    context["activity"]["pairs"][0]["stems"] = names
    packet = from_stem_masking_context(context)
    assert not any(fact.name.startswith("masking_") for fact in packet.facts)


def test_masking_duplicate_pairs_and_missing_third_source_pairs_cannot_prove_zero():
    context = _masking_context()
    context["findings"] = []
    context["activity"]["sources"].append({"name": "Kick", "active_frame_count": 90})
    context["activity"]["pairs"] *= 3
    packet = from_stem_masking_context(context)
    assert not any(fact.name.startswith("masking_") for fact in packet.facts)


@pytest.mark.parametrize("fraction", [True, "0.454", None, float("nan"), float("inf"), 10**400, -0.1, 0.199, 0.601, 1.1])
def test_masking_candidates_need_finite_fraction_supported_by_pair_activity(fraction):
    context = _masking_context()
    context["findings"][0]["evidence"]["competing_frame_fraction"] = fraction
    packet = from_stem_masking_context(context)
    assert not any(fact.name.startswith("masking_") for fact in packet.facts)


@pytest.mark.parametrize("fraction", [0.20, 0.60])
def test_masking_candidate_fraction_accepts_existing_threshold_and_pair_upper_bound(fraction):
    context = _masking_context()
    context["findings"][0]["evidence"]["competing_frame_fraction"] = fraction
    packet = from_stem_masking_context(context)
    assert next(fact.value for fact in packet.facts if fact.name == "masking_highest_competing_frame_fraction") == fraction


def test_masking_candidate_fraction_keeps_the_producers_three_decimal_rounding():
    context = _masking_context()
    context["activity"]["frame_count"] = 337
    context["activity"]["sources"] = [{"name": "Bass", "active_frame_count": 200}, {"name": "Piano", "active_frame_count": 200}]
    context["activity"]["pairs"][0]["simultaneously_active_frame_count"] = 100
    context["findings"][0]["evidence"]["competing_frame_fraction"] = 0.297
    packet = from_stem_masking_context(context)
    assert any(fact.name == "masking_candidate_count" for fact in packet.facts)


@pytest.mark.parametrize("field,value", [
    ("stems", ["Bass", "Unknown"]), ("band", "unknown"), ("evidence", {}), ("band", []),
    ("fault_family", "other"), ("detected", False), ("detected", 1),
])
def test_malformed_masking_candidate_abstains_instead_of_becoming_zero(field, value):
    context = _masking_context()
    context["findings"][0][field] = value
    packet = from_stem_masking_context(context)
    assert not any(fact.name.startswith("masking_") for fact in packet.facts)


def test_masking_candidate_from_quiet_third_stem_is_withheld_even_with_an_active_pair():
    context = _masking_context()
    context["activity"]["sources"].append({"name": "Quiet", "active_frame_count": 0})
    context["activity"]["pairs"].extend([
        {"stems": ["Bass", "Quiet"], "simultaneously_active_frame_count": 0},
        {"stems": ["Piano", "Quiet"], "simultaneously_active_frame_count": 0},
    ])
    context["findings"][0]["stems"] = ["Bass", "Quiet"]
    packet = from_stem_masking_context(context)
    assert not any(fact.name.startswith("masking_") for fact in packet.facts)


def test_masking_provenance_rejects_nonfinite_and_malformed_fact_values():
    context = _masking_context()
    context["activity"] = None
    context["evidence"]["facts"].extend([
        {"name": [], "value": 4}, {"name": "sample_rate", "value": float("inf")},
        {"name": "analyzed_seconds", "value": 10**400}, {"name": "stem_count", "value": True},
        {"name": "stem_count", "value": 13},
    ])
    packet = from_stem_masking_context(context)
    assert len(packet.facts) == 3


def test_active_masking_projection_leaves_input_and_nested_identity_unchanged():
    context = _masking_context()
    before = deepcopy(context)
    packet = from_stem_masking_context(context)
    context["findings"][0]["stems"][0] = "Changed"
    assert next(fact.value for fact in packet.facts if fact.name == "masking_highest_pair") == "Bass + Piano"
    context["findings"][0]["stems"][0] = "Bass"
    assert context == before


@pytest.mark.parametrize("findings", [None, []])
def test_masking_history_retains_activity_to_requalify_positive_and_zero_results(findings):
    context = _masking_context()
    if findings is not None:
        context["findings"] = findings
    packet = from_stem_masking_context(context)
    recovered, = packets_from_history([history_turn(packet)])
    assert recovered.facts == packet.facts
    assert recovered.stem_masking_provenance == packet.stem_masking_provenance
    assert recovered.limitations == packet.limitations


def test_legacy_masking_history_with_positive_scalar_claims_keeps_only_capture_provenance():
    # Stored evidence predating activity metadata must not regain a sonic claim on replay.
    raw = _masking_context()["evidence"]
    recovered, = packets_from_history([{"role": "user", "content": MARKER + json.dumps(raw)}])
    assert {fact.name for fact in recovered.facts} == {"stem_count", "sample_rate", "analyzed_seconds"}
    assert relevant_observations("check masking", [recovered]) == []
    assert any("withheld" in item for item in recovered.limitations)


def test_masking_history_rechecks_quiet_activity_and_does_not_trust_replayed_scalar_facts():
    packet = from_stem_masking_context(_masking_context())
    payload = packet.payload()
    payload["stem_masking_provenance"]["activity"]["pairs"][0]["simultaneously_active_frame_count"] = 0
    recovered, = packets_from_history([{"role": "user", "content": MARKER + json.dumps(payload)}])
    assert not any(fact.name.startswith("masking_") for fact in recovered.facts)
    assert any("withheld" in item for item in recovered.limitations)


def test_masking_history_rebuilds_facts_from_provenance_instead_of_tampered_scalars():
    packet = from_stem_masking_context(_masking_context())
    payload = packet.payload()
    payload["facts"].append({"name": "masking_candidate_count", "value": 999})
    recovered, = packets_from_history([{"role": "user", "content": MARKER + json.dumps(payload)}])
    assert [fact.value for fact in recovered.facts if fact.name == "masking_candidate_count"] == [1]


def test_masking_payload_copies_only_bounded_activity_and_normalized_finding_fields():
    context = _masking_context()
    context["activity"]["raw_fft"] = [123.0]
    context["findings"][0]["suggested_next_step"] = "Unvalidated prose must not survive history"
    before = deepcopy(context)
    packet = from_stem_masking_context(context)
    payload = packet.payload()
    provenance = payload["stem_masking_provenance"]
    assert set(provenance["activity"]) == {"schema", "active_floor_dbfs", "frame_count", "sources", "pairs"}
    assert set(provenance["findings"][0]) == {"fault_family", "detected", "stems", "band", "evidence"}
    provenance["activity"]["sources"][0]["active_frame_count"] = 0
    provenance["findings"][0]["stems"][0] = "Changed"
    assert packet.stem_masking_provenance["activity"]["sources"][0]["active_frame_count"] == 80
    assert packet.stem_masking_provenance["findings"][0]["stems"] == ["Bass", "Piano"]
    assert context == before


def test_audio_classification_evidence_keeps_prediction_streams_separate() -> None:
    digest = "sha256:" + "a" * 64
    packet = from_audio_classification_context({
        "schema": "kenn.audio_classification.v1",
        "status": "completed",
        "audio_sha256": digest,
        "model_id": "slo-export-v1",
        "model_sha256": "sha256:" + "b" * 64,
        "label_map_sha256": "sha256:" + "c" * 64,
        "inference_version": "1",
        "audio_only": [{"label": "kick", "probability": 0.9}, {"label": "snare", "probability": 0.1}],
        "metadata_assisted": [{"label": "kick", "probability": 0.95}],
        "selected_label": "kick",
        "selected_source": "audio_only",
        "confidence_band": "high",
        "out_of_distribution": {"status": "in_distribution", "score": 0.1},
        "evidence_used": ["audio_only"],
        "latency_ms": 4,
        "limitations": ["advisory only"],
    })

    assert packet is not None
    observations = relevant_observations("classify this sample", [packet])
    assert any("'kick'" in item and "audio only" in item for item in observations)
    assert any("Audio-only candidates: kick (90.0%), snare (10.0%)." in item for item in observations)
    assert any("Metadata-assisted candidates" in item for item in observations)
    assert all("proof" not in item.lower() or "not proof" in item.lower() for item in observations)


def test_unknown_audio_classification_stays_unresolved() -> None:
    payload = {
        "schema": "kenn.audio_classification.v1",
        "status": "completed",
        "audio_sha256": "sha256:" + "a" * 64,
        "model_id": "slo-export-v1",
        "model_sha256": "sha256:" + "b" * 64,
        "label_map_sha256": "sha256:" + "c" * 64,
        "inference_version": "1",
        "audio_only": [{"label": "Unknown", "probability": 0.6}],
        "metadata_assisted": [{"label": "Unknown", "probability": 0.6}],
        "selected_label": "Unknown",
        "selected_source": "unknown",
        "confidence_band": "low",
        "out_of_distribution": {"status": "out_of_distribution", "score": 0.98},
        "evidence_used": ["audio_only"],
        "latency_ms": 4,
        "limitations": ["advisory only"],
    }
    packet = from_audio_classification_context(payload)
    assert packet is not None
    observations = relevant_observations("identify this sample", [packet])
    assert any("identity as unresolved" in item for item in observations)


def test_ableton_evidence_preserves_track_device_inventory() -> None:
    packet = from_ableton_session(
        {
            "status": "connected",
            "tempo": 120.0,
            "tracks": [
                {"index": 0, "name": "1-MIDI", "devices": []},
                {"index": 1, "name": "4-Audio", "devices": [{"index": 0, "name": "EQ Eight"}]},
            ],
        }
    )

    assert packet is not None
    inventory = next(fact.value for fact in packet.facts if fact.name == "track_inventory")
    assert inventory == "1: 1-MIDI (no devices); 2: 4-Audio (EQ Eight)"
    observations = relevant_observations("What devices are in the Ableton session?", [packet])
    assert any("EQ Eight" in observation for observation in observations)


def test_plugin_evidence_preserves_realtime_band_energy_as_limited_measurement() -> None:
    packet = from_plugin_context({
        "schema": "kenn.live_mix_context.v1",
        "age_seconds": 1.0,
        "peak_dbfs": -5.0,
        "rms_dbfs": -18.0,
        "stereo_correlation": 0.8,
        "stereo_width": 0.2,
        "low_energy": 0.04,
        "mid_energy": 0.01,
        "high_energy": 0.002,
    })

    assert packet is not None
    assert {fact.name for fact in packet.facts} >= {"low_energy", "mid_energy", "high_energy"}
    assert any("not a calibrated spectrum" in item for item in packet.limitations)


@pytest.mark.parametrize("rms_dbfs", [-100.0, -80.0, None, True, float("nan"), float("inf"), 10 ** 1000])
def test_quiet_or_unqualified_plugin_context_keeps_provenance_but_withholds_signal_facts(rms_dbfs) -> None:
    # Quiet or unqualified RMS used to expose even misleading stereo and pink-reference facts to chat.
    context = {
        "schema": "kenn.live_mix_context.v1",
        "age_seconds": 1.0,
        "peak_dbfs": -0.1,
        "rms_dbfs": rms_dbfs,
        "crest_db": 79.9,
        "transient_ratio": 2.0,
        "clipped_samples": 8,
        "stereo_correlation": -0.9,
        "stereo_width": 0.9,
        "low_energy": 0.04,
        "mid_energy": 0.01,
        "high_energy": 0.002,
        "sample_rate": 48000,
        "analysed_samples": 96000,
        "audio_age_seconds": 0.12,
        "pink_noise_reference": {
            "curve": "pink baseline",
            "largest_deviation": {"center_hz": 315.0, "deviation_db": 5.0},
        },
        "measurement_window": {
            "start_sample": 4800, "end_sample": 9600, "duration_seconds": 0.1,
            "source_generation": 3, "dropped_samples": 0, "invalid_samples": 0,
        },
        "live_window": {
            "sample_count": 4, "window_seconds": 24.0, "status": "stable",
            "pink_noise_shape": {"largest_median_deviation": {"center_hz": 315.0, "median_deviation_db": 4.8}},
        },
    }

    packet = from_plugin_context(context)

    assert packet is not None
    names = {fact.name for fact in packet.facts}
    assert names >= {
        "sample_rate", "analysed_samples", "audio_age_seconds",
        "measurement_window_end_sample", "measurement_window_source_generation",
        "measurement_window_dropped_samples", "realtime_window_sample_count", "realtime_window_status",
    }
    assert not names & {
        "peak_dbfs", "rms_dbfs", "crest_db", "transient_ratio", "clipped_samples",
        "stereo_correlation", "stereo_width", "low_energy", "mid_energy", "high_energy",
        "realtime_pink_noise_largest_deviation_frequency_hz", "realtime_pink_noise_largest_deviation_db",
        "realtime_pink_noise_reference_curve", "realtime_pink_noise_median_deviation_frequency_hz",
        "realtime_pink_noise_median_deviation_db",
    }
    assert packet.payload()["freshness"]["current_for_diagnosis"] is True
    assert any("signal-derived measurements are withheld" in item for item in packet.limitations)


def test_plugin_context_just_above_activity_floor_keeps_signal_facts_and_pink_details() -> None:
    packet = from_plugin_context({
        "schema": "kenn.live_mix_context.v1",
        "age_seconds": 1.0,
        "rms_dbfs": -79.9,
        "peak_dbfs": -0.1,
        "low_energy": 0.04,
        "pink_noise_reference": {
            "curve": "pink baseline",
            "largest_deviation": {"center_hz": 315.0, "deviation_db": 5.0},
        },
        "live_window": {
            "pink_noise_shape": {"largest_median_deviation": {"center_hz": 315.0, "median_deviation_db": 4.8}},
        },
    })

    assert packet is not None
    names = {fact.name for fact in packet.facts}
    assert names >= {
        "rms_dbfs", "peak_dbfs", "low_energy", "realtime_pink_noise_largest_deviation_db",
        "realtime_pink_noise_median_deviation_db",
    }
    assert not any("signal-derived measurements are withheld" in item for item in packet.limitations)


def test_reference_ltas_measurement_is_rendered_as_a_listening_target() -> None:
    packet = from_mix_review_context({
        "schema": "kenn_mix_review_handoff.v1",
        "metrics": {"rms_dbfs": -18.0},
        "reference_comparison": {"dynamics": {"mix": {"rms_dbfs": -18.0}, "reference": {"rms_dbfs": -20.0}},
            "largest_ltas_difference": {"center_hz": 300.0, "delta_db": 5.0},
            "lufs_delta_db": 0.2,
        },
    })

    assert packet is not None
    observations = relevant_observations("Why is my mix different from the reference?", [packet])
    assert any("300 Hz is +5.0 dB" in item for item in observations)
    assert any("not an automatic master-EQ instruction" in item for item in observations)


def test_pink_noise_measurement_is_rendered_as_bounded_shape_evidence() -> None:
    packet = from_mix_review_context({
        "schema": "kenn_mix_review_handoff.v1",
        "metrics": {"rms_dbfs": -18.0},
        "reference_comparison": {"dynamics": {"mix": {"rms_dbfs": -18.0}, "reference": {"rms_dbfs": -20.0}},
            "pink_noise_reference": {
                "curve": "-3 dB per octave pink-noise-style spectral baseline",
                "largest_deviation": {"center_hz": 296.0, "deviation_db": 5.1},
            },
        },
    })

    assert packet is not None
    assert any(fact.name == "pink_noise_largest_deviation_db" for fact in packet.facts)
    observations = relevant_observations("Is my mix different from the pink noise reference?", [packet])
    assert any("5.1 dB above" in item and "296 Hz" in item for item in observations)
    assert any("not a quality score" in item for item in observations)


def test_realtime_pink_reference_is_provenanced_as_current_bus_evidence() -> None:
    packet = from_plugin_context({
        "schema": "kenn.live_mix_context.v1",
        "age_seconds": 1.0,
        "peak_dbfs": -5.0,
        "rms_dbfs": -18.0,
        "stereo_correlation": 0.8,
        "stereo_width": 0.2,
        "pink_noise_reference": {
            "curve": "-3 dB per octave pink-noise-style spectral baseline",
            "largest_deviation": {"center_hz": 315.0, "deviation_db": 5.0},
        },
        "live_window": {
            "sample_count": 4,
            "window_seconds": 24.0,
            "status": "stable",
            "pink_noise_shape": {"largest_median_deviation": {"center_hz": 315.0, "median_deviation_db": 4.8}},
        },
    })

    assert packet is not None
    assert any(fact.name == "realtime_pink_noise_largest_deviation_db" and fact.source == "plugin_bus_snapshot" for fact in packet.facts)
    observations = relevant_observations("Can you compare the current mix to pink noise?", [packet])
    assert any("315 Hz" in item and "not a quality score" in item for item in observations)
    assert any("median deviation near 315 Hz" in item and "repeatable bus trend" in item for item in observations)


def test_realtime_evidence_packet_exposes_current_diagnosis_freshness() -> None:
    packet = from_plugin_context({
        "schema": "kenn.live_mix_context.v1",
        "age_seconds": 1.0,
        "peak_dbfs": -5.0,
        "rms_dbfs": -18.0,
        "stereo_correlation": 0.8,
        "stereo_width": 0.2,
    })

    assert packet is not None
    freshness = packet.payload()["freshness"]
    assert freshness["status"] == "current"
    assert freshness["current_for_diagnosis"] is True
    assert freshness["max_current_age_seconds"] == 15.0


def test_realtime_mix_comparison_becomes_direct_answer_evidence() -> None:
    comparison = build_realtime_mix_comparison(
        {
            "metrics": {"peak_dbfs": -6.0, "rms_dbfs": -20.0},
            "reference_comparison": {"dynamics": {"mix": {"rms_dbfs": -18.0}, "reference": {"rms_dbfs": -20.0}},
                "pink_noise_reference": {
                    "largest_deviation": {"center_hz": 300.0, "deviation_db": 4.0},
                },
            },
        },
        {
            "freshness": {"age_seconds": 1.0, "current_for_diagnosis": True},
            "peak_dbfs": -2.0,
            "rms_dbfs": -17.0,
            "pink_noise_reference": {
                "largest_deviation": {"center_hz": 315.0, "deviation_db": 5.0},
            },
        },
        review_id="review-1",
        plugin_session_id="plugin-1",
    )
    packet = from_realtime_mix_comparison(comparison)

    assert packet is not None
    assert packet.payload()["freshness"]["current_for_diagnosis"] is True
    observations = relevant_observations(
        "How does the live bus compare with my uploaded reference?",
        [packet],
    )
    assert any("sample peak live -2.0 dBFS vs uploaded -6.0 dBFS" in item for item in observations)
    assert any("current/recent plugin-bus window" in item for item in observations)


def test_stale_realtime_evidence_remains_visible_but_is_not_current() -> None:
    packet = from_plugin_context({
        "schema": "kenn.live_mix_context.v1",
        "age_seconds": 30.0,
        "peak_dbfs": -5.0,
        "rms_dbfs": -18.0,
        "stereo_correlation": 0.8,
        "stereo_width": 0.2,
    })

    assert packet is not None
    freshness = packet.payload()["freshness"]
    assert freshness["status"] == "stale_or_unknown"
    assert freshness["current_for_diagnosis"] is False


def test_plugin_evidence_carries_where_the_100_ms_window_sits_and_what_was_dropped() -> None:
    # 14 Oct 2026: chat and mix review got levels from the windows but not the sample positions, capture age,
    # source generation or drop counts, so a stale or gapped window looked the same as a clean one.
    packet = from_plugin_context({
        "schema": "kenn.live_mix_context.v1",
        "age_seconds": 0.2,
        "peak_dbfs": -5.0,
        "rms_dbfs": -18.0,
        "audio_age_seconds": 0.12,
        "measurement_window": {
            "valid": True, "sequence": 7, "source_generation": 3, "start_sample": 4_800, "end_sample": 9_600,
            "duration_seconds": 0.1, "dropped_samples": 256, "invalid_samples": 0,
        },
    })

    assert packet is not None
    facts = {fact.name: (fact.value, fact.unit) for fact in packet.facts}
    assert facts["measurement_window_end_sample"] == (9_600.0, "samples")
    assert facts["measurement_window_source_generation"] == (3.0, "count")
    assert facts["measurement_window_dropped_samples"] == (256.0, "samples")
    assert facts["audio_age_seconds"] == (0.12, "seconds")


def test_a_malformed_window_field_is_left_out_not_guessed() -> None:
    packet = from_plugin_context({
        "schema": "kenn.live_mix_context.v1",
        "peak_dbfs": -5.0,
        "measurement_window": {"end_sample": "9600", "dropped_samples": True, "source_generation": 1},
    })

    assert packet is not None
    names = {fact.name for fact in packet.facts}
    assert names >= {"measurement_window_source_generation"}
    assert not names & {"measurement_window_end_sample", "measurement_window_dropped_samples"}


def test_mix_review_evidence_carries_the_live_window_it_compared() -> None:
    packet = from_realtime_mix_comparison({
        "schema": "kenn.realtime_mix_comparison.v1",
        "comparison_available": True,
        "comparisons": [{"metric": "peak_dbfs", "unit": "dBFS", "live_value": -0.1, "uploaded_value": -1.0,
                         "delta_live_minus_uploaded": 0.9}],
        "live_window": {"end_sample": 9_600.0, "source_generation": 3.0, "dropped_samples": 256.0,
                        "invalid_samples": 0.0, "audio_age_seconds": 0.12},
    })

    assert packet is not None
    facts = {fact.name: fact.value for fact in packet.facts}
    assert facts["realtime_live_window_dropped_samples"] == 256.0
    assert facts["realtime_live_window_end_sample"] == 9_600.0


@pytest.mark.parametrize("rms", [None, True, float("nan"), float("inf"), -float("inf"), 10 ** 1000, -100.0, -80.0])
def test_advice_context_withholds_nested_signal_data_and_rebuilds_cached_evidence(rms) -> None:
    # Removing only top-level meters left FFTs, paired windows and old packets available to advice clients.
    context = {
        "schema": "kenn.live_mix_context.v1", "scope": "plugin_bus", "conversation_id": "owned-session",
        "host_track_name": "Bass", "rms_dbfs": rms, "peak_dbfs": -0.1,
        "sample_rate": 48000, "analysed_samples": 4800, "age_seconds": 0.1,
        "freshness": {"current_for_diagnosis": True},
        "measurement_window": {"start_sample": 0, "end_sample": 4800, "source_generation": 3},
        "live_window": {"status": "stable", "sample_count": 4, "window_seconds": 24.0,
                        "pink_noise_shape": {"largest_median_deviation": {"center_hz": 315, "median_deviation_db": 6}}},
        "fft_spectra": {"bins": [1.0]}, "paired_windows": [{"peak_dbfs": -0.1}],
        "pink_noise_reference": {"largest_deviation": {"center_hz": 315, "deviation_db": 6}},
        "evidence": {"facts": [{"name": "peak_dbfs", "value": -0.1}]},
        "future_signal_metric": 42,
    }
    published = plugin_context_for_advice(context)

    assert not live_context_has_activity(context)
    assert published["conversation_id"] == "owned-session" and published["host_track_name"] == "Bass"
    assert published["freshness"] == context["freshness"]
    assert published["measurement_window"] == context["measurement_window"]
    assert published["live_window"] == {"status": "stable", "sample_count": 4, "window_seconds": 24.0}
    assert not set(published) & {"rms_dbfs", "peak_dbfs", "fft_spectra", "paired_windows", "pink_noise_reference", "future_signal_metric"}
    assert {fact["name"] for fact in published["evidence"]["facts"]} >= {"sample_rate", "measurement_window_source_generation"}
    assert "peak_dbfs" not in {fact["name"] for fact in published["evidence"]["facts"]}
    assert "at/below -80 dBFS" in published["signal_limitation"]
    assert context["evidence"]["facts"][0]["name"] == "peak_dbfs"
    assert "pink_noise_shape" in context["live_window"]


def test_advice_context_keeps_active_signal_data_and_preserves_missing_context() -> None:
    context = {"rms_dbfs": -79.9, "peak_dbfs": -0.1, "pink_noise_reference": {"status": "measured"}}
    published = plugin_context_for_advice(context)

    assert live_context_has_activity(context)
    assert published == context and published is not context
    assert plugin_context_for_advice(None) is None
    assert not live_context_has_activity(None)
    assert not live_context_has_activity({})


@pytest.mark.parametrize("rms,active", [
    ("missing", False), (None, False), (True, False), (False, False), ("-18", False),
    (float("nan"), False), (float("inf"), False), (-float("inf"), False),
    (10 ** 1000, False), (-100.0, False), (-60.0, False), (-59.9, True),
])
def test_uploaded_evidence_withholds_quiet_meters_and_nested_signal_facts(rms, active) -> None:
    # Caller handoffs and older stored reviews can contain quiet RMS beside convincing peak/stem/reference values.
    context = {
        "schema": "kenn_mix_review_handoff.v1",
        "metrics": {"rms_dbfs": rms, "peak_dbfs": -0.1, "stereo_correlation": -0.9},
        "analysis_evidence": {
            "transient_preservation": _transient_summary(score=0.9, profile="compressed"),
            "stem_masking": _erb_summary(),
            "low_end_stems": [{"name": "Bass"}],
        },
        "reference_comparison": {"dynamics": {"mix": {"rms_dbfs": -18.0}, "reference": {"rms_dbfs": -20.0}},
            "largest_ltas_difference": {"center_hz": 315.0, "delta_db": 5.0},
            "pink_noise_reference": {"curve": "pink baseline", "largest_deviation": {"center_hz": 315.0, "deviation_db": 5.0}},
            "lufs_delta_db": 4.0,
        },
    }
    if rms == "missing":
        context["metrics"].pop("rms_dbfs")
    saved = deepcopy(context)

    packet = from_mix_review_context(context)

    assert packet is not None and packet.source == "mix_review_upload"
    assert uploaded_metrics_have_activity(context["metrics"]) is active
    if active:
        assert {fact.name for fact in packet.facts} >= {
            "rms_dbfs", "peak_dbfs", "transient_preservation_score", "stem_masking_lowest_visibility",
            "reference_largest_ltas_delta_db", "pink_noise_largest_deviation_db", "reference_lufs_delta_db",
        }
    else:
        assert packet.facts == ()
        assert any("at/below -60 dBFS" in item for item in packet.limitations)
        assert relevant_observations("peak and pink reference bass masking", [packet]) == []
    assert context == saved


@pytest.mark.parametrize("summary", [
    None,
    {"score": 0.5, "matched_event_count": 1, "profile": "clean"},
    {**_transient_summary(), "activity": {"schema": "wrong", "pre_rms_dbfs": -18.0, "post_rms_dbfs": -20.0}},
    _transient_summary(pre_rms=-60.0),
    _transient_summary(post_rms=-60.1),
    _transient_summary(pre_rms=None),
    _transient_summary(post_rms=True),
    _transient_summary(pre_rms=float("nan")),
    _transient_summary(post_rms=float("inf")),
    _transient_summary(pre_rms=10**1000),
    _transient_summary(score=True),
    _transient_summary(score=float("nan")),
    _transient_summary(score=float("inf")),
    _transient_summary(score=-0.01),
    _transient_summary(score=1.01),
    _transient_summary(score=10**1000),
    _transient_summary(count=True),
    _transient_summary(count=0),
    _transient_summary(count=-1),
    _transient_summary(count=1.5),
    _transient_summary(profile="  "),
    _transient_summary(profile="x" * 161),
])
def test_transient_facts_require_active_pre_post_renders_and_bounded_result(summary):
    context = {
        "schema": "kenn_mix_review_handoff.v1",
        "metrics": {"rms_dbfs": -18.0, "peak_dbfs": -0.1},
        "analysis_evidence": {"transient_preservation": summary},
    }

    packet = from_mix_review_context(context)

    assert packet is not None
    assert not any(fact.name.startswith("transient_preservation_") for fact in packet.facts)
    assert packet.transient_preservation_provenance is None
    assert TRANSIENT_SIGNAL_LIMITATION in packet.limitations


def test_transient_facts_preserve_valid_zero_score_and_requalify_history():
    context = {
        "schema": "kenn_mix_review_handoff.v1",
        "metrics": {"rms_dbfs": -18.0, "peak_dbfs": -0.1},
        "analysis_evidence": {"transient_preservation": _transient_summary()},
    }
    saved = deepcopy(context)

    packet = from_mix_review_context(context)
    assert packet is not None
    assert transient_preservation_has_activity(context["analysis_evidence"]["transient_preservation"])
    values = {fact.name: fact.value for fact in packet.facts}
    assert values["transient_preservation_score"] == 0.0
    assert values["transient_preservation_matched_event_count"] == 1
    assert context == saved

    (recovered,) = packets_from_history([history_turn(packet)])
    recovered_values = {fact.name: fact.value for fact in recovered.facts}
    assert recovered_values["transient_preservation_score"] == 0.0
    assert recovered_values["transient_preservation_profile"] == "clean"
    assert recovered_values["transient_preservation_matched_event_count"] == 1
    assert recovered.transient_preservation_provenance == packet.transient_preservation_provenance


def test_history_drops_cached_transient_scalars_without_activity_provenance():
    raw = {
        "schema": "kenn.evidence.v1",
        "source": "mix_review_upload",
        "facts": [
            {"name": "peak_dbfs", "value": -0.1, "unit": "dB", "confidence": "measured"},
            {"name": "transient_preservation_score", "value": 0.99, "unit": "ratio"},
            {"name": "transient_preservation_profile", "value": "compressed"},
            {"name": "transient_preservation_matched_event_count", "value": 12, "unit": "events"},
        ],
        "limitations": [],
    }

    (packet,) = packets_from_history([{"role": "user", "content": MARKER + json.dumps(raw)}])

    assert {fact.name for fact in packet.facts} == {"peak_dbfs"}
    assert packet.transient_preservation_provenance is None
    assert TRANSIENT_SIGNAL_LIMITATION in packet.limitations
    assert relevant_observations("Was punch lost?", [packet]) == []


def test_unqualified_transient_metrics_cannot_enter_upload_evidence():
    packet = from_mix_review_context({
        "schema": "kenn_mix_review_handoff.v1",
        "metrics": {
            "rms_dbfs": -18.0,
            "transient_preservation_score": 0.99,
            "transient_preservation_profile": "compressed",
            "matched_event_count": 12,
        },
    })

    assert packet is not None
    assert {fact.name for fact in packet.facts} == {"rms_dbfs"}
    assert TRANSIENT_SIGNAL_LIMITATION in packet.limitations


@pytest.mark.parametrize("side", ["mix", "reference"])
@pytest.mark.parametrize("rms", [None, True, "-18", float("nan"), float("inf"), 10**1000, -60.0, -80.0, -59.9])
def test_reference_facts_require_activity_in_both_uploaded_sources(side, rms):
    # Active own meters cannot qualify an older comparison with quiet or missing reference provenance.
    comparison = {
        "dynamics": {"mix": {"rms_dbfs": -18.0}, "reference": {"rms_dbfs": -20.0}},
        "largest_ltas_difference": {"center_hz": 315.0, "delta_db": 5.0},
        "pink_noise_reference": {"largest_deviation": {"center_hz": 80.0, "deviation_db": 6.0}},
        "lufs_delta_db": 4.0,
    }
    comparison["dynamics"][side]["rms_dbfs"] = rms
    before = deepcopy(comparison)
    packet = from_mix_review_context({
        "schema": "kenn_mix_review_handoff.v1",
        "metrics": {"rms_dbfs": -18.0, "peak_dbfs": -0.1},
        "reference_comparison": comparison,
    })
    active = rms == -59.9
    assert reference_comparison_has_activity(comparison) is active
    names = {fact.name for fact in packet.facts}
    assert {"rms_dbfs", "peak_dbfs"} <= names
    assert ("reference_largest_ltas_delta_db" in names) is active
    assert ("pink_noise_largest_deviation_db" in names) is active
    if not active:
        assert any("Mix and reference RMS" in item for item in packet.limitations)
    assert comparison == before


@pytest.mark.parametrize("comparison", [None, {}, {"dynamics": None}, {"dynamics": {"mix": {"rms_dbfs": -18.0}}}])
def test_legacy_comparison_without_both_source_readings_cannot_qualify(comparison):
    assert not reference_comparison_has_activity(comparison)


def test_erb_visibility_preserves_zero_and_rebuilds_history_from_bounded_sources():
    # A real zero visibility must survive while cached contradictory scalars never win.
    summary = _erb_summary()
    packet = from_mix_review_context({"schema": "kenn_mix_review_handoff.v1", "metrics": {"rms_dbfs": -18.0}, "analysis_evidence": {"stem_masking": summary}})
    assert packet is not None and stem_masking_has_activity(summary)
    assert packet.erb_masking_provenance == summary
    payload = packet.payload()
    payload["facts"].append({"name": "stem_masking_lowest_visibility", "value": 0.99})
    payload["limitations"] = []
    recovered, = packets_from_history([{"content": MARKER + json.dumps(payload)}])
    assert [fact.value for fact in recovered.facts if fact.name == "stem_masking_lowest_visibility"] == [0.0]
    assert recovered.erb_masking_provenance == summary
    assert ERB_PREVIEW_LIMITATION in packet.limitations
    assert ERB_PREVIEW_LIMITATION in recovered.limitations
    assert "relative ERB preview visibility" in " ".join(relevant_observations("bass masking", [recovered]))
    payload["erb_masking_provenance"]["activity"]["pairs"][0]["stems"][0] = "altered"
    assert packet.erb_masking_provenance == summary


@pytest.mark.parametrize("path,value", [
    (("activity",), None), (("activity", "schema"), "wrong"),
    (("activity", "active_floor_dbfs"), -80.0), (("activity", "frame_size_samples"), 2048),
    (("activity", "sources", 0, "active_frame_count"), 0),
    (("activity", "sources", 0, "active_frame_count"), True),
    (("activity", "sources", 0, "frame_count"), 17),
    (("activity", "sources", 0, "name"), "Kick"),
    (("activity", "sources", 0, "name"), " Bass"),
    (("activity", "sources", 0, "sample_rate"), 48000),
    (("activity", "sources", 0, "sample_rate"), float("nan")),
    (("activity", "sources", 0, "sample_rate"), True),
    (("activity", "sources", 0, "sample_rate"), 10**1000),
    (("activity", "pairs"), []),
    (("activity", "pairs", 0, "simultaneously_active_frame_count"), 0),
    (("activity", "pairs", 0, "simultaneously_active_frame_count"), 9),
    (("activity", "pairs", 0, "simultaneously_active_frame_count"), True),
    (("activity", "pairs", 0, "stems"), ["Bass", "Bass"]),
    (("lowest_visibility",), float("inf")), (("lowest_visibility",), float("nan")),
    (("lowest_visibility",), -0.1), (("lowest_visibility",), 1.1),
    (("lowest_visibility",), True), (("lowest_visibility",), 10**1000),
    (("lowest_visibility_stem",), "Unmeasured"), (("stem_count",), 3), (("stem_count",), True),
])
def test_erb_visibility_requires_real_joint_activity_on_input_and_history(path, value):
    # Quiet, synthetic, aliased or malformed previews used to retain normalized visibility.
    summary = _erb_summary()
    target = summary
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    assert qualified_stem_masking_summary(summary) is None
    packet = from_mix_review_context({"schema": "kenn_mix_review_handoff.v1", "metrics": {"rms_dbfs": -18.0, "peak_dbfs": -1.0}, "analysis_evidence": {"stem_masking": summary, "transient_preservation": _transient_summary()}})
    assert packet is not None
    assert not any(fact.name.startswith("stem_masking_") for fact in packet.facts)
    assert STEM_MASKING_SIGNAL_LIMITATION in packet.limitations
    raw = packet.payload()
    raw["erb_masking_provenance"] = summary
    raw["facts"].append({"name": "stem_masking_lowest_visibility", "value": 0.99})
    recovered, = packets_from_history([{"content": MARKER + json.dumps(raw)}])
    assert not any(fact.name.startswith("stem_masking_") for fact in recovered.facts)
    assert {fact.name for fact in recovered.facts} >= {"rms_dbfs", "peak_dbfs", "transient_preservation_score"}
    assert STEM_MASKING_SIGNAL_LIMITATION in recovered.limitations


def test_erb_legacy_scalars_and_metric_aliases_cannot_bypass_source_proof():
    # Older receipts and flattened metric aliases cannot acquire measured status.
    aliases = {"stem_masking_lowest_visibility": 0.9, "overall_visibility": 0.9, "lowest_visibility": 0.9, "stem_count": 2}
    packet = from_mix_review_context({"schema": "kenn_mix_review_handoff.v1", "metrics": {"rms_dbfs": -18.0, **aliases}, "analysis_evidence": {"stem_masking": {"lowest_visibility": 0.9, "lowest_visibility_stem": "Bass"}}})
    assert packet is not None and {fact.name for fact in packet.facts} == {"rms_dbfs"}
    raw = {"schema": "kenn.evidence.v1", "source": "mix_review_upload", "facts": [{"name": name, "value": value} for name, value in aliases.items()] + [{"name": "peak_dbfs", "value": -1.0}], "limitations": []}
    recovered, = packets_from_history([{"content": MARKER + json.dumps(raw)}])
    assert {fact.name for fact in recovered.facts} == {"peak_dbfs"}
    assert STEM_MASKING_SIGNAL_LIMITATION in recovered.limitations


def test_erb_visibility_isolates_unpaired_quiet_preview_sources():
    # A quiet extra stem cannot erase a real pair or become the measured minimum.
    summary = _erb_summary()
    summary["activity"]["sources"].append({"name": "Quiet", "sample_rate": 44100, "frame_count": 16, "active_frame_count": 0})
    assert qualified_stem_masking_summary(summary) == summary
    summary["lowest_visibility_stem"] = "Quiet"
    assert qualified_stem_masking_summary(summary) is None
