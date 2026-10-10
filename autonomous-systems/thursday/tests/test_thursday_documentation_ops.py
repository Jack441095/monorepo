"""Tests for the paid-launch blocker report sourced from the operations audit."""

from __future__ import annotations

import thursday.ops.documentation_ops as do


FIXTURE_AUDIT = """\
# Operations audit

## Other checklist

- [ ] **Monitoring:** this item belongs to another section.

## Launch blockers — complete before paid sales

- [x] **Operations: verify the earlier payment.** Evidence follows.
- [ ] **Owner: approve the terms.** Legal review is pending.
- [ ] A plain-label blocker.

## Maintenance already started

- [ ] **Source: remove an obsolete file.** This is not a launch blocker.
"""


def test_parse_reads_only_paid_sales_checkboxes():
    items = do.parse_launch_blockers(FIXTURE_AUDIT)
    assert items == [
        {"label": "Operations: verify the earlier payment.", "checked": True},
        {"label": "Owner: approve the terms.", "checked": False},
        {"label": "A plain-label blocker.", "checked": False},
    ]


def test_missing_audit_reports_evidence_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("NITE_DSP_ROOT", str(tmp_path))
    out = do.launch_tracker_status()
    assert "Evidence missing" in out
    assert "operations audit not found" in out


def test_status_report_counts_and_lists_open_launch_blockers(monkeypatch, tmp_path):
    monkeypatch.setenv("NITE_DSP_ROOT", str(tmp_path))
    audit = tmp_path / do.OPERATIONS_AUDIT_RELATIVE_PATH
    audit.parent.mkdir(parents=True, exist_ok=True)
    audit.write_text(FIXTURE_AUDIT)

    out = do.launch_tracker_status()
    assert "3 blockers tracked: 1 checked, 2 open." in out
    assert "Owner: approve the terms." in out
    assert "A plain-label blocker." in out
    assert "Monitoring" not in out
    assert "Source: remove an obsolete file" not in out
    assert "not an independent verification" in out


def test_missing_paid_sales_section_reports_evidence_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("NITE_DSP_ROOT", str(tmp_path))
    audit = tmp_path / do.OPERATIONS_AUDIT_RELATIVE_PATH
    audit.parent.mkdir(parents=True, exist_ok=True)
    audit.write_text("# Operations audit\n\n## Maintenance\n- [ ] unrelated\n")

    out = do.launch_tracker_status()
    assert "Evidence missing" in out
    assert "paid-sales section" in out
