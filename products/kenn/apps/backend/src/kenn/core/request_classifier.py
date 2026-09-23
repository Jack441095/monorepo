"""Recognise chat messages that are not requests, before knowledge retrieval.

Retrieval scores almost any sentence as a confident match, so narration such
as "Every change KENN makes is logged…" used to get an unrelated tutorial.
This stays deliberately narrow: first-person problem statements ("my vocals
are too quiet") and topic searches ("sidechain compression") are requests and
must keep reaching the knowledge chat.
"""

from __future__ import annotations

import re
from typing import Any

# Labels the KENN UI renders on cards and chips; typed back verbatim they are
# not questions.
_UI_LABELS = {
    "try this", "readback verified", "live 12 synced", "ready to apply", "reverted",
    "restored to original state", "proposal dismissed", "no changes made", "apply to live 12",
    "dismiss", "info", "high", "medium", "low",
}
_QUESTION_START = re.compile(
    r"^\s*(?:what|what's|whats|how|why|when|where|which|who|whose|can|could|would|should|is|are|"
    r"do|does|did|will|shall|may|might|have|has|any)\b",
    re.I,
)
_IMPERATIVE_START = re.compile(
    r"^\s*(?:please\s+)?(?:set|pan|focus|boost|cut|raise|lower|turn|make|add|insert|remove|delete|"
    r"undo|mute|unmute|solo|unsolo|show|tell|explain|help|check|analy[sz]e|describe|list|give|find|"
    r"suggest|compare|fix|create|generate|play|stop|start|rename|group|center|centre|teach)\b",
    re.I,
)
_FIRST_PERSON = re.compile(r"\b(?:i|i'm|im|i've|me|my|mine|we|we're|our|us)\b", re.I)
_ADDRESSED_TO_KENN = re.compile(r"^\s*(?:(?:hey|hi|ok(?:ay)?|yo)\s+kenn\b|kenn\s*[,:!-])", re.I)


def classify_non_request(text: str) -> str | None:
    """Return "ui_label", "narration", or None when the message is a request."""
    message = " ".join(str(text or "").split())
    lowered = message.casefold().rstrip(".!")
    if not message or "?" in message:
        return None
    if lowered in _UI_LABELS:
        return "ui_label"
    if _QUESTION_START.match(message) or _IMPERATIVE_START.match(message):
        return None
    if _ADDRESSED_TO_KENN.match(message) or _FIRST_PERSON.search(message):
        return None
    words = re.findall(r"[A-Za-z']+", message)
    if len(words) >= 6 and re.search(r"\bkenn\b", message, re.I):
        return "narration"
    return None


def non_request_reply(kind: str) -> dict[str, Any]:
    if kind == "ui_label":
        answer = (
            "That looks like a label from one of my cards rather than a request. "
            "Tell me what you'd like, for example \"How does my low end sound?\" or "
            "\"Pan the Synth hard left.\""
        )
    else:
        answer = (
            "Noted. When you want something, ask about the session or tell me what to change, "
            "for example \"What did you change?\" or \"Set Compressor Output to 3 dB on track 7.\""
        )
    return {
        "ok": True,
        "answer": answer,
        "route": "conversation",
        "answer_mode": "non_request",
        "non_request_kind": kind,
        "found": True,
        "confidence": "high",
        "source_quality": "not_needed",
        "sources": [],
        "changed": False,
    }


__all__ = ["classify_non_request", "non_request_reply"]
