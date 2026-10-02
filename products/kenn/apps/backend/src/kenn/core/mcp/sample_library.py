"""Local sample library search, analysis, and the confirmation-only import proposal.

Every handler here was lifted verbatim out of ``KennMCPFacade._dispatch``.
``facade`` is the facade that called it, so the injected client, coordinator,
and stores stay the single owner of Live and of the task ledger.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - import cycle broken for type checking only
    from kenn.core.mcp_facade import KennMCPFacade


def search_sample_library(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query", "")).strip()[:256]
    if not query:
        raise ValueError("query is required")
    limit = args.get("limit", 10)
    try:
        limit = max(1, min(50, int(limit)))
    except (TypeError, ValueError):
        limit = 10
    from kenn.core.sample_library import library_root, scan_sample_library, search_samples

    root = library_root()
    if root is None:
        return {
            "ok": False,
            "query": query,
            "results": [],
            "error": "No sample library is configured (KENN_SAMPLE_LIBRARY_ROOT is unset or not a directory).",
        }
    entries = scan_sample_library(root)
    results = search_samples(entries, query, limit=limit)
    return {
        "ok": True,
        "query": query,
        "results": [entry.payload() for entry in results],
        "total_indexed": len(entries),
        "advisory_only": True,
        "live_import_available": True,
        "live_import_notes": "Use import_sample_to_live for a confirmation-only proposal. Reliability depends on the sample's folder already being registered as a Place in Ableton (Live > Preferences > Library); a large, deeply-nested library is not yet reliably fast/correct to search.",
    }


def analyze_sample_library_entry(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    sample_id = str(args.get("sample_id", "")).strip()[:64]
    if not sample_id:
        raise ValueError("sample_id is required")
    from kenn.core.sample_library import (
        analyze_sample_audio,
        library_root,
        resolve_sample,
        scan_sample_library,
    )

    root = library_root()
    if root is None:
        return {
            "ok": False,
            "sample_id": sample_id,
            "error": "No sample library is configured (KENN_SAMPLE_LIBRARY_ROOT is unset or not a directory).",
        }
    entries = scan_sample_library(root)
    entry = resolve_sample(entries, sample_id)
    if entry is None:
        return {
            "ok": False,
            "sample_id": sample_id,
            "error": "No sample with that id was found in the configured library (run search_sample_library first).",
        }
    result, abstain_reason = analyze_sample_audio(root / entry.relative_path)
    if result is None:
        return {
            "ok": False,
            "sample_id": sample_id,
            "filename": entry.filename,
            "error": f"Analysis abstained: {abstain_reason}.",
        }
    return {
        "ok": True,
        "sample_id": sample_id,
        "filename": entry.filename,
        "measured": True,
        **result,
    }


def find_similar_samples(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    sample_id = str(args.get("sample_id", "")).strip()[:64]
    candidate_query = str(args.get("candidate_query", "")).strip()[:256]
    if not sample_id:
        raise ValueError("sample_id is required")
    if not candidate_query:
        raise ValueError("candidate_query is required")
    limit = args.get("limit", 10)
    try:
        limit = max(1, min(20, int(limit)))
    except (TypeError, ValueError):
        limit = 10
    from kenn.core.sample_embeddings import rank_by_similarity
    from kenn.core.sample_library import library_root, resolve_sample, scan_sample_library, search_samples

    root = library_root()
    if root is None:
        return {
            "ok": False,
            "sample_id": sample_id,
            "error": "No sample library is configured (KENN_SAMPLE_LIBRARY_ROOT is unset or not a directory).",
        }
    entries = scan_sample_library(root)
    target = resolve_sample(entries, sample_id)
    if target is None:
        return {
            "ok": False,
            "sample_id": sample_id,
            "error": "No sample with that id was found in the configured library (run search_sample_library first).",
        }
    candidates = [
        (entry.id, root / entry.relative_path)
        for entry in search_samples(entries, candidate_query, limit=25)
    ]
    ranked, reason = rank_by_similarity(root / target.relative_path, candidates, limit=limit)
    if ranked is None:
        return {
            "ok": False,
            "sample_id": sample_id,
            "error": f"Similarity search abstained: {reason}.",
        }
    by_id = {entry.id: entry for entry in entries}
    results = []
    for item in ranked:
        entry = by_id.get(item["sample_id"])
        if entry is None:
            continue
        results.append({**entry.payload(), "similarity": item["similarity"]})
    return {
        "ok": True,
        "sample_id": sample_id,
        "measured": True,
        "candidate_pool_size": len(candidates),
        "results": results,
        "advisory_only": True,
        "live_import_available": True,
        "live_import_notes": "Use import_sample_to_live for a confirmation-only proposal. Reliability depends on the sample's folder already being registered as a Place in Ableton (Live > Preferences > Library); a large, deeply-nested library is not yet reliably fast/correct to search.",
    }


def import_sample_to_live(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    sample_id = str(args.get("sample_id", "")).strip()[:64]
    session_id = str(args.get("session_id", "")).strip()[:128]
    track_name = str(args.get("track_name", "")).strip()[:256]
    if not sample_id or not session_id or not track_name:
        raise ValueError("sample_id, session_id, and track_name are required")
    payload = {
        "session_id": session_id,
        "track_index": args.get("track_index"),
        "track_name": track_name,
        "clip_slot_index": args.get("clip_slot_index"),
        "sample_id": sample_id,
    }
    result = facade.client.post("/api/ableton/sample-import/proposal", payload)
    if result.get("receipt") or result.get("changed") is True:
        raise RuntimeError("KENN returned a mutation from a proposal-only MCP call")
    return result
