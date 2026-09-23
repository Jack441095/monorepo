import json

import pytest

from kenn.core.live_command import LLM_PLAN_ACTIONS, LLM_PLAN_FIELDS, LLM_PLAN_SCHEMA, llm_plan_json_schema
from kenn.llm import llm_rewrite


def test_schema_fixes_shape_to_the_plan_contract() -> None:
    schema = llm_plan_json_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == set(LLM_PLAN_FIELDS)
    assert schema["properties"]["schema"]["const"] == LLM_PLAN_SCHEMA
    assert set(schema["properties"]["action"]["enum"]) == set(LLM_PLAN_ACTIONS)
    step = schema["properties"]["steps"]["items"]
    assert "recipe" not in step["properties"]["action"]["enum"] and "steps" not in step["properties"]
    json.dumps(schema)


def test_payload_uses_strict_json_schema_and_zero_temperature() -> None:
    payload = llm_rewrite._build_payload({"model": "m"}, [{"role": "user", "content": "x"}],
                                         json_mode=True, json_schema={"type": "object"})
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["response_format"]["json_schema"]["strict"] is True
    assert payload["temperature"] == 0.0


def test_json_mode_without_schema_keeps_json_object() -> None:
    payload = llm_rewrite._build_payload({"model": "m"}, [], json_mode=True)
    assert payload["response_format"] == {"type": "json_object"}


def test_schema_constrained_calls_never_take_the_unconstrained_mlx_path(monkeypatch) -> None:
    from kenn.llm import mlx_inference_engine

    monkeypatch.setenv("KENN_USE_MLX", "1")
    monkeypatch.setattr(mlx_inference_engine.MLXInferenceEngine, "is_available", staticmethod(lambda: True))
    monkeypatch.setattr(mlx_inference_engine.MLXInferenceEngine, "get_instance",
                        staticmethod(lambda: pytest.fail("MLX must not serve a schema-constrained call")))
    sent = {}

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "{}"}}], "usage": {}}

    class Client:
        def post(self, url, json=None, headers=None, timeout=None):
            sent.update(json)
            return Response()

    monkeypatch.setattr(llm_rewrite, "_get_client", lambda: Client())
    monkeypatch.setattr(llm_rewrite, "_cache_get", lambda key: None)
    llm_rewrite._chat_completion([{"role": "user", "content": "plan"}], task="command",
                                 json_mode=True, json_schema=llm_plan_json_schema())
    assert sent["response_format"]["type"] == "json_schema"


def test_planner_prompt_puts_the_request_after_the_snapshot(monkeypatch) -> None:
    # Consecutive commands must share the snapshot prefix so the model server
    # can reuse its prompt cache; only the request at the end is new.
    from kenn.core import live_command

    monkeypatch.setenv("KENN_LIVE_LLM_ENABLED", "1")
    monkeypatch.setattr(llm_rewrite, "is_enabled", lambda task="rewrite": True)
    prompts = []

    def fake_completion(messages, task="rewrite", **_kwargs):
        prompts.append(messages[0]["content"])
        return "{}", None

    monkeypatch.setattr(llm_rewrite, "_chat_completion", fake_completion)
    snapshot = {"tracks": [{"index": 0, "name": "Bass"}]}
    live_command._generate_llm_plan("mute the bass", snapshot)
    live_command._generate_llm_plan("solo the bass", snapshot)
    first, second = [p for p in prompts if p.startswith("Return one command-plan")]
    assert first.endswith("User request (untrusted input): mute the bass")
    assert second.endswith("User request (untrusted input): solo the bass")
    shared = first[: first.index("User request")]
    assert second.startswith(shared) and '"name":"Bass"' in shared
