from __future__ import annotations

from copy import deepcopy

import pytest

from kenn.core.session_context import build_session_context
from kenn.core.session_intelligence import SCHEMA, build_session_intelligence, explanation_sections, retrieval_sources_from_cache


def _context() -> dict:
    return build_session_context(
        session_id="song-1",
        snapshot={
            "status": "connected",
            "tempo": 128.0,
            "tracks": [
                {"index": 0, "name": "Kick", "type": "audio", "devices": [], "output_meter_level": 0.82, "output_meter_right": 0.78},
                {"index": 1, "name": "Bass", "type": "midi", "devices": [], "arrangement_clips": [{"index": 0, "name": "Bass Verse", "start_time_beats": 1.0, "length_beats": 16.0}]},
            ],
            "scenes": [{"index": 0, "name": "Drop"}],
            "locators": [{"index": 0, "name": "Drop", "time_beats": 33.0}],
            "return_tracks": [],
        },
        plugin_frames=[{"schema": "kenn.live_mix_context.v1", "peak_dbfs": -1.2, "rms_dbfs": -18.0, "stereo_width": 0.7}],
    )


def test_session_intelligence_keeps_evidence_classes_and_write_boundary_separate() -> None:
    brief = build_session_intelligence(
        _context(),
        project_intent={"genre": "UK garage", "goal": "Make the drop hit harder", "references": ["Reference A"]},
        retrieval_sources=[
            {"source_id": "live12-manual-routing", "title": "Routing", "evidence_class": "official_ableton_manual"},
            {"source_id": "ignored", "evidence_class": "untrusted"},
        ],
        reference_comparison={
            "comparison_basis": "Each LTAS is normalised around 1 kHz.",
            "largest_ltas_difference": {"center_hz": 300.0, "delta_db": 5.0},
            "dynamics": {"mix": {"rms_dbfs": -15.0}, "reference": {"rms_dbfs": -16.0}},
        },
    )

    assert brief["schema"] == SCHEMA
    assert brief["status"] == "current"
    assert brief["snapshot"]["track_count"] == 2
    assert brief["track_roles"][0]["role"] == "kick"
    assert brief["track_roles"][0]["output_meter_level"] == 0.82
    assert brief["track_roles"][0]["meter_scope"] == "instantaneous_post_fader"
    assert brief["audio_evidence"][-1]["largest_difference"] == {"center_hz": 300.0, "delta_db": 5.0}
    assert brief["retrieval"] == [{"source_id": "live12-manual-routing", "evidence_class": "official_ableton_manual", "title": "Routing"}]
    assert brief["session_observations"]["source"] == "fresh_live_snapshot"
    assert brief["session_observations"]["locators"] == [{"index": 0, "name": "Drop", "time_beats": 33.0}]
    assert brief["session_observations"]["arrangement_clip_count"] == 1
    assert brief["session_observations"]["track_meter_observations"] == [{
        "track_index": 0,
        "track_name": "Kick",
        "output_meter_level": 0.82,
        "output_meter_right": 0.78,
        "scope": "instantaneous_post_fader",
        "advisory_only": True,
    }]
    assert brief["mutation_authorized"] is False
    assert "explicit confirmation" in brief["capability_state"]["write_prerequisites"]
    assert {section["kind"] for section in explanation_sections(brief)} >= {
        "observed_session_fact", "audio_measurement", "specialist_inference",
        "official_technical_reference", "producer_intent",
    }


def test_session_intelligence_surfaces_exact_selected_device_context() -> None:
    context = _context()
    context["transport"].update({
        "selected_track_index": 1,
        "selected_device_track_index": 1,
        "selected_device_index": 0,
        "selected_device_name": "EQ Eight",
    })
    context["tracks"][1]["devices"] = [{"index": 0, "name": "EQ Eight"}]

    brief = build_session_intelligence(context)

    assert brief["session_observations"]["selected_device"] == {
        "track_index": 1,
        "track_name": "Bass",
        "device_index": 0,
        "name": "EQ Eight",
    }
    assert brief["session_observations"]["present_devices"] == ["EQ Eight"]
    assert brief["snapshot"]["transport"]["selected_device_name"] == "EQ Eight"


def test_session_intelligence_fails_closed_for_stale_source_context() -> None:
    context = _context()
    context["observed_at"] -= 301
    brief = build_session_intelligence(context)

    assert brief["status"] == "unavailable"
    assert brief["snapshot"] == {}
    assert brief["track_roles"] == []
    assert brief["mutation_authorized"] is False
    assert any("stale" in error.lower() for error in brief["errors"])


