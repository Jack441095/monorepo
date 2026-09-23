import pytest

from kenn.llm import llm_rewrite

SCHEMA = {"type": "object"}


def _cfg(model: str, provider: str = "ollama") -> dict:
    return {"provider": provider, "model": model, "base_url": "http://127.0.0.1:11434/v1", "timeout": 20,
            "api_key": ""}


@pytest.mark.parametrize("model", ["qwen3.5:4b", "qwen3:8b", "library/qwen3.5:2b", "QWEN3.5:4B"])
def test_qwen3_family_schema_calls_turn_thinking_off(monkeypatch, model) -> None:
    monkeypatch.delenv("KENN_LLM_THINK", raising=False)
    assert llm_rewrite._ollama_think_off(_cfg(model), SCHEMA)


@pytest.mark.parametrize("model", ["qwen2.5:7b-instruct", "phi4-mini:latest", "deepseek-r1:7b"])
def test_other_models_keep_the_openai_route(monkeypatch, model) -> None:
    monkeypatch.delenv("KENN_LLM_THINK", raising=False)
    assert not llm_rewrite._ollama_think_off(_cfg(model), SCHEMA)


def test_only_schema_calls_to_ollama_are_rerouted(monkeypatch) -> None:
    monkeypatch.delenv("KENN_LLM_THINK", raising=False)
    assert not llm_rewrite._ollama_think_off(_cfg("qwen3.5:4b"), None)
    assert not llm_rewrite._ollama_think_off(_cfg("qwen3.5:4b", provider="openai"), SCHEMA)


def test_env_override_forces_or_disables(monkeypatch) -> None:
    monkeypatch.setenv("KENN_LLM_THINK", "off")
    assert llm_rewrite._ollama_think_off(_cfg("kenn-planner-lora"), SCHEMA)
    monkeypatch.setenv("KENN_LLM_THINK", "on")
    assert not llm_rewrite._ollama_think_off(_cfg("qwen3.5:4b"), SCHEMA)


def test_native_call_sends_think_false_with_schema_and_parses_reply(monkeypatch) -> None:
    monkeypatch.delenv("KENN_LLM_THINK", raising=False)
    monkeypatch.setenv("KENN_LLM_CACHE", "0")
    monkeypatch.setattr(llm_rewrite, "config", lambda task="rewrite": _cfg("qwen3.5:4b"))
    sent = {}

    class Reply:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {"message": {"role": "assistant", "content": '{"action":"set_mute"}'},
                    "prompt_eval_count": 2000, "eval_count": 12}

    class Client:
        def post(self, url, json=None, **_kwargs):
            sent.update(url=url, payload=json)
            return Reply()

    monkeypatch.setattr(llm_rewrite, "_get_client", lambda: Client())
    content, usage = llm_rewrite._chat_completion([{"role": "user", "content": "mute the bass"}], task="command",
                                                  system_prompt="planner", answer_mode="command",
                                                  json_mode=True, json_schema=SCHEMA)
    assert sent["url"] == "http://127.0.0.1:11434/api/chat"
    assert sent["payload"]["think"] is False and sent["payload"]["format"] == SCHEMA
    assert sent["payload"]["options"]["temperature"] == 0.0
    assert sent["payload"]["options"]["num_predict"] == llm_rewrite.MAX_TOKENS_BY_MODE["command"]
    assert content == '{"action":"set_mute"}'
    assert (usage.prompt_tokens, usage.completion_tokens, usage.total_tokens) == (2000, 12, 2012)
