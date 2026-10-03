"""Phase receipts must distinguish provider work, delivery and missing telemetry."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from scripts import measure_model_phases as tool


def test_prefill_and_decode_use_native_durations_instead_of_answer_latency():
    measured = tool.phases({"prompt_eval_duration_ns": 2_500_000_000,
                            "eval_duration_ns": 10_000_000_000,
                            "completion_tokens": 130, "latency_ms": 18000})
    assert measured["prefill_seconds"] == 2.5
    assert measured["decode_seconds"] == 10
    assert measured["decode_tokens_per_second"] == 13


@pytest.mark.parametrize("duration", [None, 0])
def test_interrupted_or_empty_decode_does_not_claim_zero_cost_or_infinite_speed(duration):
    measured = tool.phases({"completion_tokens": 0, "eval_duration_ns": duration})
    assert measured["prefill_seconds"] is None
    assert measured["decode_tokens_per_second"] is None


def test_never_attempted_rejected_and_failed_requests_still_count_against_the_gate():
    rows = [
        {"attempted": True, "accepted": True, "abstained": False, "seconds": 15, "error_type": None},
        {"attempted": True, "accepted": True, "abstained": False, "seconds": 15.01, "error_type": None},
        {"attempted": True, "accepted": False, "abstained": True, "seconds": 3, "error_type": None},
        {"attempted": False, "accepted": False, "abstained": False, "seconds": 1, "error_type": None},
        {"attempted": True, "accepted": True, "abstained": False, "seconds": 2, "error_type": "TimeoutError"},
    ]
    assert tool.gate_counts(rows)["fraction"] == 0.2
    assert tool.gate_counts(rows)["non_abstaining_fraction"] == 0.2
    assert tool.gate_counts(rows)["accepted_abstentions"] == 0
    assert tool.gate_counts([])["fraction"] is None
    assert tool.gate_counts([])["non_abstaining_fraction"] is None


@pytest.mark.parametrize("accepted", [False, True])
def test_payload_model_acceptance_is_counted_without_stream_validation_metadata(accepted):
    # Real payloads omit generation_validation, so the stream-only field lost every hit.
    usage = SimpleNamespace(task="rewrite", provider_attempted=True)
    outcome = tool.answer_outcome({"llm_enhanced": accepted}, [usage], "payload")
    assert outcome == {"attempted": True, "accepted": accepted, "abstained": False, "warnings": None}


def test_stream_rejection_overrides_the_provisional_llm_enhanced_flag():
    payload = {"llm_enhanced": True, "generation_validation": {
        "attempted": True, "accepted": False, "warnings": ["unsupported measurement"],
    }}
    assert not tool.answer_outcome(payload, [], "stream")["accepted"]
    assert not tool.answer_outcome({}, [SimpleNamespace(task="intent", provider_attempted=True)], "payload")["attempted"]


@pytest.mark.parametrize("surface", ["stream", "payload"])
@pytest.mark.parametrize("answer", [
    "Insufficient context: no evidence for this fact.",
    "Short answer:\n  insufficient CONTEXT: no evidence for this fact.",
    "Insufficient context:",
])
def test_accepted_abstentions_are_reported_separately_from_timely_explanations(surface, answer):
    # Grounding can accept a quick abstention even though it does not explain the requested concept.
    payload = {"answer": answer, "llm_enhanced": True,
               "generation_validation": {"attempted": True, "accepted": True}}
    row = {**tool.answer_outcome(payload, [], surface), "seconds": 2, "error_type": None}
    counts = tool.gate_counts([row])
    assert row["abstained"]
    assert counts["accepted_within_15_seconds"] == 1
    assert counts["accepted_abstentions"] == 1
    assert counts["accepted_non_abstaining_within_15_seconds"] == 0
    assert counts["non_abstaining_fraction"] == 0


def fake_llm():
    llm = SimpleNamespace()
    llm._build_native_ollama_payload = lambda messages=None, **kw: {
        "options": {"num_predict": 384}, "messages": messages or [],
    }
    llm._build_payload = lambda messages=None, **kw: {"max_tokens": 384, "messages": messages or []}
    llm.closed = False

    def streaming(messages, task="rewrite", **kwargs):
        llm.payload = llm._build_native_ollama_payload(messages)
        try:
            yield "first", None
            yield "second", None
        finally:
            llm.closed = True

    def completion(messages, task="rewrite", **kwargs):
        llm.payload = llm._build_native_ollama_payload(messages)
        llm.compatible = llm._build_payload(messages)
        return "answer", None

    llm.chat_completion_stream = streaming
    llm._chat_completion = completion
    return llm


def test_answer_cap_is_temporary_and_leaves_other_tasks_and_structured_plans_unchanged():
    llm = fake_llm()
    originals = vars(llm).copy()
    with tool.observe_generation(llm, 128):
        llm._chat_completion([], answer_mode="explanation")
        assert llm.payload["options"]["num_predict"] == 128
        assert llm.compatible["max_tokens"] == 128
        for task, kwargs in [("intent", {}), ("rewrite", {"json_schema": {}}),
                             ("rewrite", {"answer_mode": "action_preview"})]:
            llm._chat_completion([], task=task, **kwargs)
            assert llm.payload["options"]["num_predict"] == 384
    for key in ("_build_native_ollama_payload", "_build_payload", "chat_completion_stream", "_chat_completion"):
        assert getattr(llm, key) is originals[key]


def test_prefix_guard_close_preserves_partial_candidate_without_draining_the_provider():
    llm = fake_llm()
    with tool.observe_generation(llm, 128) as calls:
        generator = llm.chat_completion_stream([])
        assert next(generator) == ("first", None)
        generator.close()
        assert llm.closed
        assert calls[0]["candidate"] == "first"
        assert calls[0]["generation_ttft_seconds"] is not None
        assert llm._build_native_ollama_payload()["options"]["num_predict"] == 384


def test_baseline_leaves_the_provider_cap_and_payload_ttft_unchanged():
    llm = fake_llm()
    with tool.observe_generation(llm, None) as calls:
        llm._chat_completion([])
        assert llm.payload["options"]["num_predict"] == 384
        assert calls[0]["generation_ttft_seconds"] is None


@pytest.mark.parametrize("surface", ["stream", "payload"])
def test_brief_style_keeps_grounding_messages_and_token_ceiling_without_mutating_the_caller(surface):
    llm = fake_llm()
    messages = [{"role": "system", "content": "Keep every grounding rule."},
                {"role": "user", "content": "Question and full evidence."}]
    with tool.observe_generation(llm, None, answer_style="brief"):
        if surface == "stream":
            list(llm.chat_completion_stream(messages, answer_mode="explanation"))
        else:
            llm._chat_completion(messages, answer_mode="explanation")
            assert llm.compatible["messages"] == llm.payload["messages"]
            assert llm.compatible["max_tokens"] == 384
        assert llm.payload["options"]["num_predict"] == 384
        assert llm.payload["messages"][0] == messages[0]
        assert llm.payload["messages"][1]["content"] == messages[1]["content"] + "\n\n" + tool.BRIEF_STYLE
    assert messages[1]["content"] == "Question and full evidence."
    assert llm._build_native_ollama_payload(messages)["messages"] == messages


@pytest.mark.parametrize("task,kwargs", [("intent", {}), ("rewrite", {"json_mode": True}),
    ("rewrite", {"json_schema": {}}), ("rewrite", {"answer_mode": "action_receipt"})])
def test_brief_style_does_not_touch_other_tasks_or_action_and_structured_contracts(task, kwargs):
    llm = fake_llm()
    messages = [{"role": "user", "content": "Keep this contract."}]
    with tool.observe_generation(llm, None, answer_style="brief"):
        llm._chat_completion(messages, task=task, **kwargs)
        assert llm.payload["messages"] == messages
        assert llm.compatible["messages"] == messages


@pytest.mark.parametrize("abstained", [False, True])
def test_both_surfaces_measure_the_same_cases_and_keep_model_prose_only_in_scratch(tmp_path, monkeypatch, abstained):
    from kenn.llm import llm_rewrite as llm

    asked = []
    candidate = "Insufficient context: private candidate prose" if abstained else "private candidate prose"

    def completion(messages, task="rewrite", **kwargs):
        usage = llm.LLMUsage(prompt_tokens=1100, completion_tokens=130,
                             prompt_eval_duration_ns=2_000_000_000,
                             eval_duration_ns=10_000_000_000, provider_done=True)
        llm._add_usage(usage)
        return candidate, usage

    def ask(_chat, question, *, allow_llm, surface):
        asked.append((surface, question))
        answer, _usage = llm._chat_completion([])
        metadata = {"llm_enhanced": True} if surface == "payload" else {
            "generation_validation": {"attempted": True, "accepted": True},
        }
        return {"answer": answer, **metadata}, 0, None

    monkeypatch.setattr(llm, "_chat_completion", completion)
    monkeypatch.setattr(tool.latency, "_ask", ask)
    monkeypatch.setattr(tool, "mac_state", lambda: {"live_process_present": False})
    monkeypatch.setattr(tool, "_command", lambda *args: "test-commit")
    cases = [{"id": "first", "question": "first question"}, {"id": "second", "question": "second question"}]
    report = tool.measure(cases, tmp_path, None)
    assert asked == [(surface, case["question"]) for surface in ("stream", "payload") for case in cases]
    assert report["counts"]["stream"]["eligible"] == 2
    assert report["counts"]["payload"]["accepted_within_15_seconds"] == 2
    for surface in ("stream", "payload"):
        assert report["counts"][surface]["accepted_non_abstaining_within_15_seconds"] == (0 if abstained else 2)
        assert report["counts"][surface]["accepted_abstentions"] == (2 if abstained else 0)
    assert not report["release_gate_evaluated"]
    assert "private candidate prose" not in json.dumps(report)
    assert "private candidate prose" in (tmp_path / "answers.jsonl").read_text()
    assert report["rows"][0]["provider_calls"][0]["decode_tokens_per_second"] == 13
