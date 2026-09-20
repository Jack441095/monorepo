"""Tests for the capability-aware Ableton project-analysis foundation."""

from kenn.project_analysis import analyze_arrangement, analyze_plugin_optimizer, analyze_project_doctor, analyze_project_manager, creative_suggestions_for_selected_track, detect_project_analysis_request, format_analysis_answer, normalize_session, project_manager_report, recommendations_from_mix_review


def test_normalize_session_preserves_only_bridge_supported_data():
    project = normalize_session({
        "status": "connected", "tempo": 128, "is_playing": True,
        "tracks": [{"index": 4, "name": "Kick", "volume": 0.7, "pan": 0,
                    "devices": [{"index": 0, "name": "EQ Eight"}]}],
        "scenes": [{"index": 0, "name": "Intro"}],
        "return_tracks": [{"index": 0, "name": "Verb", "volume": 0.5, "devices": []}],
        "master_track": {"name": "Master", "volume": 0.8, "devices": [{"name": "Limiter"}]},
    })
    assert project.tracks[0].index == 4
    assert project.tracks[0].inferred_role == "drums"
    assert project.tracks[0].devices[0].name == "EQ Eight"
    assert "routing" in project.unavailable_capabilities
    assert "track_names" in project.available_capabilities
    assert project.return_tracks[0].name == "Verb"
    assert project.master_track is not None and project.master_track.devices[0].name == "Limiter"


def test_project_manager_finds_generic_and_duplicate_names_without_claiming_empty_tracks():
    project = normalize_session({
        "status": "connected",
        "tracks": [
            {"index": 0, "name": "Audio 1", "devices": []},
            {"index": 1, "name": "Kick", "devices": []},
            {"index": 2, "name": "kick", "devices": []},
        ],
    })
    recommendations = analyze_project_manager(project)
    titles = [item.title for item in recommendations]
    assert "Name Audio 1" in titles
    assert any("duplicate track names" in title.lower() for title in titles)
    assert not any("empty" in title.lower() for title in titles)
    assert all(not item.canAutoFix and item.requiresConfirmation for item in recommendations)


def test_project_manager_marks_name_similarity_as_non_audio_evidence():
    project = normalize_session({"status": "connected", "tracks": [
        {"index": 0, "name": "Kick Main"}, {"index": 1, "name": "Kick Layer"},
    ]})
    recommendations = analyze_project_manager(project)
    similar = next(item for item in recommendations if "similarly named" in item.title)
    assert "cannot compare their audio or MIDI content" in similar.reason


def test_report_makes_offline_and_missing_data_explicit():
    report = project_manager_report({"status": "offline", "tracks": []})
    assert report["ok"] is False
    assert report["summary"]["track_count"] == 0
    assert "audio_spectrum" in report["unavailable_data"]


def test_project_doctor_uses_meter_as_an_observation_not_a_clipping_claim():
    project = normalize_session({"status": "connected", "tracks": [
        {"index": 0, "name": "Mastering Print", "soloed": True, "output_meter_level": 0.99},
    ]})
    recommendations = analyze_project_doctor(project)
    assert {item.category for item in recommendations} == {"project_health", "mix_health"}
    assert any("not proof of clipping" in item.reason for item in recommendations)


def test_project_doctor_checks_master_meter_without_claiming_true_peak():
    project = normalize_session({"status": "connected", "master_track": {"name": "Master", "output_meter_level": 0.99}})
    recommendations = analyze_project_doctor(project)
    master = next(item for item in recommendations if item.title == "Check master headroom")
    assert "not proof of true-peak clipping" in master.reason


def test_plugin_optimizer_never_claims_cpu_from_device_names():
    project = normalize_session({"status": "connected", "tracks": [
        {"index": index, "name": f"Synth {index}", "devices": [{"name": "EQ Eight"}]}
        for index in range(4)
    ]})
    recommendations = analyze_plugin_optimizer(project)
    assert len(recommendations) == 1
    assert "CPU cost and latency are not available" in recommendations[0].reason


def test_live_project_questions_route_to_deterministic_analysis():
    assert detect_project_analysis_request("What's wrong with my mix?") is None
    assert detect_project_analysis_request("Clean up this project") == "project_manager"
    assert detect_project_analysis_request("Which plugins are using the most CPU?") == "plugin_optimizer"
    assert detect_project_analysis_request("Organise my drums") == "project_manager"
    assert detect_project_analysis_request("Is my low end balanced?") == "project_health"
    assert detect_project_analysis_request("How do I use EQ Eight?") is None


def test_arrangement_analysis_is_limited_to_session_view_structure():
    project = normalize_session({"status": "connected", "scenes": [
        {"index": 0, "name": "", "active_clip_count": 1},
        {"index": 1, "name": "Drop", "active_clip_count": 6},
    ]})
    recommendations = analyze_arrangement(project)
    assert len(recommendations) == 2
    assert all("not whether a section is good or bad" in item.reason or item.category == "arrangement" for item in recommendations)


def test_uploaded_mix_review_recommendations_keep_their_evidence_source():
    recommendations = recommendations_from_mix_review({
        "flags": [{"label": "Low dynamics", "detail": "Crest is low.", "severity": "medium", "confidence": "high"}],
        "reference_comparison": {"largest_spectral_difference": {"band": "low_mids", "delta_db": 2.5}},
    })
    assert len(recommendations) == 2
    assert recommendations[0].severity == "warning"
    assert "uploaded/rendered audio file" in recommendations[0].reason
    assert recommendations[1].category == "reference"
    assert "+2.5 dB" in recommendations[1].description


def test_creative_suggestions_require_and_scope_to_the_live_selected_track():
    project = normalize_session({"status": "connected", "selected_track_index": 1, "tracks": [
        {"index": 0, "name": "Kick"}, {"index": 1, "name": "Sub Bass"},
    ]})
    suggestions = creative_suggestions_for_selected_track(project)
    assert len(suggestions) == 3
    assert all(item.track_indices == (1,) and not item.canAutoFix for item in suggestions)
    assert detect_project_analysis_request("Make this more interesting") == "creative"


def test_clean_live_health_report_still_explains_audio_measurement_limit():
    report = {"status": "connected", "recommendations": [], "unavailable_data": ["audio_spectrum"]}
    answer = format_analysis_answer("project_health", report)
    assert "Low-end balance" in answer
    assert "uploaded/rendered audio analysis" in answer
