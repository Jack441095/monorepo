"""Tests for thursday/qa_ops.py (Thursday Ops upgrade, phase 5).

Live-parses a real markdown checklist off disk rather than caching or
paraphrasing its content -- these tests write a fixture checklist to a
temp path and confirm the parser and renderer reflect it exactly,
including the "BLOCKED on Gate 0" logic, which comes entirely from the
checklist's own section heading, not a separately-maintained item list.
"""

from __future__ import annotations

import pytest

import thursday.ops.qa_ops as qa


FIXTURE_CHECKLIST = """\
# Test Product — Beta Launch Checklist

Some preamble text with no checkbox.

## Gate 0 — Owner decisions (nothing below moves without these)

- [ ] Name the private-beta tester cohort.
- [x] Confirm the support mailbox works.

## Days 1-2 — Freeze the artifact

- [x] Land the owner's SHA decision
- [x] Commit intentionally

## Days 3-4 — Website live

- [ ] Sign off pricing
"""

FIXTURE_ALL_GATE_0_DONE = """\
## Gate 0 — Owner decisions (nothing below moves without these)

- [x] Name the private-beta tester cohort.
- [X] Confirm the support mailbox works.

## Days 1-2 — Freeze the artifact

- [ ] Land the owner's SHA decision
"""


def test_nite_dsp_root_uses_env_var_override(monkeypatch):
    monkeypatch.setenv("NITE_DSP_ROOT", "/tmp/fake-nite-dsp")
    assert qa.nite_dsp_root() == qa.Path("/tmp/fake-nite-dsp")


def test_checklist_path_joins_root_and_relative_path(monkeypatch):
    monkeypatch.setenv("NITE_DSP_ROOT", "/tmp/fake-nite-dsp")
    assert qa.checklist_path() == qa.Path("/tmp/fake-nite-dsp") / qa.CHECKLIST_RELATIVE_PATH


# ── parse_checklist ──────────────────────────────────────────────────────


def test_parse_groups_items_under_headings():
    sections = qa.parse_checklist(FIXTURE_CHECKLIST)
    headings = [s["heading"] for s in sections]
    assert "Gate 0 — Owner decisions (nothing below moves without these)" in headings
    assert "Days 1-2 — Freeze the artifact" in headings


def test_parse_reads_checked_state_case_insensitively():
    sections = qa.parse_checklist(FIXTURE_ALL_GATE_0_DONE)
    gate_0 = next(s for s in sections if "gate 0" in s["heading"].lower())
    assert all(i["checked"] for i in gate_0["items"])


def test_parse_correctly_reads_unchecked_items():
    sections = qa.parse_checklist(FIXTURE_CHECKLIST)
    gate_0 = next(s for s in sections if "gate 0" in s["heading"].lower())
    unchecked = [i["text"] for i in gate_0["items"] if not i["checked"]]
    assert unchecked == ["Name the private-beta tester cohort."]


def test_parse_ignores_preamble_text_without_crashing():
    sections = qa.parse_checklist(FIXTURE_CHECKLIST)
    # Preamble has no checkbox lines, so it shouldn't create a spurious
    # "(preamble)" section with items -- only real checkbox lines count.
    assert not any(s["heading"] == "(preamble)" and s["items"] for s in sections)


# ── beta_readiness_check ─────────────────────────────────────────────────


def test_missing_checklist_reports_evidence_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("NITE_DSP_ROOT", str(tmp_path))
    out = qa.beta_readiness_check()
    assert "Evidence missing" in out
    assert "not found" in out


def test_readiness_blocked_when_gate_0_has_unchecked_items(monkeypatch, tmp_path):
    monkeypatch.setenv("NITE_DSP_ROOT", str(tmp_path))
    checklist = tmp_path / qa.CHECKLIST_RELATIVE_PATH
    checklist.parent.mkdir(parents=True, exist_ok=True)
    checklist.write_text(FIXTURE_CHECKLIST)

    out = qa.beta_readiness_check()
    assert "BLOCKED on \"Gate 0" in out
    assert "Name the private-beta tester cohort." in out


def test_readiness_not_blocked_when_gate_0_fully_checked(monkeypatch, tmp_path):
    monkeypatch.setenv("NITE_DSP_ROOT", str(tmp_path))
    checklist = tmp_path / qa.CHECKLIST_RELATIVE_PATH
    checklist.parent.mkdir(parents=True, exist_ok=True)
    checklist.write_text(FIXTURE_ALL_GATE_0_DONE)

    out = qa.beta_readiness_check()
    assert "BLOCKED on" not in out
    assert "fully checked off" in out


def test_readiness_reports_real_overall_fraction(monkeypatch, tmp_path):
    monkeypatch.setenv("NITE_DSP_ROOT", str(tmp_path))
    checklist = tmp_path / qa.CHECKLIST_RELATIVE_PATH
    checklist.parent.mkdir(parents=True, exist_ok=True)
    checklist.write_text(FIXTURE_CHECKLIST)

    out = qa.beta_readiness_check()
    # Fixture: Gate 0 has 1/2 checked, Days 1-2 has 2/2, Days 3-4 has 0/1
    # -- 3 checked out of 5 total items.
    assert "3/5" in out
    assert "60%" in out


def test_readiness_by_section_breakdown(monkeypatch, tmp_path):
    monkeypatch.setenv("NITE_DSP_ROOT", str(tmp_path))
    checklist = tmp_path / qa.CHECKLIST_RELATIVE_PATH
    checklist.parent.mkdir(parents=True, exist_ok=True)
    checklist.write_text(FIXTURE_CHECKLIST)

    out = qa.beta_readiness_check()
    assert "Days 1-2 — Freeze the artifact: 2/2" in out
    assert "Days 3-4 — Website live: 0/1" in out


def test_readiness_never_claims_independent_verification(monkeypatch, tmp_path):
    # It must always caveat that this is just what the file says, not a
    # real-world check -- matches the checklist doc's own stated caution.
    monkeypatch.setenv("NITE_DSP_ROOT", str(tmp_path))
    checklist = tmp_path / qa.CHECKLIST_RELATIVE_PATH
    checklist.parent.mkdir(parents=True, exist_ok=True)
    checklist.write_text(FIXTURE_ALL_GATE_0_DONE)

    out = qa.beta_readiness_check()
    assert "not an independent verification" in out


def test_empty_checklist_file_reports_evidence_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("NITE_DSP_ROOT", str(tmp_path))
    checklist = tmp_path / qa.CHECKLIST_RELATIVE_PATH
    checklist.parent.mkdir(parents=True, exist_ok=True)
    checklist.write_text("# Just a heading, no checkboxes\n")

    out = qa.beta_readiness_check()
    assert "Evidence missing" in out
    assert "no checkbox items" in out