def test_session_intelligence_does_not_expose_unbounded_retrieval_metadata() -> None:
    brief = build_session_intelligence(
        _context(),
        retrieval_sources=[
            {"source_id": "good", "evidence_class": "reference_document", "path": "/private/path", "chunk_text": "do not retain"},
        ],
    )

    assert brief["retrieval"] == [{"source_id": "good", "evidence_class": "reference_document"}]


def test_session_intelligence_preserves_live_observation_availability() -> None:
    context = _context()
    context["observation_capabilities"] = {
        "locators": True,
        "arrangement_clip_inventory": False,
        "routing": True,
    }
    context["snapshot_fingerprint"] = "sha256:" + "a" * 64
    brief = build_session_intelligence(context)

    assert brief["status"] == "current"
    assert brief["session_observations"]["observation_capabilities"] == {
        "locators": True,
        "arrangement_clip_inventory": False,
        "routing": True,
    }


def test_session_intelligence_surfaces_observed_group_membership() -> None:
    context = _context()
    context["tracks"][1].update({
        "is_grouped": True,
        "group_track_index": 0,
        "group_track_name": "Drums",
    })

    brief = build_session_intelligence(context)

    assert brief["session_observations"]["group_memberships"] == [{
        "track_index": 1,
        "track_name": "Bass",
        "group_track_index": 0,
        "group_track_name": "Drums",
        "evidence_class": "observed_session_fact",
        "confidence": "observed_group_membership",
    }]


def test_session_intelligence_surfaces_advisory_audio_classifier_evidence() -> None:
    digest = "sha256:" + "a" * 64
    classification = {
        "schema": "kenn.audio_classification.v1", "status": "completed", "audio_sha256": digest,
        "model_id": "slo-export-v1", "model_sha256": "sha256:" + "b" * 64,
        "label_map_sha256": "sha256:" + "c" * 64, "inference_version": "1",
        "audio_only": [{"label": "kick", "probability": 0.9}, {"label": "snare", "probability": 0.1}],
        "metadata_assisted": [{"label": "kick", "probability": 0.95}],
        "selected_label": "kick", "selected_source": "audio_only", "confidence_band": "high",
        "out_of_distribution": {"status": "in_distribution", "score": 0.1},
        "evidence_used": ["audio_only"], "latency_ms": 4, "limitations": ["advisory only"],
    }
    brief = build_session_intelligence(build_session_context(snapshot={"status": "connected", "tracks": []}, audio_classifications=[classification]))

    observed = brief["audio_classifications"][0]
    assert observed["selected_label"] == "kick"
    assert observed["audio_only"][0] == {"label": "kick", "probability": 0.9}
    assert observed["evidence_class"] == "specialist_inference"
    assert observed["advisory_only"] is True
    assert observed["live_mutation_authorized"] is False
    assert "quality" in observed["limitations"][0]
    assert "audio_classification" in {item["kind"] for item in explanation_sections(brief)}


def test_session_intelligence_includes_only_explicit_editable_project_memory() -> None:
    context = _context()
    context["producer_preferences"] = [{
        "schema": "kenn.producer_preference.v1", "key": "creative_direction", "value": "minimal and punchy",
        "source": "explicit_user_statement", "advisory_only": True,
    }]
    context["episodic_outcomes"] = [{
        "schema": "kenn.production_episode.v1", "episode_id": "episode-1", "verdict": "revise",
        "requested_changes": ["Less busy ending"], "advisory_only": True,
    }]
    brief = build_session_intelligence(context)

    assert brief["project_memory"]["scope"] == "session_scoped"
    assert brief["project_memory"]["explicit_preferences"] == [{
        "key": "creative_direction", "value": "minimal and punchy", "source": "explicit_user_statement",
    }]
    assert brief["project_memory"]["reviewed_outcomes"][0]["verdict"] == "revise"
    assert "explicit_project_memory" in {item["kind"] for item in explanation_sections(brief)}


