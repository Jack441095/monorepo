"""Tests for thursday/finance_ops.py (Thursday Ops upgrade, phase 9).

Scoped to pricing only after finding "invoices" was already a registered
service backed by the real Admin agent (client.invoices_list()) -- a
second invoice reader would have duplicated existing functionality. See
the module docstring for the full reasoning.
"""

from __future__ import annotations

import json

import thursday.ops.finance_ops as fo


def test_get_offerings_returns_real_list_when_file_present():
    offerings = fo.get_offerings()
    assert len(offerings) > 0
    assert all("name" in o or "id" in o for o in offerings)


def test_get_offerings_empty_list_when_file_missing(monkeypatch):
    monkeypatch.setattr(fo, "_business_knowledge_path", lambda: None)
    assert fo.get_offerings() == []


def test_pricing_summary_reports_evidence_missing_when_no_data(monkeypatch):
    monkeypatch.setattr(fo, "_business_knowledge_path", lambda: None)
    out = fo.pricing_summary()
    assert "Evidence missing" in out


def test_pricing_summary_reflects_real_prices(monkeypatch, tmp_path):
    fixture = tmp_path / "business_knowledge.json"
    fixture.write_text(json.dumps({
        "offerings": [
            {"id": "test_service", "name": "Test Service", "price_from_gbp": 42, "turnaround": "1 day"},
        ],
    }))
    monkeypatch.setattr(fo, "_business_knowledge_path", lambda: fixture)
    out = fo.pricing_summary()
    assert "Test Service: from £42 — 1 day" in out
    assert str(fixture) in out


def test_pricing_summary_handles_missing_price_honestly(monkeypatch, tmp_path):
    fixture = tmp_path / "business_knowledge.json"
    fixture.write_text(json.dumps({"offerings": [{"id": "x", "name": "X"}]}))
    monkeypatch.setattr(fo, "_business_knowledge_path", lambda: fixture)
    out = fo.pricing_summary()
    assert "price not recorded" in out


def test_pricing_summary_never_fabricates_subscription_data():
    out = fo.pricing_summary()
    assert "SUBSCRIPTION/RECURRING COSTS: not tracked" in out
    assert "no data source exists" in out
