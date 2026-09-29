"""A note that gives a number Live's own range rules out is flagged, and the measurement wins."""

from __future__ import annotations

import json

import pytest

from kenn.knowledge import contradictions, measured_facts
from kenn.knowledge.measured_facts import Fact, check_note

THRESHOLD = Fact("Compressor", "Threshold", "db", -57.2, 6.0, "device_units:Compressor.Threshold")
DRIVE = Fact("Saturator", "Drive", "db", -36.0, 36.0, "device_units:Saturator.Drive")
ATTACK = Fact("Glue Compressor", "Attack", "ms", 0.01, 30.0, "device_units:Glue Compressor.Attack")
WET = Fact("Echo", "Dry Wet", "%", 0.0, 100.0, "device_units:Echo.Dry Wet")
FACTS = [THRESHOLD, DRIVE, ATTACK, WET]


def claimed(text: str, title: str = "") -> list[float]:
    return [item["claimed"] for item in check_note(text, title, FACTS)]


def test_a_threshold_below_what_live_can_show_is_flagged() -> None:
    assert claimed("Set the Compressor threshold to -70 dB for heavy squash.") == [-70.0]


def test_a_value_inside_the_measured_range_is_left_alone() -> None:
    assert claimed("Set the Compressor threshold to -18 dB and bring it up to 0 dB later.") == []


def test_the_note_title_can_name_the_device() -> None:
    assert claimed("Pull the threshold down to -80 dB.", title="Compressor basics") == [-80.0]
    assert claimed("Pull the threshold down to -80 dB.", title="Reverb basics") == []


def test_units_are_converted_before_comparing() -> None:
    fact = Fact("Auto Filter", "Frequency", "hz", 20.0, 20000.0, "x")
    assert [i["claimed"] for i in check_note("Auto Filter frequency at 30 kHz.", "", [fact])] == [30000.0]
    assert check_note("Auto Filter frequency at 2 kHz.", "", [fact]) == []


def test_a_figure_that_belongs_to_another_parameter_is_not_the_thresholds() -> None:
    text = "On the Compressor, set attack to 100 ms and threshold to -20 dB."
    assert claimed(text) == []
    assert claimed("On the Compressor, set threshold to -20 dB with attack at -90 dB.") == []


def test_a_figure_in_another_unit_is_not_compared() -> None:
    assert claimed("Compressor threshold near 400 Hz is a sidechain filter setting.") == []


def test_percent_ranges_and_millisecond_ranges() -> None:
    assert claimed("Echo dry wet at 150% is the extreme.") == [150.0]
    assert claimed("Glue Compressor attack of 100 ms is slow.") == [100.0]
    assert claimed("Glue Compressor attack of 10 ms is fine.") == []


def test_each_wrong_number_is_reported_once() -> None:
    text = "Compressor threshold -70 dB. Again, the Compressor threshold -70 dB."
    assert claimed(text) == [-70.0]


def test_profiles_and_evidence_files_both_supply_facts(tmp_path) -> None:
    evidence = {"device": "Utility", "parameters": [
        {"name": "Gain", "unit": "db", "mapping": "linear", "display_min": -35.0, "display_max": 35.0},
        {"name": "Mode", "quantized": True},
        {"name": "Odd", "unit": "db", "mapping": "unparsed"},
    ]}
    (tmp_path / "utility.json").write_text(json.dumps(evidence), encoding="utf-8")
    facts = measured_facts.load_facts(tmp_path)
    assert any(f.device == "Utility" and f.parameter == "Gain" and (f.low, f.high) == (-35.0, 35.0) for f in facts)
    assert not any(f.parameter in {"Mode", "Odd"} for f in facts)
    assert any(f.device == "Compressor" and f.parameter == "Threshold" for f in facts)


def test_a_later_measurement_replaces_the_profile(tmp_path) -> None:
    evidence = {"device": "Compressor", "parameters": [
        {"name": "Threshold", "unit": "db", "mapping": "table", "display_min": -60.0, "display_max": 6.0}]}
    (tmp_path / "compressor.json").write_text(json.dumps(evidence), encoding="utf-8")
    (fact,) = [f for f in measured_facts.load_facts(tmp_path) if (f.device, f.parameter) == ("Compressor", "Threshold")]
    assert fact.low == -60.0