def test_session_intelligence_uses_reference_measurement_from_trusted_mix_receipt() -> None:
    context = build_session_context(
        snapshot={"status": "connected", "tracks": []},
        mix_review_receipts=[{
            "schema": "kenn.mix_review.reference_comparison.v1",
            "status": "completed",
            "reference_comparison": {
                "comparison_basis": "Each LTAS is normalised around 1 kHz.",
                "largest_ltas_difference": {"center_hz": 300.0, "delta_db": 5.0},
                "dynamics": {"mix": {"rms_dbfs": -15.0}, "reference": {"rms_dbfs": -16.0}},
                "pink_noise_reference": {
                    "status": "complete",
                    "curve": "-3 dB per octave pink-noise-style spectral baseline",
                    "anchor_frequency_hz": 957.0,
                    "largest_deviation": {"center_hz": 296.0, "deviation_db": 5.1},
                },
            },
        }],
    )
    brief = build_session_intelligence(context)

    reference = next(item for item in brief["audio_evidence"] if item["kind"] == "uploaded_reference_ltas")
    assert reference["largest_difference"] == {"center_hz": 300.0, "delta_db": 5.0}
    assert "not an automatic" in reference["limitations"][1]
    pink = next(item for item in brief["audio_evidence"] if item["kind"] == "pink_noise_shape")
    assert pink["largest_deviation"] == {"center_hz": 296.0, "deviation_db": 5.1}
    coach = brief["mixdown_coach"]
    assert coach["status"] == "ready"
    assert coach["listening_checks"][0]["kind"] == "pink_noise_shape"
    assert coach["listening_checks"][0]["frequency_hz"] == 296.0
    assert coach["listening_checks"][1]["frequency_hz"] == 300.0
    assert coach["live_target_inference_allowed"] is False
    assert "measurement_guided_listening" in {item["kind"] for item in explanation_sections(brief)}


def test_session_intelligence_does_not_create_mixdown_coach_from_caller_data_alone() -> None:
    brief = build_session_intelligence(
        _context(),
        reference_comparison={
            "largest_ltas_difference": {"center_hz": 300.0, "delta_db": 5.0},
            "comparison_basis": "Untrusted caller data",
        },
    )

    assert brief["mixdown_coach"] is None
    assert "measurement_guided_listening" not in {item["kind"] for item in explanation_sections(brief)}


@pytest.mark.parametrize("quiet_side", ["mix", "reference"])
def test_session_intelligence_withholds_unqualified_uploaded_comparison(quiet_side) -> None:
    comparison = {
        "comparison_basis": "uploaded whole-file comparison",
        "dynamics": {
            "mix": {"rms_dbfs": -15.0},
            "reference": {"rms_dbfs": -16.0},
        },
        "largest_ltas_difference": {"center_hz": 300.0, "delta_db": 5.0},
        "pink_noise_reference": {
            "curve": "pink-noise-style baseline",
            "anchor_frequency_hz": 1000.0,
            "largest_deviation": {"center_hz": 300.0, "deviation_db": 5.0},
        },
    }
    comparison["dynamics"][quiet_side]["rms_dbfs"] = -60.0
    context = _context()
    context["measurements"] = [{
        "kind": "mix_review",
        "schema": "kenn.mix_review.reference_comparison.v1",
        "status": "completed",
        "reference_comparison": comparison,
    }]
    saved = deepcopy(context)

    brief = build_session_intelligence(context, reference_comparison=comparison)

    assert brief["audio_evidence"] == []
    assert brief["mixdown_coach"] is None
    assert brief["realtime_mix_comparison"] is None
    assert context == saved


@pytest.mark.parametrize("rms", ["missing", None, True, float("nan"), float("inf"), -60.0])
def test_session_intelligence_withholds_legacy_uploaded_metrics_without_qualified_rms(rms) -> None:
    metrics = {"rms_dbfs": rms, "true_peak_dbtp": -0.1, "integrated_lufs": -8.0}
    if rms == "missing":
        metrics.pop("rms_dbfs")
    context = _context()
    context["measurements"] = [{"kind": "mix_review", "metrics": metrics}]

    brief = build_session_intelligence(context)

    assert brief["audio_evidence"] == []


def test_session_intelligence_keeps_uploaded_comparison_when_both_renders_clear_floor() -> None:
    comparison = {
        "comparison_basis": "uploaded whole-file comparison",
        "dynamics": {"mix": {"rms_dbfs": -59.9}, "reference": {"rms_dbfs": -40.0}},
        "largest_ltas_difference": {"center_hz": 300.0, "delta_db": 5.0},
    }
    context = _context()
    context["measurements"] = [{
        "schema": "kenn.mix_review.reference_comparison.v1",
        "status": "completed",
        "reference_comparison": comparison,
    }]

    brief = build_session_intelligence(context)

    assert brief["audio_evidence"][0]["largest_difference"] == {"center_hz": 300.0, "delta_db": 5.0}
    assert brief["mixdown_coach"]["status"] == "ready"


