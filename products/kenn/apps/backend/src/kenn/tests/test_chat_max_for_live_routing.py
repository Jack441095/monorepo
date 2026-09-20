"""Regression coverage for a real routing gap found and fixed 2026-09-06.

"How do I use Max for Live devices?" used to route to "clarify" (a generic
intake prompt) instead of "ableton", because no topic in
``TOPIC_SYNONYMS`` (kenn.retrieval.retrieval) recognized "max for live" /
"m4l" / "amxd" phrasing at all -- retrieval itself already had a strong,
on-topic note once one was written; the gap was purely in topic
classification upstream of retrieval. This is a full-engine check (calling
``kenn.core.chat`` directly), not the narrower public "mix advice only"
surface in ``chat/app.py``, which applies its own separate, intentionally
stricter scope gate unrelated to this fix.
"""

from __future__ import annotations

from kenn.core.chat import answer_payload
from kenn.core.chat_routing import route_query


def test_max_for_live_query_routes_to_ableton_not_clarify() -> None:
    for question in (
        "How do I use Max for Live devices?",
        "How do I install a downloaded Max for Live device?",
        "What is Max for Live?",
    ):
        assert route_query(question, None) == "ableton", question


def test_max_for_live_query_is_answered_with_a_grounded_source() -> None:
    result = answer_payload("How do I use Max for Live devices?")
    assert result.get("found") is True
    assert result.get("weak_match") is not True
    sources = result.get("sources") or []
    assert sources
    assert any("max-for-live" in str(source.get("source", "")) for source in sources)
