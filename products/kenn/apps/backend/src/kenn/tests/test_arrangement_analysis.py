from __future__ import annotations

from kenn.core.arrangement_analysis import SCHEMA, analyze_arrangement_context
from kenn.core.session_context import build_session_context


def _context() -> dict:
    return build_session_context(
        session_id="arrangement-1",
        snapshot={
            "status": "connected",
            "tracks": [
                {"index": 0, "name": "Kick", "type": "audio", "clip_slots": [
                    {"index": 0, "name": "Kick Verse", "has_clip": True},
                    {"index": 1, "name": "Kick Drop", "has_clip": True},
                    {"index": 2, "name": "Kick Drop", "has_clip": True},
                ], "arrangement_clips": [{"index": 0, "name": "Kick Timeline", "start_time_beats": 1.0, "length_beats": 64.0}]},
                {"index": 1, "name": "Bass", "type": "midi", "clip_slots": [
                    {"index": 1, "name": "Bass Drop", "has_clip": True},
                    {"index": 2, "name": "Bass Drop", "has_clip": True},
                ], "arrangement_clips": [{"index": 0, "name": "Bass Timeline", "start_time_beats": 33.0, "length_beats": 32.0}]},
            ],
            "scenes": [{"index": 0, "name": "Verse"}, {"index": 1, "name": "Drop"}, {"index": 2, "name": "Drop 2"}],
            "locators": [{"index": 0, "name": "Verse", "time_beats": 1.0}, {"index": 1, "name": "Drop", "time_beats": 33.0}],
        },
    )


def test_arrangement_analysis_reports_only_observed_topology() -> None:
    result = analyze_arrangement_context(_context())

    assert result["schema"] == SCHEMA
    assert result["status"] == "current"
    assert [item["active_clip_count"] for item in result["sections"]] == [1, 2, 2]
    assert result["locators"] == [
        {"index": 0, "name": "Verse", "time_beats": 1.0, "evidence_class": "observed_session_fact", "confidence": "observed_locator"},
        {"index": 1, "name": "Drop", "time_beats": 33.0, "evidence_class": "observed_session_fact", "confidence": "observed_locator"},
    ]
    assert result["timeline_sections"] == [
        {"locator_index": 0, "locator_name": "Verse", "start_time_beats": 1.0, "end_time_beats": 33.0,
         "active_arrangement_clip_count": 1, "active_track_indices": [0], "role_counts": {"kick": 1}, "relative_density": 0.5,
         "evidence_class": "observed_session_fact", "confidence": "observed_timeline_topology"},
        {"locator_index": 1, "locator_name": "Drop", "start_time_beats": 33.0, "end_time_beats": None,
         "active_arrangement_clip_count": 2, "active_track_indices": [0, 1], "role_counts": {"bass_synth": 1, "kick": 1}, "relative_density": 1.0,
         "evidence_class": "observed_session_fact", "confidence": "observed_timeline_topology"},
    ]
    assert result["timeline_transitions"] == [{
        "from_locator_index": 0, "to_locator_index": 1, "density_delta": 0.5,
        "candidate": "timeline_density_lift", "evidence_class": "observed_session_fact",
        "interpretation": "A timeline-density change worth auditioning around the observed locator.",
    }]
    assert result["transitions"][0]["candidate"] == "density_lift"
    assert {item["clip_name"] for item in result["repetition_candidates"]} == {"Kick Drop", "Bass Drop"}
    lift = next(item for item in result["suggestions"] if "density lift" in item["title"])
    assert "If Drop is meant to feel like an escalation" in lift["prompt"]
    timeline_lift = next(item for item in result["suggestions"] if "timeline density lift" in item["title"])
    assert "At the observed Drop locator" in timeline_lift["prompt"]
    repeat = next(item for item in result["suggestions"] if item["title"] == "Check whether Kick Drop should vary")
    assert "If that repetition is intentional, leave it" in repeat["prompt"]
    assert all(item["live_mutation_authorized"] is False for item in result["suggestions"])
    assert result["advisory_only"] is True
    assert result["mutation_authorized"] is False
    assert any("does not measure loudness" in item for item in result["limitations"])


def test_arrangement_analysis_fails_closed_for_stale_context() -> None:
    context = _context()
    context["observed_at"] -= 301
    result = analyze_arrangement_context(context)

    assert result["status"] == "unavailable"
    assert result["sections"] == []
    assert result["suggestions"] == []
    assert result["mutation_authorized"] is False


def test_arrangement_analysis_keeps_observed_locators_when_session_view_is_empty() -> None:
    context = build_session_context(snapshot={
        "status": "connected", "scenes": [],
        "tracks": [
            {"index": 0, "name": "Kick", "arrangement_clips": [
                {"index": 0, "name": "Kick Intro", "start_time_beats": 1.0, "length_beats": 64.0},
            ]},
            {"index": 1, "name": "Bass", "arrangement_clips": [
                {"index": 0, "name": "Bass Drop", "start_time_beats": 33.0, "length_beats": 32.0},
            ]},
        ],
        "locators": [
            {"index": 0, "name": "Intro", "time_beats": 1.0},
            {"index": 1, "name": "Drop", "time_beats": 33.0},
        ],
    })
    result = analyze_arrangement_context(context)

    assert result["status"] == "current"
    assert result["sections"] == []
    assert result["locators"][0]["name"] == "Intro"
    assert result["timeline_transitions"][0]["candidate"] == "timeline_density_lift"
    assert result["suggestions"][0]["live_mutation_authorized"] is False
    assert "observed Drop locator" in result["suggestions"][0]["prompt"]
    assert any("No Live scenes" in item for item in result["limitations"])
