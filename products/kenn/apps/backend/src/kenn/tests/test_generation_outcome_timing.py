"""The route log says where a model call spent its time, so a slowdown can be pinned to load, prefill or decode."""

from __future__ import annotations

import json
import threading

import pytest

from kenn.core import chat_answer, route_log
from kenn.llm import llm_rewrite


@pytest.fixture(autouse=True)
def _fresh_usage(monkeypatch):
    # Each test starts with no call on record anywhere: not in the global list, not on this thread.
    monkeypatch.setattr(llm_rewrite, "_global_usage", [])
    llm_rewrite.forget_thread_usage()


def _outcome_detail(tmp_path, monkeypatch, usage):
    log = tmp_path / "routes.jsonl"
    monkeypatch.setattr(route_log, "LOG", log)
    if usage:
        llm_rewrite._add_usage(usage)
    chat_answer._log_generation_outcome(True, {"warnings": []}, 9.0)
    return json.loads(log.read_text()).get("detail")


def test_a_slow_call_is_logged_with_load_prefill_and_decode_apart(tmp_path, monkeypatch):
    usage = llm_rewrite.LLMUsage(
        prompt_tokens=812, completion_tokens=128, completion_reason="length",
        load_duration_ns=100_000_000, prompt_eval_duration_ns=2_300_000_000,
        eval_duration_ns=7_100_000_000, prompt_eval_cached_count=0,
    )
    assert _outcome_detail(tmp_path, monkeypatch, usage) == [
        "load 0.1s prefill 2.3s 812tok cached 0 decode 7.1s 128tok stop=length"
    ]


def test_a_call_that_never_finished_says_how_it_ended(tmp_path, monkeypatch):
    usage = llm_rewrite.LLMUsage(status="timeout", latency_ms=14000)
    assert _outcome_detail(tmp_path, monkeypatch, usage) == ["call timeout 14000ms"]


def test_no_call_on_record_adds_no_detail(tmp_path, monkeypatch):
    assert _outcome_detail(tmp_path, monkeypatch, None) is None


def test_another_requests_call_is_not_logged_as_this_ones(tmp_path, monkeypatch):
    # Local calls share one model slot. A request refused as busy used to log the global newest record, which was
    # the call that held the slot: another chat's timing on this answer's row (11 Oct audit, item 2).
    llm_rewrite._add_usage(llm_rewrite.LLMUsage(status="busy", provider_attempted=False))
    other = llm_rewrite.LLMUsage(prompt_tokens=900, completion_tokens=128, load_duration_ns=0,
                                 prompt_eval_duration_ns=2_000_000_000, eval_duration_ns=6_000_000_000)
    worker = threading.Thread(target=llm_rewrite._add_usage, args=(other,))
    worker.start()
    worker.join()

    assert llm_rewrite._global_usage[-1] is other
    assert _outcome_detail(tmp_path, monkeypatch, None) == ["call busy 0ms"]


def test_an_earlier_answers_call_on_this_thread_is_not_reused(tmp_path, monkeypatch):
    # The terminal chat answers every question on one thread. make_answer() forgets the last call on entry, so an
    # answer that never reached the model logs nothing rather than the previous question's timing.
    llm_rewrite._add_usage(llm_rewrite.LLMUsage(status="completed", latency_ms=9000, eval_duration_ns=None))
    monkeypatch.setattr(chat_answer, "build_template_answer", lambda *a, **k: "Template.")
    monkeypatch.setattr(chat_answer, "results_are_weak", lambda *a: True)
    chat_answer.make_answer("question", [], allow_llm=True)

    assert _outcome_detail(tmp_path, monkeypatch, None) is None
