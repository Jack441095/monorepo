"""Qualified device profiles load from data files, and only when they carry a passed qualification."""

from __future__ import annotations

import json

import pytest

from kenn.core import device_units


def entry(**changes):
    base = {"parameter": "Filter Freq", "unit": "hz", "mapping": "log", "raw_min": 0.0, "raw_max": 1.0,
            "display_min": 20.0, "display_max": 20000.0,
            "qualification": {"status": "passed", "points": 3, "qualified_at": "2026-09-30"}}
    return {**base, **changes}


@pytest.fixture()
def profiles(tmp_path, monkeypatch):
    monkeypatch.setattr(device_units, "PROFILES_DIR", tmp_path)

    def write(*entries, device="Operator", name="operator.json"):
        (tmp_path / name).write_text(json.dumps({"schema": "kenn.device_profiles.v1", "device": device, "profiles": list(entries)}), encoding="utf-8")
        device_units.reload_profiles()
        return device_units.qualified_profiles()

    yield write
    monkeypatch.undo()
    device_units.reload_profiles()


def test_a_qualified_profile_converts_display_units(profiles) -> None:
    profiles(entry())
    raw, error = device_units.display_to_raw(device_name="Operator", parameter_name="Filter Freq", value=2000.0, unit="Hz")
    assert error is None and raw == pytest.approx(2 / 3, abs=1e-3)
    display, _ = device_units.raw_to_display(device_name="operator", parameter_name="filter freq", raw=0.0, unit="hz")
    assert display == pytest.approx(20.0)


def test_a_candidate_without_a_passed_qualification_is_ignored(profiles) -> None:
    assert profiles(entry(qualification=None)) == ()
    assert profiles(entry(qualification={"status": "failed", "points": 3, "qualified_at": "2026-09-30"})) == ()
    assert profiles(entry(qualification={"status": "passed", "points": 2, "qualified_at": "2026-09-30"})) == ()
    assert profiles(entry(qualification={"status": "passed", "points": 3})) == ()
    assert device_units.find_profile("Operator", "Filter Freq", "hz") is None


@pytest.mark.parametrize("changes", [
    {"mapping": "spline"}, {"unit": "octaves"}, {"raw_max": 0.0}, {"display_min": 0.0},   # log needs a positive range
    {"display_max": float("nan")}, {"mapping": "table"},                                  # a table needs its points
])
def test_an_inconsistent_entry_is_dropped_not_loaded(profiles, changes) -> None:
    assert profiles(entry(**changes)) == ()


def test_a_table_profile_interpolates_its_measured_points(profiles) -> None:
    table = entry(parameter="Ratio", unit="ratio", mapping="table", raw_min=0.0, raw_max=1.0, display_min=1.0, display_max=100.0,
                  raw_values=[0.0, 0.5, 1.0], display_values=[1.0, 4.0, 100.0])
    profiles(table)
    raw, error = device_units.display_to_raw(device_name="Operator", parameter_name="Ratio", value=4.0, unit="ratio")
    assert error is None and raw == pytest.approx(0.5)


def test_a_broken_file_is_skipped_and_the_rest_still_load(profiles, tmp_path) -> None:
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    assert [p.parameter_name for p in profiles(entry())] == ["Filter Freq"]


def test_the_hand_verified_profiles_win_a_clash(profiles) -> None:
    clash = entry(parameter="Threshold", unit="db", mapping="linear", display_min=-100.0, display_max=100.0)
    profiles(clash, device="Compressor", name="compressor.json")
    assert device_units.find_profile("Compressor", "Threshold", "db").display_min == -57.2


def test_the_measured_facts_check_sees_qualified_profiles_too(profiles, tmp_path, monkeypatch) -> None:
    from kenn.knowledge import measured_facts

    profiles(entry())
    facts = measured_facts.facts_from_profiles()
    assert any(f.device == "Operator" and f.parameter == "Filter Freq" and (f.low, f.high) == (20.0, 20000.0) for f in facts)
