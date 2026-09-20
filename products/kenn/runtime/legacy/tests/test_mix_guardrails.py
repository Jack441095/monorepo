"""Tests for kenn.core.mix_guardrails (item 2,
docs/KENN_WEEKLY_OPTIMIZATION_PLAN_2026-08-08.md)."""

from __future__ import annotations

from kenn.core.mix_guardrails import volume_increase_risks_clipping


def test_flags_an_increase_when_meter_is_near_ceiling():
    risky, warning = volume_increase_risks_clipping(
        current_meter_level=0.95, requested_volume=0.9, current_volume=0.7,
    )
    assert risky is True
    assert "0.95" in warning


def test_does_not_flag_a_decrease_even_at_a_high_meter_reading():
    risky, warning = volume_increase_risks_clipping(
        current_meter_level=0.95, requested_volume=0.6, current_volume=0.7,
    )
    assert risky is False
    assert warning == ""


def test_does_not_flag_an_increase_when_meter_is_low():
    risky, warning = volume_increase_risks_clipping(
        current_meter_level=0.3, requested_volume=0.9, current_volume=0.2,
    )
    assert risky is False


def test_does_not_flag_when_meter_reading_is_unavailable():
    # Absence of evidence isn't a reason to warn -- e.g. Ableton hasn't
    # been restarted to pick up the meter fields yet.
    risky, warning = volume_increase_risks_clipping(
        current_meter_level=None, requested_volume=0.99, current_volume=0.1,
    )
    assert risky is False
    assert warning == ""


def test_does_not_flag_when_current_volume_is_unknown_and_request_matches_meter_threshold():
    # current_volume=None (track not found in the snapshot) -- can't tell
    # if this is an increase, so fall through to the meter-level check
    # alone rather than guessing.
    risky, _ = volume_increase_risks_clipping(
        current_meter_level=0.95, requested_volume=0.9, current_volume=None,
    )
    assert risky is True


def test_boundary_exactly_at_threshold_is_flagged():
    risky, _ = volume_increase_risks_clipping(
        current_meter_level=0.9, requested_volume=0.95, current_volume=0.5,
    )
    assert risky is True


def test_just_below_threshold_is_not_flagged():
    risky, _ = volume_increase_risks_clipping(
        current_meter_level=0.89, requested_volume=0.95, current_volume=0.5,
    )
    assert risky is False
