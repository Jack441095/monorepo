"""Tests for thursday/website_ops.py (Phase 2 -- website visibility).

All read-only live reads of the website/backend checkouts. No network,
no DB credentials. Live-DB assertions pin the HONEST status (unavailable
without DATABASE_URL), never fake counts.
"""

from __future__ import annotations

import thursday.ops.website_ops as wo


def test_site_map_lists_real_pages():
    site = wo.site_map()
    assert site["ok"] is True
    assert site["count"] > 10
    for expected in ("thursday", "pricing", "support"):
        assert expected in site["pages"], site["pages"]


def test_product_pricing_finds_pound_figures_with_citations():
    pricing = wo.product_pricing()
    assert pricing["ok"] is True
    figures = {f["figure"] for f in pricing["figures"]}
    # Prices move (this pinned £3; on 18 Oct 2026 the site lists £2 and £9),
    # so pin only that real pound figures are found, never a particular one.
    assert figures and all(f.startswith("£") for f in figures)
    assert all(f["source"] and ":" in f["source"] for f in pricing["figures"])


def test_pricing_check_compares_website_vs_truth_sheet():
    out = wo.pricing_check()
    assert any(f["figure"] in out for f in wo.product_pricing()["figures"])
    assert "0.2.0" in out  # truth-sheet beta, read live
    assert "Scope note" in out


def test_enquiry_surfaces_lists_routes_and_honest_db_status(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    surfaces = wo.enquiry_surfaces()
    assert surfaces["ok"] is True
    assert any("waitlist" in r for r in surfaces["website_api_routes"])
    assert "contact.py" in surfaces["backend_modules"]
    assert "waitlist.py" in surfaces["backend_modules"]
    assert "unavailable, not zero" in surfaces["live_db"]


def test_traffic_status_names_the_counter_and_any_custom_events():
    # Until 18 Oct 2026 this pinned a WaitlistSubmit event that the canonical
    # website has never had; it described the superseded root copy.
    traffic = wo.traffic_status()
    assert traffic["ok"] is True
    assert traffic["instrumented"] is True
    if traffic.get("custom_events"):
        assert "URL goals" in traffic["detail"]
    else:
        assert "plausible" in traffic["detail"]
        assert "no custom funnel events" in traffic["detail"]


def test_weekly_website_lines_never_raise():
    lines = wo.weekly_website_lines()
    assert 1 <= len(lines) <= 5
    assert all(isinstance(line, str) and line for line in lines)