def test_ordinary_review_comparison_requires_its_own_upload_to_clear_floor() -> None:
    comparison = {
        "comparison_basis": "uploaded whole-file comparison",
        "dynamics": {"mix": {"rms_dbfs": -15.0}, "reference": {"rms_dbfs": -16.0}},
        "largest_ltas_difference": {"center_hz": 300.0, "delta_db": 5.0},
    }
    context = _context()
    context["measurements"] = [{
        "kind": "mix_review",
        "schema": "kenn.mix_review.local_review.v1",
        "metrics": {"rms_dbfs": -60.0, "peak_dbfs": -0.1},
        "reference_comparison": comparison,
    }]

    brief = build_session_intelligence(context)

    assert brief["audio_evidence"] == []
    assert brief["mixdown_coach"] is None


def test_legacy_local_review_schema_without_kind_still_qualifies_its_metrics() -> None:
    context = _context()
    context["measurements"] = [{
        "schema": "kenn.mix_review.local_review.v1",
        "metrics": {"rms_dbfs": None, "peak_dbfs": -0.1, "integrated_lufs": -8.0},
    }]

    brief = build_session_intelligence(context)

    assert brief["audio_evidence"] == []


def test_session_intelligence_preserves_realtime_comparison_abstention_semantics() -> None:
    comparison = {
        "schema": "kenn.realtime_mix_comparison.v1",
        "comparison_available": False,
        "comparisons": [],
        "pink_noise_shape": None,
        "limitations": ["Live RMS is missing or quiet; comparison is withheld."],
    }

    brief = build_session_intelligence(_context(), reference_comparison=comparison)

    assert brief["realtime_mix_comparison"] == comparison
    assert {item["kind"] for item in brief["audio_evidence"]} == {"plugin_feature_frame"}


def test_retrieval_provenance_cache_keeps_only_source_labels_and_classes() -> None:
    sources = retrieval_sources_from_cache([
        (0.99, {
            "source": "Live 12 Manual.pdf",
            "title": "Routing",
            "kind": "pdf",
            "evidence_class": "official_ableton_manual",
            "text": "This must not leave the cache boundary.",
            "path": "/private/manual.pdf",
        }),
        (0.8, {"source": "mixing.md", "kind": "note", "text": "Nope"}),
        (0.2, {"source": "ignored", "evidence_class": "untrusted", "text": "Nope"}),
    ])

    assert sources == [
        {"source_id": "Live 12 Manual.pdf", "evidence_class": "official_ableton_manual", "title": "Routing"},
        {"source_id": "mixing.md", "evidence_class": "curated_kenn_note"},
    ]


@pytest.mark.parametrize("rms", ["missing", None, True, float("nan"), float("inf"), -float("inf"), 10 ** 1000, -100.0, -80.0])
def test_intelligence_withholds_quiet_signal_evidence_from_older_canonical_context(rms) -> None:
    # Persisted contexts built before the ingress gate still contain both quiet meters and apparently valid pink observations.
    context = _context()
    measurement = {
        "kind": "plugin_feature_frame", "schema": "kenn.live_mix_context.v1",
        "metrics": {"peak_dbfs": -0.1, "rms_dbfs": rms, "stereo_correlation": -0.9},
        "pink_noise_reference": {"largest_deviation": {"center_hz": 315.0, "deviation_db": 5.0}},
    }
    if rms == "missing":
        measurement["metrics"].pop("rms_dbfs")
    context["measurements"] = [measurement]
    saved = deepcopy(context)

    brief = build_session_intelligence(context)

    assert brief["status"] == "current"
    assert brief["audio_evidence"] == []
    assert brief["mixdown_coach"] is None
    assert brief["snapshot"]["track_count"] == 2
    assert brief["track_roles"][0]["role"] == "kick"
    assert brief["mutation_authorized"] is False
    assert context == saved


def test_intelligence_keeps_signal_evidence_just_above_live_activity_floor() -> None:
    context = _context()
    context["measurements"] = [{
        "kind": "plugin_feature_frame", "schema": "kenn.live_mix_context.v1",
        "metrics": {"peak_dbfs": -0.1, "rms_dbfs": -79.9},
        "pink_noise_reference": {"largest_deviation": {"center_hz": 315.0, "deviation_db": 5.0}},
    }]

    brief = build_session_intelligence(context)

    assert brief["audio_evidence"][0]["metrics"] == {"peak_dbfs": -0.1, "rms_dbfs": -79.9}
    assert brief["audio_evidence"][1]["kind"] == "pink_noise_shape"


