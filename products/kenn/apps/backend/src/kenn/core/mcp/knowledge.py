"""Grounded retrieval and the local pattern generator.

Every handler here was lifted verbatim out of ``KennMCPFacade._dispatch``.
``facade`` is the facade that called it, so the injected client, coordinator,
and stores stay the single owner of Live and of the task ledger.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - import cycle broken for type checking only
    from kenn.core.mcp_facade import KennMCPFacade


def ask_audio_engineering_question(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    question = str(args.get("question", "")).strip()[:2000]
    if not question:
        raise ValueError("question is required")
    session_id = str(args.get("session_id", "")).strip()[:128]
    plugin_session_id = str(args.get("plugin_session_id", "")).strip()[:128]
    mix_review_id = str(args.get("mix_review_id", "")).strip()[:128]
    request_payload = {"question": question, "session_id": session_id}
    if plugin_session_id:
        request_payload["plugin_session_id"] = plugin_session_id
    if mix_review_id:
        request_payload["mix_review_id"] = mix_review_id
    result = facade.client.post("/api/knowledge/ask", request_payload)
    response = {
        "ok": bool(result.get("ok")),
        "question": question,
        "answer": result.get("answer", ""),
        "found": bool(result.get("found")),
        "weak_match": bool(result.get("weak_match")),
        "confidence": result.get("confidence", "low"),
        "sources": result.get("sources", []),
    }
    if result.get("session_evidence"):
        response["session_evidence"] = result["session_evidence"]
    if result.get("plugin_evidence"):
        response["plugin_evidence"] = result["plugin_evidence"]
    if result.get("mix_review_evidence"):
        response["mix_review_evidence"] = result["mix_review_evidence"]
    if result.get("realtime_mix_comparison"):
        response["realtime_mix_comparison"] = result["realtime_mix_comparison"]
    return response


def kenn_search_knowledge(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    from kenn.core.chat_retrieval import search, load_chunks, load_terms
    query = str(args.get("query", ""))
    limit = int(args.get("limit", 3))
    chunks = load_chunks()
    terms = load_terms()
    raw_results = search(query, chunks, terms, limit=limit)
    return {
        "ok": True,
        "query": query,
        "results": [
            {
                "score": round(score, 2),
                "source": r.get("source"),
                "title": r.get("title"),
                "kind": r.get("kind"),
                "text_snippet": (r.get("text") or "")[:300],
            }
            for score, r in raw_results
        ],
    }


def kenn_generate_midi_pattern(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    from kenn.core.generative_midi import generate_chord_progression, generate_euclidean_rhythm, generate_drum_pattern
    ptype = str(args.get("pattern_type", "chords")).lower()
    if ptype == "chords":
        notes = generate_chord_progression(
            root=str(args.get("root", "C")),
            scale_name=str(args.get("scale", "minor")),
            progression=str(args.get("progression", "pop_i_v_vi_iv")),
        )
    elif ptype == "euclidean":
        notes = generate_euclidean_rhythm(
            hits=int(args.get("hits", 5)),
            steps=int(args.get("steps", 8)),
            pitch=int(args.get("pitch", 36)),
        )
    elif ptype == "drums":
        notes = generate_drum_pattern(
            genre=str(args.get("genre", "trap")),
            bars=int(args.get("bars", 2)),
        )
    else:
        raise ValueError(f"Unknown pattern_type: {ptype}")
    return {"ok": True, "pattern_type": ptype, "note_count": len(notes), "notes": notes}
