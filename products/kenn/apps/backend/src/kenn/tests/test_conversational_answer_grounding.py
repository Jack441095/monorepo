"""The conversation route must never hand a producer model text it cannot back up.

Found 2 Oct 2026, four defects on the paths where generated prose reached the
producer without passing chat_grounding.generated_answer_validation:

1. core/chat_routing.conversational_payload called
   generate_conversational_llm_response(query, history=history) -- the query and
   the history, and not one retrieved note -- then returned the result as the whole
   answer at "confidence": "high" with "sources": [] and llm_enhanced True.
   should_use_llm_rewrite() refuses route == "conversation", so this was
   structurally the one route that could never reach the gate, and it is the first
   branch of the streaming path. Asking it for "thanks" produced a confident
   paragraph of unsolicited EQ advice invented from the base model's prior.
2. llm/llm_rewrite.llm_route_query posted unconditionally to
   {base_url}/chat/completions, the OpenAI-compatible route that ignores `think`.
   On kenn-brain-qwen3-8b, a reasoning model, the 20-token cap went into a thinking
   block, content came back empty, and the function returned None on every call.
3. llm/llm_rewrite.critique_answer returned {"passed": True} on any failure, so a
   self-critique that never ran was reported as a pass.
4. core/chat_formatting.weak_match_answer imported `llm_enabled` from llm_rewrite,
   which defines `is_enabled`. The ImportError was swallowed by the
   `except Exception: pass` directly underneath it, so that copy of the feature had
   never executed a single line.

Each test below names the guard, so removing it fails the test rather than quietly
restoring the old behaviour.
"""

from __future__ import annotations

import ast
import inspect
import io
import subprocess
import sys
import textwrap
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import httpx

from kenn.core.chat_formatting import weak_match_answer
from kenn.core.chat_routing import (
    CONVERSATIONAL_TEMPLATES,
    canned_response_index,
    conversational_intent,
    conversational_payload,
    conversational_reply,
)
from kenn.llm import llm_rewrite


def _canned_responses(query: str) -> list[str]:
    """Every line the conversation route can return for any intent."""
    return [line for lines in CONVERSATIONAL_TEMPLATES.values() for line in lines]


def test_thanks_returns_the_canned_line_and_never_llm_enhanced_prose() -> None:
    payload = conversational_payload("thanks")

    assert payload is not None
    assert payload["intent"] == "thanks"
    # The one flag a producer or a UI badge could read as "a model wrote this".
    assert payload["llm_enhanced"] is False
    # The answer is byte-identical to the deterministic template, not a paraphrase of it.
    assert payload["answer"] == conversational_reply("thanks", "thanks")
    assert payload["answer"] in _canned_responses("thanks")


def test_no_model_call_is_attempted_for_any_conversational_intent() -> None:
    # The real failure: the model was reached here. Patch the call site that used to
    # exist and assert nothing reaches it, whatever the environment says.
    with mock.patch.object(
        llm_rewrite,
        "generate_conversational_llm_response",
        side_effect=AssertionError("conversational route asked the model for prose"),
    ):
        for query in (
            "thanks",
            "thanks for that",
            "hey",
            "hello there",
            "how are you doing today",
            "help",
            "tell me a joke",
            "who are you",
        ):
            payload = conversational_payload(query)
            assert payload is not None, query
            assert payload["llm_enhanced"] is False, query
            assert payload["answer"] in _canned_responses(query), query


def test_conversational_answer_is_either_gated_or_a_deterministic_template() -> None:
    # The gate cannot pass an ungrounded conversational answer, which is the reason
    # the deterministic line is the answer and not a gated generation. If that ever
    # changes, this test says so out loud instead of leaving a silent hole.
    from kenn.core.chat_grounding import generated_answer_validation

    for query in ("thanks", "hey", "help", "tell me a joke", "who are you"):
        answer = conversational_reply(query, conversational_intent(query))
        verdict = generated_answer_validation(
            query,
            [],
            answer,
            route="conversation",
            confidence="high",
            answer_mode="studio_dialogue",
        )
        if verdict["accepted"]:
            continue
        # Rejected by the gate: fine, because the line is a fixed template in this
        # repository and not model output, so nothing ungrounded is asserted.
        assert answer in _canned_responses(query), query
        assert "weak grounding" in " ".join(verdict["warnings"]), query


