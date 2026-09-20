"""KENN routing language-robustness regression tests (2026-07-08).

Two related bugs made real production questions fall through to Thursday's
"Not sure I caught that" dead-end instead of reaching KENN:

  1. Plural production terms didn't match: `\\bkick\\b` matches "kick" but not
     "kicks", so "how do I process kicks?" classified as unknown. Fixed by
     allowing an optional plural suffix in the production keyword pattern.
  2. The regex keyword list can never cover every natural phrasing ("how do I
     make my mix louder", "help me with my mixdown", "what settings"). Since this
     is a studio assistant, the orchestrator now defaults leftover unknown/
     contextual questions to KENN (which abstains politely if off-topic) instead
     of the dead-end.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from thursday.intent import classify_intent  # noqa: E402
from thursday import orchestrator  # noqa: E402
from thursday.session_manager import get_or_create_session  # noqa: E402


def _intent(q: str) -> str:
    return classify_intent(q, {}).name


def test_plural_production_terms_are_production_qa() -> None:
    for q in ["process kicks", "compress the drums", "tune my vocals", "how do I process kicks?"]:
        assert _intent(q) == "production_qa", q


def test_singular_production_terms_still_work() -> None:
    for q in ["process a kick", "compress the drum", "tune my vocal"]:
        assert _intent(q) == "production_qa", q


def test_common_natural_production_phrasings_are_production_qa() -> None:
    for q in ["how do I make my mix louder", "help me with my mixdown", "can you help me mix",
              "my low end is weak", "how do I get a wider mix", "how do I use an lfo"]:
        assert _intent(q) == "production_qa", q


def test_business_queries_do_not_become_production() -> None:
    assert _intent("show my invoices") != "production_qa"
    assert _intent("how is business") != "production_qa"
    assert _intent("schedule a session") != "production_qa"
    assert _intent("whats my revenue") != "production_qa"


def _routes_to_kenn(q: str, monkeypatch) -> bool:
    """Run the real orchestrator with KENN stubbed; True if the query reached KENN."""
    reached = {"kenn": False}

    def fake_ask_kenn(text, fast=False):
        reached["kenn"] = True
        return f"KENN: {text}"

    monkeypatch.setattr(orchestrator.api, "ask_kenn", fake_ask_kenn)
    session = get_or_create_session(f"langtest-{abs(hash(q)) % 99999}")
    resp = orchestrator.handle(q, session, list_records=lambda _t: [])
    return reached["kenn"] or "Not sure I caught that" not in resp


def test_ambiguous_followups_reach_kenn_not_dead_end(monkeypatch) -> None:
    # These classify as unknown/contextual but must not hit "Not sure I caught that".
    for q in ["what settings", "can you explain more", "i need help with my song"]:
        assert _routes_to_kenn(q, monkeypatch), q
