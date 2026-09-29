"""A candidate becomes a profile only when Live's own display agrees with it at three points and every write is undone."""

from __future__ import annotations

import json
import math

import pytest

from kenn.core import device_units
from scripts.qualify_device_profiles import locate, run, pick_raw_values as raw_test_values, to_profile, within_tolerance, write_profiles

FILTER = {"parameter": "Filter Freq", "unit": "hz", "mapping": "log", "raw_min": 0.0, "raw_max": 1.0, "display_min": 20.0, "display_max": 20000.0}
GAIN = {"parameter": "Gain", "unit": "db", "mapping": "linear", "raw_min": 0.0, "raw_max": 1.0, "display_min": -36.0, "display_max": 36.0}
STATE = {"tracks": [{"index": 0, "name": "Bass", "devices": [{"name": "EQ Eight"}]}, {"index": 3, "name": "Lead", "devices": [{"name": "Operator"}]}]}


class FakeLive:
    """Stands in for the qualifier's real-Live call: shows what a chosen truth function says, like str_for_value."""

    def __init__(self, truth, fail_on=None):
        self.truth, self.fail_on, self.calls = truth, fail_on, []

    def qualify(self, *, endpoint, track_index, device_index, parameter_name, value, session_id, apply):
        self.calls.append((parameter_name, value, apply))
        if self.fail_on and len(self.calls) == self.fail_on:
            return {"status": "failed", "error": "device restoration or replay check failed", "target": {}}
        if not apply:
            return {"status": "proposal_ready", "target": {"display_before": "1.00 kHz"}}
        return {"status": "passed", "target": {"display_before": "1.00 kHz"}, "display_after": self.truth(parameter_name, value), "restored_readback": 0.5}


def live_truth(parameter, raw):
    if parameter == "Filter Freq":
        hz = 20.0 * (1000.0 ** raw)
        return f"{hz / 1000:.2f} kHz" if hz >= 1000 else f"{hz:.0f} Hz"
    return f"{-36 + 72 * raw:.1f} dB"


def setup(tmp_path, *entries, device="Operator"):
    candidates = tmp_path / "candidates"
    candidates.mkdir(exist_ok=True)
    (candidates / "operator.json").write_text(json.dumps({"device": device, "profiles": list(entries)}), encoding="utf-8")
    return dict(candidates_dir=candidates, state=STATE, endpoint="x", pause=0.0, profiles_dir=tmp_path / "profiles", transcripts_dir=tmp_path / "transcripts")


def test_three_agreeing_points_qualify_the_parameter_and_the_profile_then_loads(tmp_path, monkeypatch) -> None:
    live = FakeLive(live_truth)
    summary = run(**setup(tmp_path, FILTER), qualify=live.qualify, apply=True)
    assert summary["passed"] == ["Operator / Filter Freq"] and summary["failed"] == []
    assert len(live.calls) == 3 and all(apply for _, _, apply in live.calls)
    saved = json.loads((tmp_path / "profiles" / "operator.json").read_text(encoding="utf-8"))
    assert saved["profiles"][0]["qualification"]["points"] == 3 and saved["profiles"][0]["qualification"]["status"] == "passed"
    assert len(json.loads((tmp_path / "transcripts" / "operator.json").read_text(encoding="utf-8"))["Filter Freq"]["points"]) == 3
    monkeypatch.setattr(device_units, "PROFILES_DIR", tmp_path / "profiles")
    device_units.reload_profiles()
    raw, error = device_units.display_to_raw(device_name="Operator", parameter_name="Filter Freq", value=1000.0, unit="hz")
    monkeypatch.undo()
    device_units.reload_profiles()
    assert error is None and raw == pytest.approx(math.log(50) / math.log(1000), abs=1e-3)


def test_a_mapping_that_disagrees_with_lives_display_is_not_written(tmp_path) -> None:
    linear_display = lambda parameter, raw: f"{20 + raw * 19980:.0f} Hz"   # Live is not logarithmic here; the candidate says it is
    summary = run(**setup(tmp_path, FILTER), qualify=FakeLive(linear_display).qualify, apply=True)
    assert summary["passed"] == [] and "Filter Freq" in summary["failed"][0] and "predicted" in summary["failed"][0]
    assert not (tmp_path / "profiles").exists()


