import json

import pytest

from kenn.llm import llm_rewrite

CFG = {"model": "qwen2.5:1.5b"}
MESSAGES = [{"role": "system", "content": "planner"}, {"role": "user", "content": "Mute the drums."}]


def test_omitting_output_matches_an_explicit_empty_contract() -> None:
    assert llm_rewrite._cache_key(CFG, MESSAGES) == llm_rewrite._cache_key(CFG, MESSAGES, None)


def test_output_contract_separates_cached_answers() -> None:
    plain = llm_rewrite._cache_key(CFG, MESSAGES)
    json_mode = llm_rewrite._cache_key(CFG, MESSAGES, {"json_mode": True, "json_schema": None, "answer_mode": "command"})
    schema_a = llm_rewrite._cache_key(CFG, MESSAGES, {"json_mode": True, "json_schema": {"type": "object"},
                                                      "answer_mode": "command"})
    schema_b = llm_rewrite._cache_key(CFG, MESSAGES, {"json_mode": True, "json_schema": {"type": "array"},
                                                      "answer_mode": "command"})
    assert len({plain, json_mode, schema_a, schema_b}) == 4


@pytest.fixture
def cached_calls(monkeypatch, tmp_path):
    monkeypatch.setenv("KENN_LLM_CACHE", "1")
    monkeypatch.setenv("KENN_LLM_THINK", "off")
    monkeypatch.setattr(llm_rewrite, "_get_db_path", lambda: tmp_path / "llm_cache.db")
    monkeypatch.setattr(llm_rewrite, "mlx_selected", lambda task: False)
    cfg = {"provider": "ollama", "model": "kenn-brain-qwen3-8b",
           "base_url": "http://127.0.0.1:11434/v1", "timeout": 20, "api_key": ""}
    monkeypatch.setattr(llm_rewrite, "config", lambda task: dict(cfg))
    sent = []

    class Reply:
        def __init__(self, content):
            self.content = content

        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": self.content},
                    "choices": [{"message": {"content": self.content}}]}

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def iter_lines(self):
            return iter([
                json.dumps({"message": {"content": self.content}, "done": False}),
                json.dumps({"done": True}),
            ])

    class Client:
        def post(self, url, **kwargs):
            sent.append((url, kwargs["json"]))
            return Reply(f"response-{len(sent)}")

        def stream(self, method, url, **kwargs):
            return self.post(url, **kwargs)

    monkeypatch.setattr(llm_rewrite, "_get_client", lambda: Client())

    def call(surface, *, mode="general", task="rewrite"):
        if surface == "payload":
            return llm_rewrite._chat_completion(MESSAGES, task, answer_mode=mode)
        chunks = list(llm_rewrite.chat_completion_stream(MESSAGES, task, answer_mode=mode))
        return "".join(content for content, _ in chunks), chunks[-1][1]

    return call, cfg, sent


@pytest.mark.parametrize("first,second", [("payload", "payload"), ("stream", "stream"),
                                          ("payload", "stream"), ("stream", "payload")])
def test_short_answer_mode_never_replays_a_cached_general_answer(cached_calls, first, second):
    # Plain responses used to omit answer mode, so the 384-token answer bypassed a 256-token request.
    call, _, sent = cached_calls
    assert call(first)[0] == "response-1"
    content, usage = call(second, mode="quick_fix")
    assert content == "response-2" and not usage.cache_hit
    assert sent[-1][1]["options"]["num_predict"] == 256


@pytest.mark.parametrize("first,second", [("payload", "stream"), ("stream", "payload")])
def test_matching_answer_contract_reuses_cache_across_chat_surfaces(cached_calls, first, second):
    call, _, sent = cached_calls
    assert call(first)[0] == "response-1"
    content, usage = call(second)
    assert content == "response-1" and usage.cache_hit and not usage.provider_attempted
    assert len(sent) == 1


@pytest.mark.parametrize("field,value", [("provider", "other-provider"),
                                        ("base_url", "http://127.0.0.1:11435/v1")])
def test_same_model_alias_at_another_provider_or_endpoint_never_replays_an_answer(cached_calls, field, value):
    call, cfg, sent = cached_calls
    call("payload")
    cfg[field] = value
    content, usage = call("payload")
    assert content == "response-2" and not usage.cache_hit
    assert len(sent) == 2


@pytest.mark.parametrize("surface", ["payload", "stream"])
def test_another_task_does_not_inherit_a_cached_rewrite(cached_calls, surface):
    call, _, sent = cached_calls
    call(surface)
    content, usage = call(surface, task="followups")
    assert content == "response-2" and not usage.cache_hit
    assert len(sent) == 2


def test_cache_disabled_keeps_both_surfaces_on_the_provider(cached_calls, monkeypatch):
    call, _, sent = cached_calls
    call("payload")
    monkeypatch.setenv("KENN_LLM_CACHE", "0")
    assert call("payload")[0] == "response-2"
    assert call("stream")[0] == "response-3"
    assert len(sent) == 3
