"""Tests for Thursday's business subagent name routing and prefix cleaning.

Verifies that queries addressing agents by name (e.g. "ask adam to", "adam,")
are correctly routed to the respective agent handlers and that prefix-cleaning
successfully strips out the conversational addressing headers.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from thursday.registry.handlers import (
    _clean_agent_request,
    _handle_admin_agent,
    _handle_marketing_agent,
    _handle_research_agent,
)


def test_clean_agent_request() -> None:
    # Test 'ask [name] to' prefix
    assert _clean_agent_request("ask adam to draft an invoice") == "draft an invoice"
    assert _clean_agent_request("ask mark to write outreach") == "write outreach"
    assert _clean_agent_request("ask rhianna to guide to compression") == "guide to compression"
    
    # Test '[name],' prefix
    assert _clean_agent_request("adam, create a client") == "create a client"
    assert _clean_agent_request("mark, draft a post") == "draft a post"
    assert _clean_agent_request("rhianna, guide to compression") == "guide to compression"
    
    # Test 'talk to [name] about' prefix
    assert _clean_agent_request("talk to adam about the new project") == "the new project"
    
    # Test '[name] ' prefix (no punctuation)
    assert _clean_agent_request("adam compose an email to Jordan") == "compose an email to Jordan"
    
    # Non-matching strings remain unchanged
    assert _clean_agent_request("draft an invoice for Sarah") == "draft an invoice for Sarah"


def test_handle_admin_agent_cleans_and_calls_api() -> None:
    calls = []

    class FakeApi:
        def admin_agent(self, subcommand: str, text: str) -> str:
            calls.append((subcommand, text))
            return "mocked admin output"

    reply = _handle_admin_agent(
        FakeApi(),
        "ask adam to draft an invoice for Sarah 4 hours vocal session at 45"
    )
    assert calls == [("invoice", "for Sarah 4 hours vocal session at 45")]
    assert reply == "mocked admin output"


def test_handle_marketing_agent_cleans_and_calls_api() -> None:
    calls = []

    class FakeApi:
        def marketing_agent(self, subcommand: str, text: str) -> str:
            calls.append((subcommand, text))
            return "mocked marketing output"

    reply = _handle_marketing_agent(
        FakeApi(),
        "ask mark to draft outreach for new client"
    )
    assert calls == [("outreach", "for new client")]
    assert reply == "mocked marketing output"


def test_handle_research_agent_cleans_and_calls_api() -> None:
    calls = []

    class FakeApi:
        def research_agent(self, subcommand: str, text: str) -> str:
            calls.append((subcommand, text))
            return "mocked research output"

    reply = _handle_research_agent(
        FakeApi(),
        "ask rhianna to guide to vocal compression"
    )
    assert calls == [("suggest", "guide to vocal compression")]
    assert reply == "mocked research output"


def test_agent_voices_resolved() -> None:
    from thursday.voice_output import AGENT_VOICES
    assert AGENT_VOICES["thursday"] == "af_heart"
    assert AGENT_VOICES["kenn"] == "am_onyx"
    assert AGENT_VOICES["adam"] == "am_adam"
    assert AGENT_VOICES["mark"] == "af_bella"
    assert AGENT_VOICES["rhianna"] == "am_michael"


def test_generate_agent_response_fallback() -> None:
    import os
    from Shared.kenn_bridge import generate_agent_response
    
    # Temporarily disable LLM in environment to trigger fast fallback
    old_val = os.environ.get("KENN_LM_ENABLED")
    os.environ["KENN_LM_ENABLED"] = "0"
    try:
        res = generate_agent_response("Admin / Assistant", "draft invoice", "rule", "template")
        assert res is None
    finally:
        if old_val is not None:
            os.environ["KENN_LM_ENABLED"] = old_val
        else:
            del os.environ["KENN_LM_ENABLED"]


def test_check_and_deliver_autonomous_flow() -> None:
    import os
    from Shared.draft_sender import check_and_deliver_autonomous
    
    # Mock data store callables
    records = []
    def list_records(table):
        if table == "clients":
            return [{"name": "Sarah", "email": "sarah@example.com"}]
        return records
    def add_record(table, r):
        r["id"] = "d1"
        records.append(r)
        return r
    def update_record(table, rid, updates):
        for r in records:
            if r.get("id") == rid:
                r.update(updates)
                
    draft = {"id": "d1", "recipient": "Sarah", "subject": "Test subject", "body": "Test body", "status": "Pending"}
    records.append(draft)
    
    # Set autonomous mode env
    old_auto = os.environ.get("AUDIO_TOO_AUTONOMOUS")
    os.environ["AUDIO_TOO_AUTONOMOUS"] = "1"
    
    try:
        # Mock queue_draft_delivery to prevent actual DB inserts during test
        import app.delivery_service
        orig_queue = app.delivery_service.queue_draft_delivery
        app.delivery_service.queue_draft_delivery = lambda req: (202, {"ok": True})
        
        # Mock process_one to prevent smtplib connection
        import app.delivery_worker
        orig_process = app.delivery_worker.process_one
        app.delivery_worker.process_one = lambda worker_id: None
        
        try:
            note = check_and_deliver_autonomous(draft, list_records, add_record, update_record)
            assert "Autonomous Mode" in note
            assert draft["status"] == "Approved"
            assert draft["recipient"] == "sarah@example.com"
        finally:
            app.delivery_service.queue_draft_delivery = orig_queue
            app.delivery_worker.process_one = orig_process
    finally:
        if old_auto is not None:
            os.environ["AUDIO_TOO_AUTONOMOUS"] = old_auto
        else:
            del os.environ["AUDIO_TOO_AUTONOMOUS"]

