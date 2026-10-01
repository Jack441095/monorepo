"""A2: the wave-1 device zoo Jack builds in Live, and the rehearsal that catches a wasted night.

Live belongs to Jack, so none of this touches it. The zoo fixture is the set he is asked to build, rehearsed here
against FakeLiveBackend so a device sitting on a return instead of a track is found here rather than 90 minutes into
Live night 1.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import prep_device_zoo
from scripts.qualify_device_candidates import pick_raw_values, to_profile

from kenn.core.device_units import DeviceUnitProfile
from kenn.core.live_action_service import DEVICE_INSERTION_ALLOWLIST

PROFILES_DIR = Path(__file__).resolve().parents[3] / "core" / "device_profiles"


@pytest.fixture(scope="module")
def zoo() -> dict:
    return json.loads(prep_device_zoo.ZOO_FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def rehearsal() -> dict:
    return prep_device_zoo.rehearse(prep_device_zoo.WAVE_ONE)


def _unmapped(report: dict) -> list[str]:
    return [entry for entries in report["unmapped_reasons"].values() for entry in entries]


def test_the_zoo_puts_each_wave_one_device_on_its_own_regular_track(zoo) -> None:
    """locate() only searches state['tracks'], so a device on a return cannot be qualified at all."""
    tracks = zoo["session"]["tracks"]
    on_tracks = [device["name"] for track in tracks for device in track["devices"]]
    assert sorted(on_tracks) == sorted(prep_device_zoo.WAVE_ONE)
    assert not zoo["return_tracks"] and not zoo["session"]["return_tracks"]
    assert not zoo["session"]["master_track"]["devices"]


def test_the_zoo_needs_exactly_one_track_per_device_so_the_sweep_measures_each_once(zoo) -> None:
    """measure_all_devices.sweep keys its evidence on class_name, so a second copy would only be skipped."""
    assert len(zoo["session"]["tracks"]) == len(prep_device_zoo.WAVE_ONE)
    assert len({track["name"] for track in zoo["session"]["tracks"]}) == len(zoo["session"]["tracks"])


def test_a_wave_one_name_live_does_not_ship_is_reported_before_the_live_night() -> None:
    """--only matches the name Live reports, so a typo would quietly measure nothing at all."""
    report = prep_device_zoo.preflight(("EQ Eight", "Widows And Orphans"))
    assert any("Widows And Orphans" in problem and "not a Live 12 Suite browser name" in problem
               for problem in report["problems"])


def test_the_wave_one_devices_kenn_cannot_insert_are_listed_with_the_reason() -> None:
    """Four of the twelve have to be dragged in by hand, so the set cannot be built by script."""
    report = prep_device_zoo.preflight(prep_device_zoo.WAVE_ONE)
    hand_dragged = {row["device"] for row in report["rows"] if not row["insertable"]}
    assert hand_dragged == {"Utility", "Limiter", "Reverb", "Delay"}
    assert not hand_dragged & DEVICE_INSERTION_ALLOWLIST
    for row in report["rows"]:
        if not row["insertable"]:
            assert row["reason"], f"{row['device']} needs a hand drag but nobody wrote down why"


def test_a_clean_preflight_of_the_whole_wave_reports_no_problems() -> None:
    assert prep_device_zoo.preflight(prep_device_zoo.WAVE_ONE)["problems"] == []


def test_the_rehearsal_measures_every_wave_one_device_and_finds_nothing_off_a_track(rehearsal) -> None:
    """The night is two hours. This is what proves the set is worth opening it for."""
    assert rehearsal["problems"] == []
    assert rehearsal["devices_found"] == len(prep_device_zoo.WAVE_ONE)
    assert rehearsal["candidates"] == len(prep_device_zoo.WAVE_ONE)
    assert rehearsal["not_on_a_track"] == []
    assert rehearsal["rehearsed"] > 0


def test_the_rehearsal_qualifies_nothing_into_the_shipped_profiles() -> None:
    """apply=False is the point: a rehearsal that wrote a profile would claim evidence no Live run produced."""
    before = {path.name for path in PROFILES_DIR.glob("*.json")}
    prep_device_zoo.rehearse(prep_device_zoo.WAVE_ONE)
    assert {path.name for path in PROFILES_DIR.glob("*.json")} == before


def test_a_rehearsal_that_measures_nothing_is_reported_rather_than_passing_silently() -> None:
    """sweep returns an empty summary when Live is not connected, and an empty expectation is not a pass."""
    report = prep_device_zoo.rehearse(())
    assert any("expected" in problem for problem in report["problems"])


def test_a_ratio_display_is_readable_because_live_writes_a_space_before_the_one() -> None:
    """Compressor and Glue Compressor both show "4.00 : 1"; matching the unit as one token drops Ratio."""
    report = prep_device_zoo.rehearse(("Compressor", "Glue Compressor"))
    assert not any("Ratio" in entry for entry in _unmapped(report)), _unmapped(report)


def test_a_bare_number_parameter_is_left_unmapped_rather_than_guessed_at() -> None:
    """EQ Eight's Q shows "1.00" with no unit, so there is nothing to convert to and KENN must not invent one."""
    report = prep_device_zoo.rehearse(("EQ Eight",))
    assert "EQ Eight / Q" in _unmapped(report)
    assert any("bare number with no unit" in reason for reason in report["unmapped_reasons"])


def test_a_db_control_that_only_goes_above_zero_still_gets_three_points_to_test() -> None:
    """Saturator's Base runs 0..24 dB. Clamping its range to 0 dB left one distinct value, so it could never qualify."""
    saturator_base = DeviceUnitProfile("Saturator", "Base", "db", 0.0, 1.0, 0.0, 24.0, mapping="linear")
    points = pick_raw_values(saturator_base, None)
    assert len(set(points)) == 3, "three fractions of a collapsed range all land on the same raw value"
    assert all(0.0 <= point <= 1.0 for point in points)


def test_a_db_control_that_does_go_below_zero_is_still_never_taken_above_it() -> None:
    """The clamp exists so a gain-like control cannot be driven loud; the all-positive fallback must not weaken it."""
    utility_output = DeviceUnitProfile("Utility", "Output", "db", 0.0, 1.0, -60.0, 60.0, mapping="linear")
    points = pick_raw_values(utility_output, None)
    assert len(set(points)) == 3
    assert max(points) < 1.0, "Output reaches +60 dB at the top of its raw range"


def test_a_candidate_profile_round_trips_through_the_shipping_conversion() -> None:
    """pick_raw_values and to_profile have to agree with device_units, or the qualifier tests values it cannot write."""
    entry = {"parameter": "Frequency", "unit": "hz", "raw_min": 0.0, "raw_max": 1.0,
             "display_min": 20.0, "display_max": 20000.0, "mapping": "log"}
    profile = to_profile("Auto Filter", entry)
    assert profile.display_unit == "hz"
    assert len(set(pick_raw_values(profile, None))) == 3


def test_the_nights_command_sequence_filters_the_measure_to_the_wave() -> None:
    """Without --only the sweep would also measure every device left over in the set from an earlier night."""
    commands = prep_device_zoo.command_sequence(("EQ Eight", "Compressor"))
    assert '--only "EQ Eight,Compressor"' in commands[0]
    assert commands[1].startswith("python3 tooling/scripts/build_device_profiles.py")
    assert commands[-2] == "python3 tooling/scripts/qualify_device_candidates.py"
    assert commands[-1].endswith("--apply"), "the unapplied run is the safe first one"