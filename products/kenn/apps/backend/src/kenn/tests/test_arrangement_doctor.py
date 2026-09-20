"""Unit tests for KENN Autonomous Arrangement Doctor & Energy Profiler (V6.0)."""

from __future__ import annotations

import pytest
from kenn.core.arrangement_doctor import ArrangementDoctor, get_arrangement_doctor


def test_section_segmentation_and_energy():
    """Validates timeline section segmentation, energy indices, and drop contrast."""
    doctor = ArrangementDoctor()
    tracks = [
        {"name": "Kick", "volume": 0.9},
        {"name": "Sub Bass", "volume": 0.85},
        {"name": "Lead Synth", "volume": 0.8},
        {"name": "Hihats", "volume": 0.7},
    ]

    report = doctor.analyze_timeline(tracks=tracks, total_bars=64)

    assert report.total_bars == 64
    assert len(report.sections) >= 5
    assert 0.0 <= report.mean_energy <= 1.0

    # Ensure sections follow musical progression
    section_types = [s.section_type for s in report.sections]
    assert "INTRO" in section_types
    assert "VERSE" in section_types
    assert "BUILDUP" in section_types
    assert "DROP_CHORUS" in section_types
    assert "OUTRO" in section_types

    # Drop contrast delta must be positive (>= +0.25)
    assert report.drop_contrast_delta >= 0.25


def test_buildup_hpf_sweep_recipe():
    """Asserts that buildup sweep rises from 30 Hz to 250 Hz on Eq8."""
    doctor = get_arrangement_doctor()
    report = doctor.analyze_timeline()

    sweep = next((r for r in report.transition_recipes if r.get("type") == "automation_sweep"), None)
    assert sweep is not None
    assert sweep["target"] == "Master"
    assert sweep["device_type"] == "Eq8"
    assert sweep["filter_type"] == "HighPass18"
    assert sweep["start_value_hz"] == 30.0
    assert sweep["end_value_hz"] == 250.0


def test_pre_drop_silent_cutout():
    """Asserts 1-beat silent cutout recipe preceding drop beat 1."""
    doctor = ArrangementDoctor()
    report = doctor.analyze_timeline()

    cutout = next((r for r in report.transition_recipes if r.get("type") == "pre_drop_cutout"), None)
    assert cutout is not None
    assert cutout["action"] == "mute_track_interval"
    assert cutout["target"] == "Rhythm_and_Bass"
    assert cutout["duration_beats"] >= 1.0
