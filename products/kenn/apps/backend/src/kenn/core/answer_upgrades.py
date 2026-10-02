"""Offer a grounded model answer while its originating chat turn is still current.

The producer sees the template first. One model generation runs at a time under
the background timeout; a new turn or session clear discards its delivery without
pretending that the inference request has stopped. Enabled by KENN_LLM_BACKGROUND
and the chat model setting.
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from typing import Any, Callable

KEEP_SECONDS = 600
MAX_KEPT = 50
_LOCK = threading.Lock()
_BUSY = threading.Lock()
_RESULTS: dict[str, dict[str, Any]] = {}
_TURNS: dict[str, dict[str, Any]] = {}


def enabled() -> bool:
    from kenn.llm.llm_rewrite import is_enabled

    return os.environ.get("KENN_LLM_BACKGROUND", "").strip().lower() in {"1", "true", "yes", "on"} and is_enabled()


def _forget_old(now: float) -> None:
    for entries in (_RESULTS, _TURNS):
        for key in [k for k, v in entries.items() if now - v["at"] > KEEP_SECONDS]:
            del entries[key]
        while len(entries) > MAX_KEPT:
            del entries[min(entries, key=lambda k: entries[k]["at"])]


def _discard_session(session_id: str) -> None:
    for key in [k for k, v in _RESULTS.items() if v["session_id"] == session_id]:
        del _RESULTS[key]
    _TURNS.pop(session_id, None)


def invalidate(session_id: str) -> None:
    with _LOCK:
        _discard_session(session_id.strip())


def begin_turn(session_id: str) -> str:
    session_id = session_id.strip()
    turn_id = uuid.uuid4().hex
    with _LOCK:
        _forget_old(time.time())
        _discard_session(session_id)
        _TURNS[session_id] = {"id": turn_id, "at": time.time()}
        _forget_old(time.time())
    return turn_id


def _current_turn(session_id: str, turn_id: str) -> bool:
    return not turn_id or _TURNS.get(session_id, {}).get("id") == turn_id


def is_current_turn(*, session_id: str = "", turn_id: str = "") -> bool:
    with _LOCK:
        return _current_turn(session_id.strip(), turn_id)


def write_if_current(write: Callable[[], Any], *, session_id: str = "", turn_id: str = "") -> bool:
    """Persist a completed answer only while its originating turn still owns delivery.

    The callback must contain persistence, not retrieval or answer generation.
    Cancellation waits for an already-started save, including cache embedding,
    so validation and the write cannot race a new turn or session clear.
    """
    with _LOCK:
        if not _current_turn(session_id.strip(), turn_id):
            return False
        write()
        return True


def start(write: Callable[[], dict[str, Any]], *, session_id: str = "", turn_id: str = "") -> str | None:
    """Return a job id, or None if generation is busy or this request was superseded."""
    session_id = session_id.strip()
    with _LOCK:
        _forget_old(time.time())
        if not _current_turn(session_id, turn_id):
            return None
    if not _BUSY.acquire(blocking=False):
        log_outcome("busy", 0.0)
        return None
    upgrade_id = uuid.uuid4().hex[:16]
    with _LOCK:
        _forget_old(time.time())
        # A newer HTTP request can arrive while the older template is still being
        # built. It must also prevent that older request from starting a new job.
        if not _current_turn(session_id, turn_id):
            _BUSY.release()
            return None
        _RESULTS[upgrade_id] = {"status": "pending", "session_id": session_id, "at": time.time()}
        _forget_old(time.time())

    def run() -> None:
        started = time.perf_counter()
        entry = {"status": "rejected", "error": "Interrupted"}
        try:
            # The interactive LLM timeout is tuned for the ask path, where someone is watching a
            # spinner and needs a fast fallback. Inheriting it here meant this path could never win:
            # measured 1 Oct on the owner's M3, 0 of 30 upgrades were accepted, because a ~60 s
            # answer always hit the 20 s ceiling and `enhance()` returned None, so the swap offered
            # back the same template the producer was already looking at. The template is already on
            # screen by the time this thread runs, so there is nobody to fail fast for.
            from kenn.llm.llm_rewrite import background_budget

            with background_budget():
                payload = write()
            accepted = bool(payload.get("llm_enhanced"))
            entry = {"status": "accepted" if accepted else "rejected",
                     "answer": str(payload.get("answer") or "") if accepted else "",
                     "sources": payload.get("sources") if accepted else None}
        except Exception as exc:  # a model failure only means the template stands
            entry = {"status": "rejected", "error": type(exc).__name__}
        finally:
            entry.update(session_id=session_id, at=time.time(), seconds=round(time.perf_counter() - started, 1))
            with _LOCK:
                _forget_old(time.time())
                delivered = upgrade_id in _RESULTS
                if delivered:
                    _RESULTS[upgrade_id] = entry
                _BUSY.release()
        outcome = entry["status"] if "error" not in entry else "error"
        log_outcome(outcome if delivered else "expired", entry["seconds"] * 1000.0)

    threading.Thread(target=run, name=f"kenn-answer-upgrade-{upgrade_id}", daemon=True).start()
    return upgrade_id


def log_outcome(outcome: str, milliseconds: float) -> None:
    """One timing row per attempt, including answers discarded after a newer turn.

    Only the outcome and how long it took are kept, never the question or either answer.
    """
    try:
        from kenn.core import route_log

        route_log.record(f"answer_upgrade:{outcome}", milliseconds, brain=outcome == "accepted", proposal=False)
    except Exception:
        pass  # timing is diagnostic; it must never cost the answer


def get(upgrade_id: str, *, session_id: str = "") -> dict[str, Any]:
    with _LOCK:
        _forget_old(time.time())
        entry = _RESULTS.get(str(upgrade_id))
        if not entry or entry["session_id"] != session_id.strip():
            return {"status": "expired"}
        return {k: v for k, v in entry.items() if k not in {"at", "session_id"}}


__all__ = [
    "KEEP_SECONDS", "begin_turn", "enabled", "get", "invalidate", "is_current_turn",
    "log_outcome", "start", "write_if_current",
]
