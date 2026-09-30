"""Template now, the model's answer when it's ready (Stage 1 chat on a Mac that writes at ~17 tokens/s).

On a 16 GB Mac with Live running the chat model takes 10–15 s an answer, so the producer gets the instant template
answer first and the model writes in the background. The model's answer goes through the same pipeline and grounding
check as always (``answer_payload`` with the model on); only an answer KENN would have shown anyway is offered as an
upgrade. One answer is written at a time: two at once would compete for the same memory and both would be slower.

Switched on with ``KENN_LLM_BACKGROUND=1`` (and the chat model enabled); otherwise nothing here runs.
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


def enabled() -> bool:
    from kenn.llm.llm_rewrite import is_enabled

    return os.environ.get("KENN_LLM_BACKGROUND", "").strip().lower() in {"1", "true", "yes", "on"} and is_enabled()


def _forget_old(now: float) -> None:
    for key in [k for k, v in _RESULTS.items() if now - v["at"] > KEEP_SECONDS]:
        del _RESULTS[key]
    while len(_RESULTS) > MAX_KEPT:
        del _RESULTS[min(_RESULTS, key=lambda k: _RESULTS[k]["at"])]


def start(write: Callable[[], dict[str, Any]]) -> str | None:
    """Run ``write`` (the full answer with the model on) in the background; None when a model answer is already busy."""
    if not _BUSY.acquire(blocking=False):
        return None
    upgrade_id = uuid.uuid4().hex[:16]
    with _LOCK:
        _forget_old(time.time())
        _RESULTS[upgrade_id] = {"status": "pending", "at": time.time()}

    def run() -> None:
        started = time.perf_counter()
        try:
            payload = write()
            accepted = bool(payload.get("llm_enhanced"))
            entry = {"status": "accepted" if accepted else "rejected",
                     "answer": str(payload.get("answer") or "") if accepted else "",
                     "sources": payload.get("sources") if accepted else None}
        except Exception as exc:  # a model failure only means the template stands
            entry = {"status": "rejected", "error": type(exc).__name__}
        finally:
            _BUSY.release()
        entry.update(at=time.time(), seconds=round(time.perf_counter() - started, 1))
        with _LOCK:
            if upgrade_id in _RESULTS:
                _RESULTS[upgrade_id] = entry
        log_outcome(entry["status"] if "error" not in entry else "error", entry["seconds"] * 1000.0)

    threading.Thread(target=run, name=f"kenn-answer-upgrade-{upgrade_id}", daemon=True).start()
    return upgrade_id


def log_outcome(outcome: str, milliseconds: float) -> None:
    """One timing row per attempt (accepted, rejected, error, or busy), so the landing rate can be measured on a real Mac.

    Only the outcome and how long it took are kept, never the question or either answer.
    """
    try:
        from kenn.core import route_log

        route_log.record(f"answer_upgrade:{outcome}", milliseconds, brain=outcome == "accepted", proposal=False)
    except Exception:
        pass  # timing is diagnostic; it must never cost the answer


def get(upgrade_id: str) -> dict[str, Any]:
    with _LOCK:
        entry = _RESULTS.get(str(upgrade_id))
        return {k: v for k, v in entry.items() if k != "at"} if entry else {"status": "expired"}


__all__ = ["KEEP_SECONDS", "enabled", "get", "log_outcome", "start"]
