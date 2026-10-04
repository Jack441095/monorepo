"""The route log says where a model call spent its time, so a slowdown can be pinned to load, prefill or decode."""

from __future__ import annotations

import json

from kenn.core import chat_answer, route_log
from kenn.llm import llm_rewrite


def _outcome_detail(tmp_path, monkeypatch, usage):
    log = tmp_path / "routes.jsonl"
    monkeypatch.setattr(route_log, "LOG", log)
    monkeypatch.setattr(llm_rewrite, "_global_usage", [usage] if usage else [])
    chat_answer._log_generation_outcome(True, {"warnings": []}, 9.0)
    return json.loads(log.read_text())["detail"]


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
    log = tmp_path / "routes.jsonl"
    monkeypatch.setattr(route_log, "LOG", log)
    monkeypatch.setattr(llm_rewrite, "_global_usage", [])
    chat_answer._log_generation_outcome(True, {"warnings": []}, 9.0)
    assert "detail" not in json.loads(log.read_text())
