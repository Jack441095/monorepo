#!/usr/bin/env python3
"""Probe application admission in a fresh process without contacting a model.

Transport is stubbed, so overlap means concurrent provider requests, not parallel
inference inside Ollama. This does not measure latency or qualify the Live gate.
"""

from __future__ import annotations

import argparse
import json
import threading
from contextlib import contextmanager, nullcontext
from unittest.mock import patch

from kenn.core import answer_upgrades
from kenn.llm import llm_rewrite as llm


MESSAGES = [{"role": "system", "content": "Use the evidence."},
            {"role": "user", "content": "Explain compression."}]
CFG = {"provider": "ollama", "model": "kenn-brain-qwen3-8b",
       "base_url": "http://127.0.0.1:11434/v1", "timeout": 20, "api_key": ""}
REPLY = {"message": {"content": "Fixture"}, "done": True, "done_reason": "stop"}


class StubReply:
    def raise_for_status(self):
        pass

    def json(self):
        return REPLY

    def iter_lines(self):
        yield json.dumps(REPLY)


class HeldTransport:
    def __init__(self, *, serialize=False):
        self.started = threading.Event()
        self.foreground = threading.Event()
        self.release = threading.Event()
        self.lock = threading.Lock()
        self.gate = threading.Lock() if serialize else None
        self.active = 0
        self.peak = 0
        self.calls = []

    @contextmanager
    def request(self, **kwargs):
        if self.gate:
            self.gate.acquire()
        background = threading.current_thread().name.startswith("kenn-answer-upgrade-")
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
            self.calls.append({"owner": "background" if background else "foreground",
                               "stream": bool(kwargs["json"].get("stream")),
                               "think": kwargs["json"].get("think")})
        try:
            if background:
                self.started.set()
                if not self.release.wait(3):
                    raise TimeoutError("Admission probe did not release its transport")
            else:
                self.foreground.set()
            yield StubReply()
        finally:
            with self.lock:
                self.active -= 1
            if self.gate:
                self.gate.release()

    def post(self, *args, **kwargs):
        with self.request(**kwargs) as reply:
            return reply

    def stream(self, *args, **kwargs):
        return self.request(**kwargs)


def probe(surface: str, *, serialize_transport: bool = False, admit_local_requests: bool = True) -> dict:
    """Hold a background call while a foreground provider wrapper advances."""
    if surface not in {"payload", "stream"}:
        raise ValueError("Unknown surface")
    transport = HeldTransport(serialize=serialize_transport)
    errors = []
    finished = threading.Event()
    foreground_finished = threading.Event()
    background_workers = []

    def foreground():
        try:
            if surface == "stream":
                list(llm.chat_completion_stream(MESSAGES))
            else:
                llm.chat_completion(MESSAGES)
        except Exception as exc:
            errors.append(type(exc).__name__)
        finally:
            foreground_finished.set()

    def background():
        background_workers.append(threading.current_thread())
        try:
            llm.chat_completion(MESSAGES)
            return {"llm_enhanced": False}
        finally:
            finished.set()

    admission = llm._local_model_request if admit_local_requests else lambda provider: nullcontext()
    # Patch only in this standalone process: no cache, session, log or network writes.
    with patch.multiple(answer_upgrades, _LOCK=threading.Lock(), _BUSY=threading.Lock(),
                        _RESULTS={}, _TURNS={}, log_outcome=lambda *args: None), \
            patch.multiple(llm, config=lambda task="rewrite": CFG,
                           mlx_selected=lambda task: False, _get_client=lambda: transport,
                           _cache_get=lambda key: None, _cache_put=lambda *args: None,
                           _add_usage=lambda usage: None, _model_slot=threading.Lock(),
                           _local_model_request=admission), \
            patch.dict("os.environ", {"KENN_LLM_THINK": "off", "KENN_LIVE_BACKEND": "fake"}):
        job = answer_upgrades.start(background)
        worker = threading.Thread(target=foreground, name="kenn-admission-probe")
        try:
            if not job or not transport.started.wait(1):
                raise RuntimeError("Background fixture did not reach transport")
            second_blocked = answer_upgrades.start(lambda: {"llm_enhanced": False}) is None
            worker.start()
            foreground_finished.wait(0.25)
            entered_before_release = transport.foreground.is_set()
            finished_before_release = foreground_finished.is_set()
        finally:
            transport.release.set()
            if worker.ident is not None:
                worker.join(timeout=2)
            if not finished.wait(2):
                raise RuntimeError("Background fixture did not finish")
            for background_worker in background_workers:
                background_worker.join(timeout=2)
            if worker.is_alive() or any(item.is_alive() for item in background_workers):
                raise RuntimeError("Admission fixture did not finish")
        background_status = answer_upgrades.get(job)["status"]
    return {"surface": surface, "transport": "stubbed", "peak_provider_requests": transport.peak,
            "foreground_entered_before_background_release": entered_before_release,
            "foreground_finished_before_background_release": finished_before_release,
            "local_admission_enabled": admit_local_requests,
            "second_background_blocked": second_blocked, "background_status": background_status,
            "provider_calls": transport.calls, "foreground_errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-single-request", action="store_true")
    parser.add_argument("--without-admission", action="store_true",
                        help="Disable admission only in this offline probe as a counterfactual control")
    args = parser.parse_args()
    rows = [probe(surface, admit_local_requests=not args.without_admission) for surface in ("payload", "stream")]
    print(json.dumps({"kind": "offline_admission_probe", "latency_measured": False,
                      "rows": rows}, indent=2))
    if any(row["foreground_errors"] not in ([], ["LLMBusyError"])
           or row["background_status"] != "rejected" for row in rows):
        return 2
    return int(args.require_single_request and any(row["peak_provider_requests"] > 1 for row in rows))


if __name__ == "__main__":
    raise SystemExit(main())