def test_canned_line_survives_a_process_restart() -> None:
    # hash() on a str is randomised per interpreter by PYTHONHASHSEED, so the old
    # abs(hash(query)) % 4 gave the same "thanks" a different reply after every
    # restart. Two interpreters with different seeds must agree, across enough
    # queries that the two seeds cannot coincide on all of them by chance.
    probes = ("thanks", "hey", "how are you", "nice one", "cheers", "thanks a lot")
    src = (
        "from kenn.core.chat_routing import canned_response_index;"
        f"print([canned_response_index(probe, 4) for probe in {probes!r}])"
    )
    source_dir = str(Path(llm_rewrite.__file__).resolve().parents[2])
    outputs = []
    for seed in ("0", "12345", "99991"):
        proc = subprocess.run(
            [sys.executable, "-c", src],
            capture_output=True,
            text=True,
            check=True,
            env={
                "PATH": "/usr/bin:/bin",
                "PYTHONHASHSEED": seed,
                "PYTHONPATH": source_dir,
                "KENN_LIVE_BACKEND": "fake",
            },
        )
        outputs.append(proc.stdout.strip())
    assert outputs[0] == outputs[1] == outputs[2], outputs


def test_canned_response_index_is_pinned_to_a_digest_not_a_hash() -> None:
    # A range check would still pass with abs(hash(query)) % count behind it. Pin the
    # exact values: these are the first four bytes of the SHA-256 of the query, so any
    # move back to hash() changes them.
    assert [canned_response_index(q, 4) for q in ("thanks", "hey", "help", "what's up")] == [
        0,
        2,
        2,
        3,
    ]


def test_llm_route_query_uses_the_native_think_off_route_for_qwen3() -> None:
    # kenn-brain-qwen3-8b on Ollama. The OpenAI-compatible /chat/completions route
    # ignores `think`, so the model thought for the whole 20-token cap and returned
    # empty content; llm_route_query then returned None and route_query() fell
    # through to "unknown" without a word about it.
    posted: dict = {}

    def _post(url, json=None, headers=None, timeout=None):
        posted["url"] = url
        posted["json"] = json
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"message": {"content": "production"}}, request=request)

    env = {
        "KENN_LLM_ENABLED": "1",
        "KENN_LLM_PROVIDER": "ollama",
        "KENN_LLM_BASE_URL": "http://127.0.0.1:11434/v1",
        "KENN_LLM_MODEL": "kenn-brain-qwen3-8b",
    }
    with mock.patch.dict(llm_rewrite.os.environ, env, clear=False):
        with mock.patch.object(llm_rewrite, "_get_client", return_value=mock.Mock(post=_post)):
            assert llm_rewrite.llm_route_query("why does everything sound thin") == "production"

    assert posted["url"] == "http://127.0.0.1:11434/api/chat"
    assert posted["json"]["think"] is False
    assert posted["json"]["options"]["num_predict"] == 20


def test_llm_route_query_still_uses_chat_completions_for_non_thinking_providers() -> None:
    posted: dict = {}

    def _post(url, json=None, headers=None, timeout=None):
        posted["url"] = url
        request = httpx.Request("POST", url)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "game_audio"}}]}, request=request
        )

    env = {
        "KENN_LLM_ENABLED": "1",
        "KENN_LLM_PROVIDER": "openai",
        "KENN_LLM_API_KEY": "test-key",
        "KENN_LLM_BASE_URL": "https://api.openai.com/v1",
        "KENN_LLM_MODEL": "gpt-4o-mini",
    }
    with mock.patch.dict(llm_rewrite.os.environ, env, clear=False):
        with mock.patch.object(llm_rewrite, "_get_client", return_value=mock.Mock(post=_post)):
            assert llm_rewrite.llm_route_query("why does everything sound thin") == "game_audio"

    assert posted["url"] == "https://api.openai.com/v1/chat/completions"


