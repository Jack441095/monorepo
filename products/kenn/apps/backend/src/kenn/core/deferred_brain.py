"""Template first, model answer when it's ready.

On a 16 GB Mac with Live open the local 8B takes 7-16 s to write an answer, and most of those answers still fail the
grounding check afterwards. So with KENN_CHAT_BRAIN_DEFERRED=1 the chat reply goes out at once with the template, and
the model's rewrite runs on one background worker. The page polls /kenn/api/ask/brain and swaps the text in only if the
rewrite passed the same validation as before. The worker is single on purpose: two 8B calls at once would starve Live.
"""

from __future__ import annotations

import contextvars
import os
import queue
import threading
import time
import uuid
from typing import Callable

MAX_JOBS = 64
MAX_QUEUED = 2
JOB_TTL_SECONDS = 300.0

_sink: contextvars.ContextVar[list | None] = contextvars.ContextVar("kenn_deferred_brain_sink", default=None)
_LOCK = threading.Lock()
_JOBS: dict[str, dict] = {}
_QUEUE: "queue.Queue[tuple[str, Callable[[], str | None]]]" = queue.Queue()
_worker: threading.Thread | None = None


def enabled() -> bool:
    return os.environ.get("KENN_CHAT_BRAIN_DEFERRED", "").strip().lower() in {"1", "true", "yes", "on"}


def begin() -> contextvars.Token:
    """Ask make_answer to hand its model step back instead of running it."""
    return _sink.set([])


def end(token: contextvars.Token) -> Callable[[], str | None] | None:
    """Stop collecting; return the deferred model step if make_answer produced one."""
    collected = _sink.get()
    _sink.reset(token)
    return collected[-1] if collected else None


def pending() -> bool:
    """Whether the request being answered has handed its model step back (so its template must not be cached as final)."""
    return bool(_sink.get())


def defer(step: Callable[[], str | None]) -> bool:
    """Called by make_answer at the point it would have run the model. False means run it inline."""
    collected = _sink.get()
    if collected is None:
        return False
    collected.append(step)
    return True


def submit(step: Callable[[], str | None]) -> str | None:
    """Queue a model step; None when the worker is already backed up (the template stands)."""
    _start_worker()
    with _LOCK:
        _drop_old()
        if sum(1 for job in _JOBS.values() if job["status"] in {"queued", "running"}) >= MAX_QUEUED:
            return None
        job_id = uuid.uuid4().hex[:12]
        _JOBS[job_id] = {"status": "queued", "answer": "", "created": time.time(), "ms": 0.0}
    _QUEUE.put((job_id, step))
    return job_id


def schedule(result: dict, step: Callable[[], str | None] | None) -> None:
    """Queue the model step for a reply and mark it `brain_pending`, if the reply is one the model may rewrite.

    Only a grounded knowledge answer waits: not a weak-match reply (its withheld text must stay), not one carrying a
    proposal (the page won't poll it). The rewrite is calibrated the same way the template was.
    """
    if (step is None or result.get("proposal") or result.get("weak_match")
            or result.get("confidence") not in {"high", "medium"}):
        return
    from kenn.core.chat_grounding import calibrate_answer_for_grounding

    grounding = result.get("grounding") or {}

    def rewrite_then_calibrate() -> str | None:
        text = step()
        return calibrate_answer_for_grounding(text, grounding) if text else text

    job_id = submit(rewrite_then_calibrate)
    if job_id:
        result["brain_pending"] = {"job_id": job_id}


def status(job_id: str) -> dict:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return {"status": "unknown"}
        result = {"status": job["status"], "ms": round(job["ms"], 1)}
        if job["status"] == "ready":
            result["answer"] = job["answer"]
        return result


def _drop_old() -> None:
    now = time.time()
    for job_id in [j for j, job in _JOBS.items() if now - job["created"] > JOB_TTL_SECONDS]:
        del _JOBS[job_id]
    while len(_JOBS) > MAX_JOBS:
        del _JOBS[next(iter(_JOBS))]


def _start_worker() -> None:
    global _worker
    with _LOCK:
        if _worker is not None and _worker.is_alive():
            return
        _worker = threading.Thread(target=_run, name="kenn-deferred-brain", daemon=True)
        _worker.start()


def _run() -> None:
    while True:
        job_id, step = _QUEUE.get()
        with _LOCK:
            job = _JOBS.get(job_id)
            if job is None:
                continue
            job["status"] = "running"
        started = time.perf_counter()
        answer: str | None = None
        try:
            answer = step()
        except Exception:
            answer = None  # the template already went out; a failed rewrite just leaves it
        elapsed = (time.perf_counter() - started) * 1000
        with _LOCK:
            job = _JOBS.get(job_id)
            if job is not None:
                job["ms"] = elapsed
                job["status"] = "ready" if answer else "rejected"
                job["answer"] = answer or ""
        _log_outcome(elapsed, bool(answer))


def _log_outcome(elapsed_ms: float, used: bool) -> None:
    try:
        from kenn.core import route_log

        route_log.record("brain_deferred", elapsed_ms, brain=used, proposal=False)
    except Exception:
        pass  # timing is diagnostic