NOTE = """# Compressor threshold
Status: Approved
Tags: compressor, dynamics

Short answer:
Set the Compressor threshold to {value} dB.
"""


@pytest.fixture()
def registry(tmp_path, monkeypatch):
    monkeypatch.setenv("KENN_DB_PATH", str(tmp_path / "kenn.db"))
    monkeypatch.setenv("KENN_MEASURED_DEVICES_DIR", str(tmp_path / "none"))
    notes = tmp_path / "notes"
    notes.mkdir()
    return notes


def test_the_scan_records_a_note_vs_measured_finding_and_then_retires_it_when_the_note_is_fixed(registry) -> None:
    note = registry / "compressor-threshold.md"
    note.write_text(NOTE.format(value="-75"), encoding="utf-8")
    (found,) = [c for c in contradictions.scan_for_contradictions(registry) if c["type"] == "note_vs_measured"]
    assert found["source_a"] == "compressor-threshold.md" and found["source_b"] == "measured:Compressor.Threshold"
    assert found["conflicting_data"]["winner"] == "measured_live_data" and "-57.2" in found["description"]
    assert [c["type"] for c in contradictions.list_contradictions()] == ["note_vs_measured"]

    note.write_text(NOTE.format(value="-20"), encoding="utf-8")
    contradictions.scan_for_contradictions(registry)
    assert contradictions.list_contradictions() == []


def test_a_generated_measured_note_is_not_checked_against_itself(registry) -> None:
    dated = NOTE.replace("Tags: compressor, dynamics", "Tags: compressor, dynamics\nMeasured at: 2026-09-30")
    (registry / "measured-compressor.md").write_text(dated.format(value="-75"), encoding="utf-8")
    assert [c for c in contradictions.scan_for_contradictions(registry) if c["type"] == "note_vs_measured"] == []


def test_a_hand_written_measured_name_without_the_date_is_still_checked(registry) -> None:
    # Regression (review): the exemption used to be the filename alone.
    (registry / "measured-compressor.md").write_text(NOTE.format(value="-75"), encoding="utf-8")
    assert len([c for c in contradictions.scan_for_contradictions(registry) if c["type"] == "note_vs_measured"]) == 1


def test_keeping_the_measurement_turns_the_note_back_into_a_draft(registry) -> None:
    note = registry / "compressor-threshold.md"
    note.write_text(NOTE.format(value="-75"), encoding="utf-8")
    contradictions.scan_for_contradictions(registry)
    (open_item,) = contradictions.list_contradictions()
    assert contradictions.resolve_contradiction(open_item["contradiction_id"], "primary_b", registry)
    assert "Status: Draft" in note.read_text(encoding="utf-8")


GLUE = Fact("Glue Compressor", "Threshold", "db", -40.0, 0.0, "x")


def test_the_default_evidence_folder_is_the_one_the_measuring_tool_writes_to() -> None:
    # Regression (review, 29 Sept): parents[4] pointed at products/kenn/apps/tooling, so measured files were never read.
    assert measured_facts.DEFAULT_MEASURED_DIR.parent.is_dir() and measured_facts.DEFAULT_MEASURED_DIR.is_dir()
    assert measured_facts.DEFAULT_MEASURED_DIR.parts[-4:] == ("kenn", "tooling", "data", "measured_devices")


def test_a_title_about_one_device_does_not_cover_a_sentence_about_another() -> None:
    # Regression (review): "Gate threshold -80 dB" in a note titled "Compressor vs Gate" was held to the Compressor's range.
    assert claimed("Gate threshold -80 dB is fine for noisy drums.", title="Compressor vs Gate") == []
    assert claimed("Pull the threshold to -80 dB.", title="Compressor basics") == [-80.0]


def test_a_longer_device_name_is_not_read_as_the_shorter_one() -> None:
    both = [THRESHOLD, GLUE]
    got = check_note("Glue Compressor threshold at -50 dB.", "Glue Compressor tips", both)
    assert [(i["device"], i["claimed"]) for i in got] == [("Glue Compressor", -50.0)]


@pytest.mark.parametrize("sentence", [
    "Common mistakes: setting the Compressor threshold to -80 dB.",
    "Never push the Compressor threshold below -70 dB.",
    "Avoid a Compressor threshold of -90 dB.",
])
def test_a_warning_about_a_value_is_not_a_claim_that_it_can_be_set(sentence) -> None:
    assert claimed(sentence) == []