def test_llm_route_query_does_not_return_none_in_silence() -> None:
    # A thinking-model payload on the OpenAI-compatible route returns empty content.
    # Returning None there is indistinguishable from "no model available", and
    # route_query() drops both into "unknown". The failure must be visible.
    def _post(url, json=None, headers=None, timeout=None):
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"choices": [{"message": {"content": ""}}]}, request=request)

    env = {
        "KENN_LLM_ENABLED": "1",
        "KENN_LLM_PROVIDER": "openai",
        "KENN_LLM_API_KEY": "test-key",
        "KENN_LLM_BASE_URL": "https://api.openai.com/v1",
        "KENN_LLM_MODEL": "gpt-4o-mini",
    }
    buf = io.StringIO()
    with mock.patch.dict(llm_rewrite.os.environ, env, clear=False):
        with mock.patch.object(llm_rewrite, "_get_client", return_value=mock.Mock(post=_post)):
            with redirect_stdout(buf):
                assert llm_rewrite.llm_route_query("why does everything sound thin") is None

    assert "llm_route_query" in buf.getvalue()
    assert "keyword routing" in buf.getvalue()


def test_critique_answer_fails_closed_when_the_model_raises() -> None:
    with mock.patch.object(
        llm_rewrite, "_chat_completion", side_effect=TimeoutError("LLM timed out after 20s")
    ):
        result = llm_rewrite.critique_answer("q", "a", "context", "past")

    assert result["passed"] is False
    assert result["warnings"], "a failed critique must say why it failed"
    assert "timed out" in " ".join(result["warnings"])


def test_critique_answer_fails_closed_on_unparseable_json() -> None:
    with mock.patch.object(llm_rewrite, "_chat_completion", return_value=("not json at all", None)):
        result = llm_rewrite.critique_answer("q", "a", "context", "past")

    assert result["passed"] is False
    assert result["warnings"]


def test_reflection_marks_the_answer_failed_when_the_critique_cannot_run() -> None:
    # The caller reads .get("passed", True), so a critique_answer that returned
    # passed=True on a timeout signed off an answer nobody had checked. End to end:
    # with KENN_CRITIQUE_LLM_ENABLED on and the model broken, the answer must fail.
    from kenn.knowledge.reflection import post_answer_critique

    with mock.patch.dict("os.environ", {"KENN_CRITIQUE_LLM_ENABLED": "1"}, clear=False):
        # reflection.py also checks is_enabled() before calling, so the gate has to be
        # satisfied for this branch to run at all.
        with mock.patch("kenn.llm.llm_rewrite.is_enabled", return_value=True):
            with mock.patch("kenn.llm.llm_rewrite._chat_completion", side_effect=RuntimeError("boom")):
                report = post_answer_critique(
                    "How much release on the sidechain?",
                    "Use 5 ms release at 4:1.",
                    [],
                    [],
                )

    assert report["passed"] is False
    assert any("self-critique did not run" in str(w) for w in report["warnings"]), report["warnings"]


def test_weak_match_answer_does_not_swallow_an_import_error_into_canned_banter() -> None:
    # The dead branch imported `llm_enabled`, which does not exist. The ImportError
    # was eaten by `except Exception: pass` on every single call, so the feature
    # looked alive in review and had never run.
    #
    # Parsed rather than grepped, because the comment above the return explains the
    # dead import and names it: a text search would match its own explanation.
    tree = ast.parse(textwrap.dedent(inspect.getsource(weak_match_answer)))
    assert not [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and (node.module or "").endswith("llm_rewrite")
    ], "weak_match_answer must not import llm_rewrite inside a try/except that hides the failure"
    assert not [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ExceptHandler)
    ], "weak_match_answer must not swallow exceptions; that is how the ImportError stayed invisible"
    # And the answer is stable for a given query, with the model switched on.
    first = weak_match_answer("what do you think about the mix")
    second = weak_match_answer("what do you think about the mix")
    assert first == second


def test_weak_match_answer_reports_a_broken_llm_module_instead_of_pretending() -> None:
    # Belt and braces for the same defect: even with the model advertised as enabled,
    # the answer is a fixed line and no model is called.
    env = {"KENN_LLM_ENABLED": "1", "KENN_LLM_PROVIDER": "ollama"}
    with mock.patch.dict(llm_rewrite.os.environ, env, clear=False):
        with mock.patch.object(
            llm_rewrite,
            "generate_conversational_llm_response",
            side_effect=AssertionError("weak_match_answer called the model"),
        ):
            answer = weak_match_answer("what do you think about the mix")
    assert isinstance(answer, str) and answer
    assert "Traceback" not in answer