"""Tests for thursday/funding_ops.py (Thursday Ops upgrade, phase 3).

Stricter contract than marketing_ops/advertising_ops: every quantitative
figure must be a live query result (or an honest "unavailable"), never a
default of 0 standing in for "couldn't check." No grant matching is
implemented at all -- confirmed with the founder 2026-09-02 that
fabricating grant program names/fit scores is worse than not having the
feature.
"""

from __future__ import annotations

import thursday.ops.funding_ops as fo


def test_get_live_traction_counts_reports_unavailable_when_app_db_unreachable(monkeypatch):
    # No app.db on the path (this test doesn't run inside the Flask app
    # process) -- must say "unavailable", never silently report 0.
    monkeypatch.setattr(fo, "_resolve_list_records", lambda: None)
    counts = fo.get_live_traction_counts()
    assert all(v == fo._UNAVAILABLE for v in counts.values())
    assert set(counts) == {"clients", "leads", "invoices", "enquiries", "expenses", "projects"}


def test_get_live_traction_counts_uses_real_list_records(monkeypatch):
    fake_data = {
        "clients": [{"id": 1}, {"id": 2}],
        "leads": [{"id": 1}],
        "invoices": [],
        "enquiries": [],
        "expenses": [],
        "projects": [],
    }
    monkeypatch.setattr(fo, "_resolve_list_records", lambda: lambda table: fake_data[table])
    counts = fo.get_live_traction_counts()
    assert counts["clients"] == 2
    assert counts["leads"] == 1
    assert counts["invoices"] == 0


def test_get_live_traction_counts_reports_unavailable_per_table_on_query_error(monkeypatch):
    def flaky(table):
        if table == "clients":
            raise RuntimeError("db locked")
        return []

    monkeypatch.setattr(fo, "_resolve_list_records", lambda: flaky)
    counts = fo.get_live_traction_counts()
    assert counts["clients"] == fo._UNAVAILABLE
    assert counts["leads"] == 0  # other tables still report real (zero) data


def test_report_says_not_ready_with_zero_traction(monkeypatch):
    monkeypatch.setattr(fo, "_resolve_list_records", lambda: lambda table: [])
    out = fo.funding_readiness_report()
    assert "Not ready" in out
    assert "zero clients, leads, invoices, or enquiries" in out


def test_report_never_claims_ready_with_zero_traction(monkeypatch):
    monkeypatch.setattr(fo, "_resolve_list_records", lambda: lambda table: [])
    out = fo.funding_readiness_report()
    assert "Ready for investment" not in out
    assert "Ready to fundraise" not in out


def test_report_reflects_real_traction_when_present(monkeypatch):
    fake_data = {
        "clients": [{"id": 1}], "leads": [], "invoices": [],
        "enquiries": [], "expenses": [], "projects": [],
    }
    monkeypatch.setattr(fo, "_resolve_list_records", lambda: lambda t: fake_data[t])
    out = fo.funding_readiness_report()
    assert "Clients: 1" in out
    assert "real recorded activity" in out
    assert "Not ready" not in out


def test_report_never_fabricates_grant_names_or_scores():
    out = fo.funding_readiness_report()
    assert "GRANT READINESS:" in out
    assert "Not assessed here" in out
    assert "founder/human research" in out
    # None of these should ever appear -- confirms no hardcoded program
    # names snuck into the fallback text.
    for forbidden in ("Innovate UK", "SBIR", "Horizon Europe", "SEIS", "EIS"):
        assert forbidden not in out


def test_report_does_not_invent_legal_or_team_facts():
    out = fo.funding_readiness_report()
    assert "LEGAL / TEAM / FUNDING HISTORY:" in out
    assert "Not determinable from this codebase" in out


def test_report_cites_source_docs_rather_than_duplicating_narrative(monkeypatch):
    monkeypatch.setattr(fo, "_resolve_list_records", lambda: lambda t: [])
    out = fo.funding_readiness_report()
    assert "docs/NITE_DSP_BUSINESS_PLAN_V1.md" in out
    assert "docs/NITE_SUBMIT_LAUNCH_TRUTH_SHEET.md" in out
    assert "docs/NITE_DSP_PORTFOLIO_READINESS_AUDIT_V1.md" in out