def test_a_failed_write_undo_or_replay_check_stops_the_parameter_and_writes_nothing(tmp_path) -> None:
    live = FakeLive(live_truth, fail_on=2)
    summary = run(**setup(tmp_path, FILTER), qualify=live.qualify, apply=True)
    assert len(live.calls) == 2 and "restoration or replay" in summary["failed"][0]
    assert not (tmp_path / "profiles").exists()


def test_without_apply_nothing_is_written_to_live_or_to_the_profiles(tmp_path) -> None:
    live = FakeLive(live_truth)
    summary = run(**setup(tmp_path, FILTER), qualify=live.qualify, apply=False)
    assert all(not apply for _, _, apply in live.calls) and summary["passed"] == []
    assert "nothing written" in summary["skipped"][0] and not (tmp_path / "profiles").exists()


def test_a_dB_control_is_never_tested_above_zero() -> None:
    profile = to_profile("Utility", GAIN)
    values = raw_test_values(profile, current=None)
    assert len(values) == 3 and all(-36 + 72 * raw <= 1e-9 for raw in values)


def test_a_test_value_never_equals_the_current_value() -> None:
    profile = to_profile("Utility", {**GAIN, "display_min": -36.0, "display_max": 0.0})
    assert 0.5 not in [round(v, 6) for v in raw_test_values(profile, current=0.5)]


@pytest.mark.parametrize("shown, ok", [("1.00 kHz", True), ("1.01 kHz", True), ("1.03 kHz", False), ("1.20 kHz", False), ("998 Hz", True), ("2 kHz", False), ("weird", False), ("12 dB", False)])
def test_the_display_check_reads_units_and_allows_for_the_digits_shown(shown, ok) -> None:
    profile = to_profile("Operator", FILTER)
    raw = math.log(50) / math.log(1000)   # the mapping predicts 1000 Hz
    assert within_tolerance(profile, raw, shown)[0] is ok


def test_devices_only_on_a_return_or_master_and_hand_verified_ones_are_skipped(tmp_path) -> None:
    compressor = {"parameter": "Threshold", "unit": "db", "mapping": "linear", "raw_min": 0.0, "raw_max": 1.0, "display_min": -60.0, "display_max": 6.0}
    kwargs = setup(tmp_path, compressor, device="Compressor")
    summary = run(**{**kwargs, "state": STATE}, qualify=FakeLive(live_truth).qualify, apply=True)
    assert summary["skipped"] == ["Compressor: not on a regular track in the open set"]
    kwargs = setup(tmp_path, compressor, device="Operator")
    (tmp_path / "candidates" / "operator.json").write_text(json.dumps({"device": "Compressor", "profiles": [compressor]}), encoding="utf-8")
    summary = run(**{**kwargs, "state": {"tracks": [{"index": 1, "devices": [{"name": "Compressor"}]}]}}, qualify=FakeLive(live_truth).qualify, apply=True)
    assert summary["skipped"] == ["Compressor / Threshold: hand-verified profile already exists"]


def test_the_device_on_switch_is_never_toggled(tmp_path) -> None:
    live = FakeLive(live_truth)
    summary = run(**setup(tmp_path, {**FILTER, "parameter": "Device On"}), qualify=live.qualify, apply=True)
    assert live.calls == [] and "never toggled" in summary["skipped"][0]


def test_requalifying_replaces_one_parameter_and_keeps_the_others(tmp_path) -> None:
    old = {"parameter": "Filter Freq", "display_max": 10000.0, "qualification": {"status": "passed", "points": 3, "qualified_at": "2026-01-01"}}
    (tmp_path / "profiles").mkdir()
    (tmp_path / "profiles" / "operator.json").write_text(json.dumps({"device": "Operator", "profiles": [old, {**GAIN, "qualification": old["qualification"]}]}), encoding="utf-8")
    result = {"points": [{"raw": 0.2}, {"raw": 0.5}, {"raw": 0.8}]}
    write_profiles(tmp_path / "profiles", tmp_path / "transcripts", "Operator", [(FILTER, result)])
    saved = json.loads((tmp_path / "profiles" / "operator.json").read_text(encoding="utf-8"))["profiles"]
    assert [p["parameter"] for p in saved] == ["Filter Freq", "Gain"] and saved[0]["display_max"] == 20000.0


def test_locate_finds_the_first_track_carrying_the_device() -> None:
    assert locate(STATE, "operator") == (3, 0) and locate(STATE, "Wavetable") is None
