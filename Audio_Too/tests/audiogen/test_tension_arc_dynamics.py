"""Tension-arc role dynamics differ across anchor templates."""

from __future__ import annotations

from data.tension_arc_dynamics import (
    apply_tension_arc_to_arrangement_curve,
    apply_tension_arc_to_professionalizer_velocities,
    tension_arc_for_emotion,
    tension_arc_role_velocity_table,
)


def test_tension_arc_tables_differ_by_template():
    flat = tension_arc_role_velocity_table("flat")
    fall = tension_arc_role_velocity_table("fall")
    spike = tension_arc_role_velocity_table("spike")
    assert flat["chorus"] < spike["chorus"]
    assert fall["chorus"] < flat["chorus"]
    assert fall["intro"] > spike["intro"]


def test_grief_uses_fall_arc():
    assert tension_arc_for_emotion("grief") == "fall"


def test_excitement_uses_spike_arc():
    assert tension_arc_for_emotion("excitement") == "spike"


def test_arrangement_curve_blend_moves_section_dynamic():
    curve = {"section_dynamic": 1.0, "melody_vel_scale": 1.0}
    apply_tension_arc_to_arrangement_curve(curve, role="chorus", emotion_name="grief", blend=1.0)
    assert float(curve["section_dynamic"]) < 0.92
    curve2 = {"section_dynamic": 1.0, "melody_vel_scale": 1.0}
    apply_tension_arc_to_arrangement_curve(curve2, role="chorus", emotion_name="excitement", blend=1.0)
    assert float(curve2["section_dynamic"]) > 1.10


def test_audit_fall_arc_accepts_negative_intro_chorus_velocity():
    from scripts.batch_full_song_note_audit import _intro_chorus_velocity_arc_fit

    assert _intro_chorus_velocity_arc_fit(-4.0, "fall") >= 0.9
    assert _intro_chorus_velocity_arc_fit(3.5, "fall") >= 0.8
    assert _intro_chorus_velocity_arc_fit(30.0, "fall") < 0.55
    assert _intro_chorus_velocity_arc_fit(29.0, "flat") >= 0.7


def test_audit_spike_arc_prefers_large_lift():
    from scripts.batch_full_song_note_audit import _intro_chorus_velocity_arc_fit

    assert _intro_chorus_velocity_arc_fit(45.0, "spike") >= 0.95
    assert _intro_chorus_velocity_arc_fit(2.0, "spike") < 0.55


def test_professionalizer_velocities_follow_primary_emotion():
    base = {"intro": 0.84, "chorus": 1.08, "outro": 0.78}
    grief_vel = apply_tension_arc_to_professionalizer_velocities(base, emotion_name="grief", blend=1.0)
    spike_vel = apply_tension_arc_to_professionalizer_velocities(base, emotion_name="excitement", blend=1.0)
    assert grief_vel["chorus"] < base["chorus"]
    assert spike_vel["chorus"] > base["chorus"]
