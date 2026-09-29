"""Measured evidence becomes candidate profiles, choosers or an honest 'unmapped' with the reason."""

from __future__ import annotations

import json

import pytest

from kenn.core import device_units
from scripts.build_device_profiles import build, classify_parameter, coverage, main, render

LINEAR = {"name": "Resonance", "unit": "%", "mapping": "linear", "raw_min": 0.0, "raw_max": 1.0, "display_min": 0.0, "display_max": 100.0}
LOG = {"name": "Filter Freq", "unit": "hz", "mapping": "log", "raw_min": 0.0, "raw_max": 1.0, "display_min": 20.0, "display_max": 20000.0}
TABLE = {"name": "Threshold", "unit": "db", "mapping": "table", "raw_min": 0.0, "raw_max": 1.0, "display_min": -60.0, "display_max": 6.0,
         "points": [[0.0, -60.0], [0.5, -20.0], [1.0, 6.0]]}
DESC = {**TABLE, "name": "Release Time", "mapping": "table_descending", "points": [[0.0, 300.0], [0.5, 40.0], [1.0, 1.0]],
        "display_min": 300.0, "display_max": 1.0, "unit": "ms"}


def kind(entry):
    return classify_parameter(entry)[0]


def test_continuous_parameters_in_a_unit_kenn_converts_become_profiles() -> None:
    assert [kind(e) for e in (LINEAR, LOG, TABLE, DESC)] == ["profile"] * 4
    _, table = classify_parameter(TABLE)
    assert table["mapping"] == "table" and table["raw_values"] == [0.0, 0.5, 1.0] and table["display_values"] == [-60.0, -20.0, 6.0]


def test_a_descending_table_is_kept_as_measured() -> None:
    _, data = classify_parameter(DESC)
    assert data["display_values"] == [300.0, 40.0, 1.0]


def test_a_long_table_is_thinned_but_keeps_both_ends() -> None:
    points = [[i / 199, -60 + 66 * i / 199] for i in range(200)]
    _, data = classify_parameter({**TABLE, "points": points})
    assert len(data["raw_values"]) == 64 and data["raw_values"][0] == 0.0 and data["raw_values"][-1] == 1.0


def test_choosers_keep_the_option_live_shows_for_each_value() -> None:
    which, data = classify_parameter({"name": "Model", "quantized": True, "options": [[0, "Peak"], [1, "RMS"], [2, " "]]})
    assert which == "chooser" and data["options"] == [{"raw": 0, "label": "Peak"}, {"raw": 1, "label": "RMS"}]


@pytest.mark.parametrize("entry, reason", [
    ({"name": "Gain", "unit": "value", "mapping": "linear", "raw_min": 0, "raw_max": 1, "display_min": 0, "display_max": 1}, "no unit"),
    ({"name": "Odd", "mapping": "unparsed", "examples": ["Off", "On"]}, "isn't a number"),
    ({"name": "Broken", "error": "timeout"}, "timeout"),
    ({"name": "Empty", "quantized": True, "options": []}, "no readable options"),
    ({**LOG, "display_min": 0.0}, "reaches zero"),
    ({**TABLE, "points": [[0, 1], [1, 2]]}, "fewer than three"),
])
def test_what_cannot_be_mapped_says_why(entry, reason) -> None:
    which, data = classify_parameter(entry)
    assert which == "unmapped" and reason in data["reason"]


def test_evidence_without_a_date_is_refused() -> None:
    with pytest.raises(ValueError):
        build({"device": "Operator", "parameters": []})


def test_candidates_are_not_qualified_and_the_loader_ignores_them(tmp_path, monkeypatch) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "operator.json").write_text(json.dumps({"device": "Operator", "measured_at": "2026-09-30", "parameters": [LOG]}), encoding="utf-8")
    out = tmp_path / "candidates"
    monkeypatch.setattr("sys.argv", ["x", "--evidence-dir", str(evidence), "--out-dir", str(out)])
    assert main() == 0
    candidate = json.loads((out / "operator.json").read_text(encoding="utf-8"))
    assert candidate["profiles"][0]["parameter"] == "Filter Freq" and "qualification" not in candidate["profiles"][0]
    monkeypatch.setattr(device_units, "PROFILES_DIR", out)   # even if someone points the loader at the candidates folder
    device_units.reload_profiles()
    assert device_units.find_profile("Operator", "Filter Freq", "hz") is None
    monkeypatch.undo()
    device_units.reload_profiles()


def test_coverage_counts_devices_parameters_and_what_is_missing() -> None:
    operator = build({"device": "Operator", "measured_at": "2026-09-30", "parameters": [LINEAR, LOG, {"name": "M", "quantized": True, "options": [[0, "A"]]}, {"name": "X", "mapping": "unparsed"}]})
    compressor = build({"device": "Compressor", "measured_at": "2026-09-30", "parameters": [{**TABLE}]})
    report = coverage([operator, compressor], ["Operator", "Compressor", "Wavetable", "Simpler"])
    assert report["devices_measured"] == 2 and report["devices_installed"] == 4 and report["not_measured"] == ["Simpler", "Wavetable"]
    assert report["parameters"] == {"profiles": 3, "qualified": 1, "choosers": 1, "unmapped": 1}   # Compressor Threshold is hand-verified
    text = render(report)
    assert "2 devices measured of 4 installed" in text and "Not measured yet (2): Simpler, Wavetable" in text
