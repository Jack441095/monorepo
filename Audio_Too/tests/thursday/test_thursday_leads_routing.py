"""Regression: "who are my leads" must route to the Pipeline service, not
Client Info.

Live-tested 2026-08-03: Client Info's own triggers ("client", "who is",
"tell me about", ...) don't match "who are my leads" at all -- it was
winning purely on its client_mgmt intent-confidence bonus, since
score_by_triggers() gives 0 for a real trigger-word miss. The result was a
disambiguation prompt built for a specific-client lookup ("Which client?
Try 'tell me about Jordan'.") answering a plural, "list all of them"
question -- a genuinely confusing non-sequitur, not a helpful answer.

thursday/registry/business.py's Pipeline service gained "leads"/"my leads"
as explicit triggers, routing this to the funnel/bottleneck summary instead
-- the closest existing, actually useful answer. No dedicated "list leads
by name" handler exists yet; that's a separate, real feature gap, not
something this fix invents.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT / "studio" / "kenn") not in sys.path:
    sys.path.insert(0, str(ROOT / "studio" / "kenn"))

from thursday import client as api  # noqa: E402
from thursday import session_manager  # noqa: E402
from thursday.orchestrator import handle  # noqa: E402


def test_who_are_my_leads_routes_to_pipeline_not_client_info(monkeypatch, tmp_path):
    monkeypatch.setattr(session_manager, "SESSION_DIR", tmp_path / "sessions")
    monkeypatch.setattr(session_manager, "SESSION_FILE", tmp_path / ".session")
    monkeypatch.setattr(
        api, "pipeline_summary",
        lambda: "\U0001f4ca Pipeline Summary\n\n  Leads: 3 (2 new / 1 warm / 0 hot / 0 closed)",
    )

    def _fail_if_called(*a, **k):
        raise AssertionError("must not route to Client Info for a plural 'list all leads' question")

    monkeypatch.setattr(api, "client_summary", _fail_if_called)

    session = session_manager.get_or_create_session("test-leads-routing")
    result = handle("who are my leads", session=session, list_records=lambda _: [])

    assert "Which client?" not in result
    assert "Pipeline Summary" in result
    assert "Leads: 3" in result


def test_pipeline_summary_trigger_still_works(monkeypatch, tmp_path):
    """Regression guard: adding "leads" as a trigger must not break the
    existing, primary "pipeline summary" phrasing."""
    monkeypatch.setattr(session_manager, "SESSION_DIR", tmp_path / "sessions")
    monkeypatch.setattr(session_manager, "SESSION_FILE", tmp_path / ".session")
    monkeypatch.setattr(api, "pipeline_summary", lambda: "\U0001f4ca Pipeline Summary\n\n  Leads: 0")

    session = session_manager.get_or_create_session("test-pipeline-summary")
    result = handle("pipeline summary", session=session, list_records=lambda _: [])

    assert "Pipeline Summary" in result


def test_a_specific_client_lookup_still_routes_to_client_info(monkeypatch, tmp_path):
    """Regression guard: the new "leads" trigger must not steal a genuine
    specific-client question away from Client Info."""
    monkeypatch.setattr(session_manager, "SESSION_DIR", tmp_path / "sessions")
    monkeypatch.setattr(session_manager, "SESSION_FILE", tmp_path / ".session")
    monkeypatch.setattr(api, "client_summary", lambda *a, **k: "Client: Jordan\n  Status: Active")

    def _fail_if_called():
        raise AssertionError("must not route a specific-client question to Pipeline")

    monkeypatch.setattr(api, "pipeline_summary", _fail_if_called)

    session = session_manager.get_or_create_session("test-client-lookup")
    def mock_list_records(table):
        if table == "projects":
            return [{"client": "Jordan", "project": "EP Mix", "service": "Mixing", "status": "Open", "id": "p1"}]
        return []
    result = handle("tell me about Jordan", session=session, list_records=mock_list_records)

    assert "Client: Jordan" in result
