"""Keep explicit insert associations scoped to an owner and fresh topology.

AbletonOSC has no durable project/track ID. These short-lived declarations are
revision checks, not project identity; they never grant extra control authority.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from typing import Any

_bindings: dict[tuple[str, str], dict[str, Any]] = {}
_lock = threading.RLock()
_TTL_SECONDS = 300.0  # Reaffirm after five minutes; no bindings survive a companion restart.
_MAX_BINDINGS = 256  # Bound declarations independently of feature history.
_REQUEST = re.compile(r"^\s*(?:bind this insert to\s+(.+?)|unbind this insert)\s*[.!]?\s*$", re.I)


def wants_insert_binding(question: str) -> bool:
    """Recognise an explicit user declaration, never infer one from analysis."""
    return bool(_REQUEST.fullmatch(question))


def _revision(state: dict[str, Any], context: dict[str, Any]) -> str:
    tracks = [(t.get("index"), t.get("name")) for t in state.get("tracks", []) if isinstance(t, dict)]
    window = context.get("measurement_window") or {}
    # Mixer values do not invalidate an association; names/order, stream
    # generation and rate changes do. No project ID is invented.
    data = [tracks, context.get("conversation_id"), context.get("host_track_name"), context.get("sample_rate"), window.get("source_generation")]
    return hashlib.sha256(json.dumps(data, ensure_ascii=False).encode()).hexdigest()


def check_binding(owner: str, insert: str, state: dict[str, Any], context: dict[str, Any]) -> dict[str, Any] | None:
    """Return the current declaration, or a stale marker requiring re-binding."""
    with _lock:
        binding = _bindings.get((owner, insert))
        if binding is None:
            return None  # Unbound inserts retain the existing unique-host-name path.
        if (time.monotonic() - binding["created_at"] > _TTL_SECONDS or binding["revision"] != _revision(state, context)
                or context.get("analysed_samples", 0) < binding["sample_count"]):
            return {"stale": True}  # Keep the marker: do not silently fall back to name inference.
        return dict(binding)


def bound_insert_contexts(owner: str, state: dict[str, Any]) -> list[dict[str, Any]]:
    """Read only this owner's explicit, revision-checked insert declarations."""
    from kenn.plugin_handoff import live_context_summary

    with _lock:
        inserts = [insert for bound_owner, insert in _bindings if bound_owner == owner]
    result = []
    for insert in inserts:
        context = live_context_summary(insert)
        if not context or context.get("conversation_id", "") not in ("", owner):
            continue  # Expired or reassigned audio cannot identify this owner's paired source.
        binding = check_binding(owner, insert, state, context)
        if binding and not binding.get("stale"):
            result.append({"insert": insert, "binding": binding, "context": context})
    return result


def answer_insert_binding(question: str, *, owner: str, insert: str, state: dict[str, Any], context: dict[str, Any] | None, adapter: Any) -> dict[str, Any] | None:
    """Bind/unbind KENN metadata only; never call a Live setter or issue a card."""
    match = _REQUEST.fullmatch(question)
    if not match:
        return None  # Analysis and general dialogue retain their own routes.
    result = {"ok": True, "route": "live_insert_binding", "answer_mode": "live_analysis", "sources": [],
              "found": True, "confidence": "unknown", "requires_confirmation": False, "proposal": None, "confirmation_token": ""}
    key = (owner, insert)
    if match.group(1) is None:
        with _lock:
            _bindings.pop(key, None)
        return {**result, "answer": "Cleared this insert's explicit association. No Live settings changed."}
    if (not owner or not insert or state.get("status") != "connected" or not context
            or not context.get("freshness", {}).get("current_for_diagnosis") or not context.get("measurement_window")):
        # Binding needs both fresh topology and a generation-tagged running insert.
        return {**result, "answer": "Play this insert with continuous analysis enabled and Live connected, then say 'bind this insert to track 1' using its actual track number."}
    resolution = adapter.resolve("Analyse " + match.group(1), state, context.get("host_track_name", ""))
    target = resolution.get("target")
    if target is None:
        return {**result, "answer": resolution["reason"]}  # Multiple named targets need an explicit number.
    source = context.get("host_track_name", "")
    if source and source.casefold() != str(target["name"]).casefold():
        # A user declaration cannot override conflicting host evidence.
        return {**result, "answer": f"The host reports '{source}' for this insert. Place it on '{target['name']}' before binding."}
    binding = {"track_index": target["index"], "track_name": target["name"], "revision": _revision(state, context),
               "sample_count": context["analysed_samples"], "created_at": time.monotonic()}
    with _lock:
        if key not in _bindings and len(_bindings) >= _MAX_BINDINGS:
            # Evict the oldest declaration rather than allowing unbounded owner state.
            _bindings.pop(min(_bindings, key=lambda k: _bindings[k]["created_at"]))
        _bindings[key] = binding
    return {**result, "confidence": "high", "binding": {"track_index": target["index"], "name": target["name"], "expires_in_seconds": _TTL_SECONDS},
            "answer": f"Associated this insert with track {target['index'] + 1} '{target['name']}' for this owner for five minutes. Names/order and audio-generation changes require re-binding. AbletonOSC supplies no durable project ID; re-bind after switching sets. No Live settings changed."}
