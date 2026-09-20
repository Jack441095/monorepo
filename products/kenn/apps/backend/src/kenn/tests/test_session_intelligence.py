from __future__ import annotations

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
        plugin_frames=[{"schema": "kenn.live_mix_context.v1", "peak_dbfs": -1.2, "stereo_width": 0.7}],
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
