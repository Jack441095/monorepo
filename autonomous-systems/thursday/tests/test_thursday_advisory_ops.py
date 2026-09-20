"""Tests for thursday/advisory_ops.py (Phase 3 -- backend advisory).

Schema is parsed live from backend/app/models.py (AST, no backend
import). Advice must cite live facts or name missing instrumentation --
never invent funnels or numbers.
"""

from __future__ import annotations

import thursday.ops.advisory_ops as adv


def test_schema_summary_lists_real_tables():
    schema = adv.schema_summary()
    assert schema["ok"] is True
    for expected in ("users", "purchases", "products", "waitlist_entries",
                     "contact_entries", "paraphrase_orders"):
        assert expected in schema["tables"], sorted(schema["tables"])
    assert schema["tables"]["users"]  # columns parsed, not just names
    assert "unavailable" in schema["counts"]  # no DB here: honest, not zero


def test_data_availability_is_honest_without_db_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    avail = adv.data_availability()
    assert "waitlist_entries" in avail["schema_tables"]
    assert "unavailable" in avail["live_counts"]
    assert "Plausible" in avail["traffic"]


def test_business_brief_uses_live_facts():
    brief = adv.business_brief()
    combined = " ".join(brief["facts"])
    assert "6 offerings" in combined or "offerings" in combined
    assert "38 pages" in combined
    assert "0.2.0" in combined
    assert "14 tables" in combined


def test_marketing_advice_pricing_cites_live_prices():
    out = adv.marketing_advice("pricing strategy")
    assert "£45-180" in out or ("£3" in out and "£180" in out)
    assert "0.2.0" in out
    assert "CANNOT ANSWER" in out


def test_marketing_advice_unknown_topic_refuses_to_guess():
    out = adv.marketing_advice("quantum billboard synergy")
    assert "No grounded recommendation" in out
    assert "CANNOT ANSWER" in out


def test_what_to_instrument_is_concrete():
    items = adv.what_to_instrument()
    assert len(items) >= 4
    combined = " ".join(items)
    assert "waitlist-submit" in combined
    assert "waitlist_entries" in combined
    assert "DATABASE_URL" in combined


def test_backend_counts_honest_without_reader(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    counts = adv.backend_counts()
    assert set(counts) == {"waitlist_entries", "contact_entries", "purchases", "paraphrase_orders"}
    assert all("unavailable" in str(v) and "credentials" in str(v) for v in counts.values())
    assert all(v != 0 for v in counts.values())  # never fake-zero


def test_backend_counts_live_with_injected_reader():
    store = {"waitlist_entries": [{}, {}, {}], "contact_entries": [{}],
             "purchases": [{}, {}], "paraphrase_orders": []}
    counts = adv.backend_counts(list_records=lambda table: store[table])
    assert counts == {"waitlist_entries": 3, "contact_entries": 1,
                      "purchases": 2, "paraphrase_orders": 0}


def test_backend_counts_failing_table_reports_honestly():
    def boom(table):
        raise RuntimeError("connection lost")
    counts = adv.backend_counts(list_records=boom)
    assert all("unavailable" in str(v) for v in counts.values())
