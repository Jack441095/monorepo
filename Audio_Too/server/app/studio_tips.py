"""Public studio tips — retrieval-only answers from kenn."""

from __future__ import annotations

import sys
from pathlib import Path

import ableton_bridge

DISCLAIMER = (
    "Production guidance from your local approved notes and manuals — not a substitute for "
    "professional advice. Answers are retrieval-based (no cloud rewrite on this endpoint)."
)

LM_ROOT = Path(__file__).resolve().parent.parent.parent / "studio" / "kenn"
if str(LM_ROOT) not in sys.path:
    sys.path.insert(0, str(LM_ROOT))


def _dynamic_starter_extra() -> list[str]:
    """Recent dashboard/public questions and open LM gaps."""
    extra: list[str] = []
    try:
        import lm_gaps
        import tips_queries

        for gap in lm_gaps.list_gaps_filtered(status="open", limit=5):
            q = str(gap.get("question", "")).strip()
            if q:
                extra.append(q)
        for row in tips_queries.list_queries(limit=12):
            q = str(row.get("question", "")).strip()
            if q:
                extra.append(q)
    except OSError:
        pass
    return extra


def _lm_catalog() -> dict:
    from kenn.core.suggestions import catalog_payload, typeahead

    return {
        "starters": catalog_payload(extra=[])["starters"],
        "typeahead": typeahead,
    }


def safe_public_answer(payload: dict) -> dict:
    sources = [
        {
            "label": str(source.get("label") or source.get("title") or "Approved source")[:160],
            "kind": str(source.get("kind", "note"))[:40],
        }
        for source in (payload.get("sources") or [])[:5]
        if isinstance(source, dict)
    ]
    session = payload.get("session") if isinstance(payload.get("session"), dict) else {}
    return {
        "question": str(payload.get("question", ""))[:500],
        "answer": str(payload.get("answer", ""))[:20_000],
        "sources": sources,
        "found": bool(payload.get("found")),
        "confidence": str(payload.get("confidence", "low"))[:20],
        "source_quality": str(payload.get("source_quality", ""))[:40],
        "topics": [str(item)[:80] for item in (payload.get("topics") or [])[:12]],
        "related_questions": [str(item)[:500] for item in (payload.get("related_questions") or [])[:8]],
        "used_history": bool(payload.get("used_history")),
        "llm_enhanced": bool(payload.get("llm_enhanced")),
        "conversation_only": bool(payload.get("conversation_only")),
        "weak_match": bool(payload.get("weak_match")),
        "session": {"session_id": str(session.get("session_id", ""))[:80]} if session else {},
    }


def validate_question(payload: dict) -> str:
    if str(payload.get("company_website", "")).strip():
        raise ValueError("Invalid request.")
    question = str(payload.get("question", "")).strip()
    if len(question) < 3:
        raise ValueError("Question must be at least 3 characters.")
    if len(question) > 500:
        raise ValueError("Question must be 500 characters or fewer.")
    return question


def public_catalog() -> dict:
    catalog = _lm_catalog()
    return {
        "ok": True,
        "disclaimer": DISCLAIMER,
        "suggested_questions": catalog["starters"],
        "retrieval_only": True,
    }


def suggest_questions(query: str, *, limit: int = 8) -> dict:
    catalog = _lm_catalog()
    suggestions = catalog["typeahead"](query, limit=limit)
    return {"ok": True, "query": query, "suggestions": suggestions}


def ask_public(question: str, *, limit: int = 8, session_id: str = "") -> dict:
    payload = ableton_bridge.ask(
        question,
        limit=limit,
        history=None,
        allow_llm=False,
        channel="public_tips",
        session_id=session_id,
        allow_generation=False,
    )
    payload = safe_public_answer(payload)
    payload["disclaimer"] = DISCLAIMER
    payload["retrieval_only"] = True
    payload["cta"] = "enquiry" if payload.get("confidence") == "low" else "learn_more"
    return payload
