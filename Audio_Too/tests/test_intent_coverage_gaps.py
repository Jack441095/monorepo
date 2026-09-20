"""Intent coverage regression tests (conversation audit P1, 2026-07-08).

The conversation audit found five misroutes in a 45-query labelled corpus
(89% -> 100% after these fixes):

  - "how do I make my 808 hit harder"        -> unknown  (missing "808")
  - "how do I set up a soundbank in wwise"   -> unknown  (missing game-audio terms)
  - "my wwise event isnt playing in unity"   -> unknown  (missing game-audio terms)
  - "who are my leads"                       -> unknown  (client_mgmt pattern too narrow)
  - "make me a beat"                         -> unknown  (audio_generation broke on
                                                the "me" object pronoun)

Plus two informal phrasings found during the multi-turn probe that would have
fallen into the unknown->KENN default and gotten a confidently wrong answer:

  - "hows business" (no apostrophe)          -> unknown  (business_ops needed apostrophe)
  - "book him in tomorrow"                   -> unknown  (no session/meeting noun)

See docs/KENN_THURSDAY_CONVERSATION_AUDIT_2026-07-08.md for the full audit.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from thursday.intent import classify_intent  # noqa: E402


def _intent(q: str) -> str:
    return classify_intent(q, {}).name


def test_game_audio_and_modern_terms_are_production_qa() -> None:
    for q in ["how do I make my 808 hit harder",
              "how do I set up a soundbank in wwise",
              "my wwise event isnt playing in unity",
              "how do I configure an rtpc in fmod"]:
        assert _intent(q) == "production_qa", q


def test_informal_leads_query_is_client_mgmt() -> None:
    assert _intent("who are my leads") == "client_mgmt"


def test_audio_generation_survives_object_pronoun() -> None:
    assert _intent("make me a beat") == "audio_generation"
    assert _intent("generate us a loop") == "audio_generation"


def test_informal_business_status_without_apostrophe() -> None:
    assert _intent("hows business") == "business_ops"


def test_informal_booking_phrase_is_calendar_scheduling() -> None:
    assert _intent("book him in tomorrow") == "calendar_scheduling"
    assert _intent("book her in for friday") == "calendar_scheduling"
