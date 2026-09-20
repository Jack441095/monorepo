"""Section dynamics stage: tension arc and default-form contrast."""

from __future__ import annotations

from composition.section_planner.section_dynamics_stage import (
    LIGHT_COUNTERLINE_FLOOR_EMOTIONS,
    RICH_COUNTER_EMOTIONS,
    SPARSE_COUNTER_EMOTIONS,
    apply_default_form_contrast_polish,
    apply_final_tension_arc_dynamics,
    resolve_dynamics_emotion_name,
)


def test_resolve_dynamics_prefers_song_primary():
    assert resolve_dynamics_emotion_name(section_emotion_name="joy", song_primary_emotion_name="grief") == "grief"


def test_fall_arc_lowers_chorus_section_dynamic():
    curve = {"section_dynamic": 1.0, "melody_vel_scale": 1.0}
    result = apply_final_tension_arc_dynamics(
        curve,
        role="chorus",
        section_emotion_name="grief",
        song_primary_emotion_name="grief",
        blend=1.0,
    )
    assert result.tension_arc == "fall"
    assert float(curve["section_dynamic"]) < 0.92


def test_spike_arc_raises_chorus_section_dynamic():
    curve = {"section_dynamic": 1.0, "melody_vel_scale": 1.0}
    result = apply_final_tension_arc_dynamics(
        curve,
        role="chorus",
        section_emotion_name="excitement",
        blend=1.0,
    )
    assert result.tension_arc == "spike"
    assert float(curve["section_dynamic"]) > 1.08


def test_default_form_contrast_sets_section_contrast_strength():
    curve = {"section_dynamic": 1.0}
    apply_default_form_contrast_polish(
        curve,
        emotion_name="neutral",
        role="chorus",
        role_occurrence=1,
        strength=1.0,
    )
    assert float(curve.get("section_contrast_strength", 0.0)) >= 1.1


def test_chorus_counter_cap_for_sparse_emotions():
    curve = {"counter_melody_enabled_mult": 0.22}
    apply_default_form_contrast_polish(
        curve,
        emotion_name="anger",
        role="chorus",
        role_occurrence=1,
        strength=1.0,
    )
    assert float(curve["counter_melody_enabled_mult"]) <= 0.08


def test_chorus_counter_floor_for_rich_emotions():
    curve = {"counter_melody_enabled_mult": 0.12}
    apply_default_form_contrast_polish(
        curve,
        emotion_name="grief",
        role="chorus",
        role_occurrence=1,
        strength=1.0,
    )
    assert float(curve["counter_melody_enabled_mult"]) >= 0.26


def test_sparse_and_rich_sets_are_disjoint():
    assert not SPARSE_COUNTER_EMOTIONS.intersection(RICH_COUNTER_EMOTIONS)


def test_light_counterline_floor_emotions_are_sparse_not_rich():
    assert LIGHT_COUNTERLINE_FLOOR_EMOTIONS.issubset(SPARSE_COUNTER_EMOTIONS)
    assert not LIGHT_COUNTERLINE_FLOOR_EMOTIONS.intersection(RICH_COUNTER_EMOTIONS)
