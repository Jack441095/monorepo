"""Business pronoun/context carry regression tests (conversation audit P2, 2026-07-08).

"tell me about jordan" -> "show his invoices" -> "book him in tomorrow": the third
turn didn't reach an actual booking action. Two things were checked:

  1. Pronoun resolution itself: `resolve_request("book him in tomorrow",
     {"current_client": "jordan"})` already correctly resolved "him" -> "jordan"
     (this was never broken).
  2. Service selection: the resolved "book jordan in tomorrow" scored the generic
     calendar/agenda service over the "sessions" scheduling service, because
     "sessions" had no standalone "book" trigger and didn't share the
     calendar_scheduling intent — so it never got to the actual booking handler.

Fixed by adding a "book" trigger to the sessions ServiceDef and including
calendar_scheduling in its intents, so an informal "book <name> in <time>" reaches
the real Sessions/scheduling action instead of a non-actionable agenda view.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from thursday.resolver import resolve_request  # noqa: E402
from thursday import orchestrator  # noqa: E402
from thursday.session_manager import get_or_create_session  # noqa: E402


def test_pronoun_resolves_to_current_client() -> None:
    text, entities = resolve_request("book him in tomorrow", {"current_client": "jordan"})
    assert text == "book jordan in tomorrow"
    assert entities.get("current_client") == "jordan"


def test_multiturn_booking_reaches_sessions_not_kenn_or_generic_agenda(monkeypatch) -> None:
    kenn_hits = []

    def fake_ask_kenn(text, *a, **k):
        kenn_hits.append(text)
        return f"[KENN: {text[:30]}]"

    def fake_list_records(table: str) -> list[dict]:
        # _handle_client_info (thursday/registry/handlers.py) falls back to
        # KENN whenever the named client has zero records anywhere -- by
        # design, for a genuinely unknown name. An always-empty stub makes
        # turn 1 hit that fallback regardless of the context-carry behaviour
        # this test exists to check, so give "jordan" one real project.
        if table == "projects":
            return [{"client": "Jordan", "project": "EP Mix", "service": "Mixing", "status": "Open"}]
        return []

    monkeypatch.setattr(orchestrator.api, "ask_kenn", fake_ask_kenn)
    session = get_or_create_session("test-business-context-carry")

    orchestrator.handle("tell me about jordan", session, list_records=fake_list_records)
    orchestrator.handle("show his invoices", session, list_records=fake_list_records)
    reply = orchestrator.handle("book him in tomorrow", session, list_records=fake_list_records)

    assert not kenn_hits, "booking must not fall through to KENN"
    assert "agenda" not in reply.lower(), "must not fall back to the generic agenda view"
    assert "session" in reply.lower(), "must reach the Sessions scheduling action"