def _optional_audio_receipt():
    return {
        "schema": "kenn.mix_review.local_review.v1", "status": "completed",
        "metrics": {"rms_dbfs": -15.0, "peak_dbfs": -1.0, "low_end_share": 0.0,
                    "stem_masking_lowest_visibility": 0.8, "transient_preservation_score": 0.8},
        "findings": ["Cached mixed optional analysis"], "action_plan": ["Cached optional repair"],
        "analysis_evidence": {
            "stem_masking": {
                "stem_count": 2, "lowest_visibility": 0.0, "lowest_visibility_stem": "Bass",
                "activity": {"schema": "kenn.erb_masking.activity.v1", "active_floor_dbfs": -60.0,
                             "frame_size_samples": 4096,
                             "sources": [{"name": name, "sample_rate": 44100, "frame_count": 2, "active_frame_count": 2} for name in ("Bass", "Kick")],
                             "pairs": [{"stems": ["Bass", "Kick"], "simultaneously_active_frame_count": 1}]},
            },
            "transient_preservation": {
                "score": 0.0, "matched_event_count": 1, "profile": "clean",
                "activity": {"schema": "kenn.transient_preservation.activity.v1", "pre_rms_dbfs": -18.0, "post_rms_dbfs": -20.0},
            },
            "low_end_stems": [{"name": "Bass", "low_end_share": 0.0, "activity": {
                "schema": "kenn.low_end_stem.activity.v1", "active_floor_dbfs": -60.0,
                "source_rms_dbfs": -18.0, "window_rms_dbfs": -20.0, "sample_rate": 44100,
                "analysis_sample_count": 8192, "frame_size_samples": 4096, "window_start_sample": 2048,
            }}],
        },
        "reference_comparison": {
            "dynamics": {"mix": {"rms_dbfs": -15.0}, "reference": {"rms_dbfs": -16.0}},
            "largest_ltas_difference": {"center_hz": 300.0, "delta_db": 0.0},
        },
    }


@pytest.mark.parametrize("bad_section", [None, "stem_masking", "transient_preservation", "low_end_stems"])
@pytest.mark.parametrize("edited_context", [False, True])
def test_receipt_to_session_brief_requalifies_optional_audio_independently(bad_section, edited_context):
    # An active whole mix cannot qualify legacy stem scalars or a quiet optional render.
    receipt = _optional_audio_receipt()
    if bad_section:
        receipt["analysis_evidence"][bad_section] = [] if bad_section == "low_end_stems" else {}
    before = deepcopy(receipt)
    context = build_session_context(mix_review_receipts=[receipt])
    if edited_context:
        context["measurements"] = [{"kind": "mix_review", **receipt}]
    brief = build_session_intelligence(context)
    measured = next(item for item in brief["audio_evidence"] if item["kind"] == "mix_review")
    assert measured["metrics"]["rms_dbfs"] == -15.0
    assert measured["metrics"]["low_end_share"] == 0.0
    for section, fact in (("stem_masking", "stem_masking_lowest_visibility"), ("transient_preservation", "transient_preservation_score")):
        if section == bad_section:
            assert fact not in measured["metrics"]
        else:
            assert measured["metrics"][fact] == 0.0
    assert ("low_end_measured_stems" in measured["metrics"]) is False  # Names remain in bounded proof, not numeric metrics.
    if bad_section != "low_end_stems":
        assert measured["analysis_evidence"]["low_end_stems"][0]["low_end_share"] == 0.0
        assert any("own centered FFT-window" in item for item in measured["limitations"])
    if bad_section != "stem_masking":
        assert any("calibrated" in item for item in measured["limitations"])
    assert any(item["kind"] == "uploaded_reference_ltas" and item["largest_difference"]["delta_db"] == 0.0 for item in brief["audio_evidence"])
    if bad_section:
        assert any("withheld" in item for item in measured["limitations"])
        if not edited_context:
            assert context["measurements"][0]["findings"] == []
            assert context["measurements"][0]["action_plan"] == []
    assert receipt == before


@pytest.mark.parametrize("metric", ["stem_masking_lowest_visibility", "overall_visibility", "stem_count", "transient_preservation_score", "matched_event_count", "low_end_overlap"])
def test_legacy_receipt_metric_aliases_cannot_become_session_measurements(metric):
    receipt = {"schema": "kenn.mix_review.local_review.v1", "status": "completed",
               "metrics": {"rms_dbfs": -15.0, metric: 0.8},
               "findings": ["Cached optional claim"], "action_plan": ["Cached optional repair"]}
    context = build_session_context(mix_review_receipts=[receipt])
    measurement = context["measurements"][0]
    assert measurement["metrics"] == {"rms_dbfs": -15.0}
    assert measurement["findings"] == measurement["action_plan"] == []
    measured = build_session_intelligence(context)["audio_evidence"][0]
    assert measured["metrics"] == {"rms_dbfs": -15.0}
    assert any("withheld" in item for item in measured["limitations"])
