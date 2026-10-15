from __future__ import annotations

from copy import deepcopy

import pytest

from kenn.core.evidence import (
    from_ableton_session,
    from_audio_classification_context,
    from_mix_review_context,
    from_plugin_context,
    live_context_has_activity,
    uploaded_metrics_have_activity,
    plugin_context_for_advice,
    from_realtime_mix_comparison,
    from_stem_masking_context,
    relevant_observations,
)
from kenn.core.realtime_mix_comparison import build_realtime_mix_comparison


def test_stem_masking_evidence_preserves_proxy_limits() -> None:
    packet = from_stem_masking_context({
        "schema": "kenn.mix_review_masking_analysis.v1",
        "ok": True,
        "evidence": {
            "schema": "kenn.evidence.v1",
            "source": "stem_masking_analysis",
            "facts": [{
                "name": "masking_highest_competing_frame_fraction",
                "value": 0.454,
                "unit": "ratio",
                "source": "stem_masking_analysis",
                "confidence": "measured_proxy",
            }],
            "limitations": ["Not a perceptual masking model."],
        },
    })
    assert packet is not None
    assert packet.source == "stem_masking_analysis"
    assert packet.facts[0].value == 0.454
    assert "perceptual" in packet.limitations[0]


def test_stem_masking_evidence_generates_bounded_follow_up_observation() -> None:
    packet = from_stem_masking_context({
        "schema": "kenn.mix_review_masking_analysis.v1",
        "ok": True,
        "evidence": {
            "schema": "kenn.evidence.v1",
            "source": "stem_masking_analysis",
            "facts": [
                {"name": "masking_candidate_count", "value": 2, "unit": "candidates"},
                {"name": "masking_highest_competing_frame_fraction", "value": 0.454, "unit": "ratio"},
                {"name": "masking_highest_pair", "value": "Bass + Piano"},
                {"name": "masking_highest_band", "value": "bass"},
            ],
            "limitations": ["Not a perceptual masking model."],
        },
    })

    assert packet is not None
    observations = relevant_observations("what is competing in the low end?", [packet])
    assert any("Bass + Piano" in item and "45.4%" in item for item in observations)
    assert any("not proof of audible masking" in item for item in observations)


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
        "reference_comparison": {
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
        "reference_comparison": {
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
            "reference_comparison": {
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
            "transient_preservation": {"score": 0.9, "profile": "compressed"},
            "stem_masking": {"lowest_visibility": 0.1, "lowest_visibility_stem": "Bass"},
            "low_end_stems": [{"name": "Bass"}],
        },
        "reference_comparison": {
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
