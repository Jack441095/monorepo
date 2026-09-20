"""KENN abstention regression tests (conversation audit P0, 2026-07-08).

KENN had no real abstention: `answer_payload("whats the capital of france")`
returned confidence=high with 3 sources, a fabricated audio-flavoured answer.
Root cause: `note_query_affinity`'s term overlap wasn't stopword-filtered, so a
single shared function word ("of", "me") produced a false-positive affinity
score, which let `results_are_weak`'s no-recognized-topic branch pass through.
Fixed by adding common function words to `STOPWORDS` (retrieval.py), which
`normalized_terms`/`tokenize` both use.

See docs/KENN_THURSDAY_CONVERSATION_AUDIT_2026-07-08.md for the full audit.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT / "studio" / "kenn") not in sys.path:
    sys.path.insert(0, str(ROOT / "studio" / "kenn"))

from kenn.core.chat_answer import answer_payload  # noqa: E402
from kenn.core.chat_retrieval import normalized_terms  # noqa: E402


def test_stray_function_words_no_longer_create_false_affinity() -> None:
    q = normalized_terms("whats the capital of france")
    title = normalized_terms("The Power of Minimalism")
    assert not (q & title), "shared stopword ('of') must not count as term overlap"

    q2 = normalized_terms("write me a poem about cats")
    title2 = normalized_terms("Feed Me Bass Resampling")
    assert not (q2 & title2), "shared stopword ('me') must not count as term overlap"


def test_off_topic_questions_abstain_with_low_confidence() -> None:
    for q in [
        "whats the capital of france",
        "write me a poem about cats",
        "give me relationship advice",
        "can you give me financial advice",
        "should I invest in stocks",
        "dating advice",
        "give me advice on career choices",
    ]:
        payload = answer_payload(q, limit=5, allow_llm=False)
        assert payload.get("confidence") == "low", q
        assert payload.get("weak_match") is True, q


def test_harmless_off_topic_chitchat_gets_a_real_reply_not_a_fabricated_answer() -> None:
    """"tell me a joke" used to fall through this same low-confidence
    abstention path; as of 2026-07-27 it's handled by an intentional
    conversational route (a real audio-engineer joke, no fake grounding) --
    a different, deliberately friendlier outcome than the "I don't know"
    factual-question case above, not a regression of it. What this test
    (and the module docstring's original incident) actually guards against
    is a *fabricated audio-flavoured answer with fake sources* -- that
    invariant still holds: sources stay empty and nothing here claims to be
    a grounded/researched answer.
    """
    payload = answer_payload("tell me a joke", limit=5, allow_llm=False)
    assert payload.get("route") == "conversation"
    assert payload.get("sources") == []


def test_real_production_questions_still_answer_confidently() -> None:
    for q in ["how do I process kicks", "how do I set up a soundbank in wwise",
              "how do I make my mix louder"]:
        payload = answer_payload(q, limit=5, allow_llm=False)
        assert payload.get("confidence") == "high", q
        assert payload.get("weak_match") is not True, q
        assert payload.get("sources"), q


def test_discount_questions_route_to_the_business_pricing_client_delivery_mode() -> None:
    """Regression (2026-08-02, live-tested): "can you give me a discount on
    mixing?" fell through to a generic mixing-workflow tutorial
    (route=production, answer_mode=mix_diagnosis) instead of
    business_pricing_query() routing it to client_delivery mode -- the
    existing, tested pathway with real scope-boundary business content
    (see tests/chat/test_chat_conversation.py's pricing-followup tests).
    Every other pricing word ("quote", "price", "rate", "cost", "charge")
    was already recognized; "discount" just wasn't in the set."""
    from kenn.core.chat_routing import business_pricing_query

    assert business_pricing_query("can you give me a discount on mixing?")
    assert business_pricing_query("do you offer any discounts on mastering?")
    # Still requires a mix/master/client-adjacent word -- a bare "discount"
    # with no production context stays a plain out-of-scope/weak-match case,
    # not a business-pricing one.
    assert not business_pricing_query("can you give me a discount?")
