"""Tests for thursday/documentation_ops.py (Thursday Ops upgrade, phase
11). Live-parses real markdown tables off disk -- fixture-based so these
tests don't depend on the real tracker's current content, matching
qa_ops's test pattern.
"""

from __future__ import annotations

import thursday.ops.documentation_ops as do


FIXTURE_TRACKER = """\
# Test Launch Tracker

## Decisions

| Decision | Status | Evidence |
|---|---|---|
| First thing | DONE | some/path.md |
| Second thing | DONE | other/path.md |

## Gates

| ID | Gate | Status | Next action | Owner/evidence |
|---|---|---|---|---|
| T-01 | Thing one | IN PROGRESS | Do the thing | someone |
| T-02 | Thing two | BLOCKED | Wait for X | someone |
| T-03 | Thing three | NOT STARTED | Start it | someone |
| T-04 | Thing four | OWNER ACTION | Founder decides | someone |
| T-05 | Compound status | DONE for reviewed fields; policy IN PROGRESS | Extend carefully | someone |

## Not a status table

| Name | Notes |
|---|---|
| X | This table has no Status column |
"""


def test_parse_extracts_rows_from_tables_with_status_column():
    rows = do.parse_gate_statuses(FIXTURE_TRACKER)
    labels = [r["label"] for r in rows]
    assert "First thing" in labels
    assert "T-01" in labels
    # The table without a Status column contributes nothing.
    assert "X" not in labels


def test_parse_reads_correct_status_value_per_row():
    rows = do.parse_gate_statuses(FIXTURE_TRACKER)
    by_label = {r["label"]: r["status"] for r in rows}
    assert by_label["T-02"] == "BLOCKED"
    assert by_label["T-04"] == "OWNER ACTION"


def test_parse_handles_tables_with_different_column_counts():
    rows = do.parse_gate_statuses(FIXTURE_TRACKER)
    # 3-column table (Decision/Status/Evidence) and 5-column table
    # (ID/Gate/Status/.../...) both parsed correctly despite different
    # status-column positions (index 1 vs index 2).
    by_label = {r["label"]: r["status"] for r in rows}
    assert by_label["First thing"] == "DONE"
    assert by_label["T-01"] == "IN PROGRESS"


def test_missing_tracker_reports_evidence_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("NITE_DSP_ROOT", str(tmp_path))
    out = do.launch_tracker_status()
    assert "Evidence missing" in out
    assert "not found" in out


def test_status_report_tallies_correctly(monkeypatch, tmp_path):
    monkeypatch.setenv("NITE_DSP_ROOT", str(tmp_path))
    tracker = tmp_path / do.LAUNCH_TRACKER_RELATIVE_PATH
    tracker.parent.mkdir(parents=True, exist_ok=True)
    tracker.write_text(FIXTURE_TRACKER)

    out = do.launch_tracker_status()
    assert "7 gates tracked." in out
    # T-05's compound status ("DONE for reviewed fields; policy IN
    # PROGRESS") tallies under "done" -- it's the first recognized
    # keyword found by substring match, per the module's documented
    # policy. So: First thing, Second thing, T-05 -> done: 3.
    assert "done: 3" in out
    assert "in progress: 1" in out
    assert "blocked: 1" in out
    assert "not started: 1" in out
    assert "owner action: 1" in out


def test_status_report_lists_blocking_gates_by_name(monkeypatch, tmp_path):
    monkeypatch.setenv("NITE_DSP_ROOT", str(tmp_path))
    tracker = tmp_path / do.LAUNCH_TRACKER_RELATIVE_PATH
    tracker.parent.mkdir(parents=True, exist_ok=True)
    tracker.write_text(FIXTURE_TRACKER)

    out = do.launch_tracker_status()
    assert "BLOCKING (3):" in out  # T-02 BLOCKED, T-03 NOT STARTED, T-04 OWNER ACTION
    assert "T-02: BLOCKED" in out
    assert "T-03: NOT STARTED" in out
    assert "T-04: OWNER ACTION" in out


def test_status_report_never_hides_a_row_behind_compound_status(monkeypatch, tmp_path):
    monkeypatch.setenv("NITE_DSP_ROOT", str(tmp_path))
    tracker = tmp_path / do.LAUNCH_TRACKER_RELATIVE_PATH
    tracker.parent.mkdir(parents=True, exist_ok=True)
    tracker.write_text(FIXTURE_TRACKER)

    rows = do.parse_gate_statuses(tracker.read_text())
    # "label" is always the table's first column (here, the ID column),
    # not whichever column looks most descriptive -- T-05 is the compound
    # row's real label, not the "Gate" column's "Compound status" text.
    compound_row = next(r for r in rows if r["label"] == "T-05")
    assert compound_row["status"] == "DONE for reviewed fields; policy IN PROGRESS"


def test_empty_table_free_doc_reports_evidence_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("NITE_DSP_ROOT", str(tmp_path))
    tracker = tmp_path / do.LAUNCH_TRACKER_RELATIVE_PATH
    tracker.parent.mkdir(parents=True, exist_ok=True)
    tracker.write_text("# Just prose\n\nNo tables here at all.\n")

    out = do.launch_tracker_status()
    assert "Evidence missing" in out
    assert "no parseable Status-column tables" in out
