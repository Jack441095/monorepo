"""Chorus counter-melody presence floors stay audible after thinning."""

from __future__ import annotations

from types import SimpleNamespace

from composition.section_planner.counter_melody_stage import apply_counter_presence_multiplier


def test_chorus_counter_presence_multiplier_keeps_minimum_events():
    plan = SimpleNamespace(
        counter_events=[
            (5, 60, 50, float(i), 0.5, [60])
            for i in range(8)
        ],
        melody_events=[],
    )
    apply_counter_presence_multiplier(
        plan,
        role="chorus",
        multiplier=0.22,
    )
    assert len(plan.counter_events) >= 4


def test_fall_arc_audit_fit_accepts_release_velocity():
    from scripts.batch_full_song_note_audit import _intro_chorus_velocity_arc_fit

    assert _intro_chorus_velocity_arc_fit(-4.0, "fall") >= 0.9
    assert _intro_chorus_velocity_arc_fit(28.0, "rise") >= 0.85
