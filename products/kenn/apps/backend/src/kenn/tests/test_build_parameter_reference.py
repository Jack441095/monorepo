"""Parameter-reference notes carry only what Live displayed, start as drafts, and index as measured data."""

from __future__ import annotations

import json

import pytest

from kenn.knowledge.measured_facts import check_note, facts_from_evidence
from kenn.retrieval.build_index import iter_note_chunks
from scripts.build_parameter_reference import build_notes, describe, main

COMPRESSOR = {
    "device": "Compressor", "measured_at": "2026-09-30",
    "parameters": [
        {"name": "Threshold", "unit": "db", "mapping": "table", "display_min": -57.2, "display_max": 6.0},
        {"name": "Ratio", "unit": "ratio", "mapping": "log", "display_min": 1.0, "display_max": 100.0},
        {"name": "Attack", "unit": "ms", "mapping": "linear", "display_min": 0.01, "display_max": 1000.0},
        {"name": "Release", "unit": "ms", "mapping": "log", "display_min": 1.0, "display_max": 3000.0},
        {"name": "Frequency", "unit": "hz", "mapping": "log", "display_min": 20.0, "display_max": 20000.0},
        {"name": "Model", "quantized": True, "options": [[0, "Peak"], [1, "RMS"], [2, "Expand"], [1, "RMS"]]},
        {"name": "Odd", "mapping": "unparsed", "examples": ["Off", "On"]},
        {"name": "Broken", "error": "timeout"},
    ],
}


@pytest.mark.parametrize("index, expected", [
    (0, "- Threshold: -57.2 dB to +6 dB; the control does not follow a straight line; Live uses its own table."),
    (1, "- Ratio: 1:1 to 100:1; the control moves in a logarithmic curve (equal knob steps are equal ratios)."),
    (3, "- Release: 1 ms to 3 s; the control moves in a logarithmic curve (equal knob steps are equal ratios)."),
    (4, "- Frequency: 20 Hz to 20 kHz; the control moves in a logarithmic curve (equal knob steps are equal ratios)."),
    (5, "- Model: choose one of Peak, RMS, Expand."),
    (6, "- Odd: Live shows values such as Off, On."),
    (7, None),
])
def test_each_parameter_says_only_what_live_displayed(index, expected) -> None:
    assert describe(COMPRESSOR["parameters"][index]) == expected


def test_a_device_with_many_parameters_is_split_into_small_notes() -> None:
    many = {"device": "Operator", "measured_at": "2026-09-30",
            "parameters": [{"name": f"P{n}", "unit": "%", "mapping": "linear", "display_min": 0, "display_max": 100} for n in range(30)]}
    notes = build_notes(many, status="Draft")
    assert sorted(notes) == ["measured-operator-1.md", "measured-operator-2.md", "measured-operator-3.md"]
    assert "part 2 of 3" in notes["measured-operator-2.md"]


def test_notes_start_as_drafts_and_the_index_skips_them(tmp_path) -> None:
    (name, text), = build_notes(COMPRESSOR, status="Draft").items()
    (tmp_path / name).write_text(text, encoding="utf-8")
    assert iter_note_chunks(tmp_path / name) == []


def test_an_approved_note_indexes_as_measured_data(tmp_path) -> None:
    (name, text), = build_notes(COMPRESSOR, status="Approved").items()
    (tmp_path / name).write_text(text, encoding="utf-8")
    chunks = iter_note_chunks(tmp_path / name)
    assert chunks and {c.evidence_class for c in chunks} == {"measured_live_data"}
    assert "Threshold: -57.2 dB to +6 dB" in chunks[0].text


def test_the_notes_do_not_contradict_the_measurements_they_came_from(tmp_path) -> None:
    (tmp_path / "compressor.json").write_text(json.dumps(COMPRESSOR), encoding="utf-8")
    (name, text), = build_notes(COMPRESSOR, status="Approved").items()
    assert check_note(text, "Compressor parameter ranges", facts_from_evidence(tmp_path)) == []


def test_evidence_without_a_date_is_refused() -> None:
    with pytest.raises(ValueError):
        build_notes({"device": "Compressor", "parameters": []}, status="Draft")


def test_the_command_writes_drafts_then_approves(tmp_path, monkeypatch) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "compressor.json").write_text(json.dumps(COMPRESSOR), encoding="utf-8")
    out = tmp_path / "notes"
    monkeypatch.setattr("sys.argv", ["x", "--out", str(out), "--evidence-dir", str(evidence)])
    assert main() == 0 and "Status: Draft" in (out / "measured-compressor-1.md").read_text(encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["x", "--out", str(out), "--evidence-dir", str(evidence), "--approve"])
    assert main() == 0 and "Status: Approved" in (out / "measured-compressor-1.md").read_text(encoding="utf-8")


def test_a_rerun_keeps_an_approved_note_approved_and_drops_parts_no_longer_needed(tmp_path, monkeypatch) -> None:
    # Regression (review): a rerun without --approve demoted every note to Draft, and shrunk devices left stale parts.
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    many = {"device": "Operator", "measured_at": "2026-09-30",
            "parameters": [{"name": f"P{n}", "unit": "%", "mapping": "linear", "display_min": 0, "display_max": 100} for n in range(30)]}
    (evidence / "operator.json").write_text(json.dumps(many), encoding="utf-8")
    out = tmp_path / "notes"
    args = ["x", "--out", str(out), "--evidence-dir", str(evidence)]
    monkeypatch.setattr("sys.argv", [*args, "--approve"])
    assert main() == 0 and len(list(out.glob("measured-operator-*.md"))) == 3

    many["parameters"] = many["parameters"][:20]
    (evidence / "operator.json").write_text(json.dumps(many), encoding="utf-8")
    monkeypatch.setattr("sys.argv", args)
    assert main() == 0
    assert sorted(p.name for p in out.glob("measured-operator-*.md")) == ["measured-operator-1.md", "measured-operator-2.md"]
    assert all("Status: Approved" in p.read_text(encoding="utf-8") for p in out.glob("measured-operator-*.md"))
