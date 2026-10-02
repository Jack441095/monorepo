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


def test_prose_qwen3_calls_are_rerouted_too(monkeypatch) -> None:
    """A qwen3 chat answer must not think first, schema or no schema.

    This used to assert the opposite, and that was the defect: 1 Oct 2026 measured 24 of 30 questions coming
    back with an empty answer and ``finish_reason: length``, because the prose path took Ollama's
    OpenAI-compatible route, which ignores ``think``, and Qwen3 spent the whole cap inside a ``thinking`` block.
    KENN logged it as "generation returned no answer" and it read as a grounding failure.
    """
    monkeypatch.delenv("KENN_LLM_THINK", raising=False)
    assert llm_rewrite._ollama_think_off(_cfg("qwen3.5:4b"), None)
    assert not llm_rewrite._ollama_think_off(_cfg("qwen3.5:4b", provider="openai"), SCHEMA)


def test_kenns_own_curated_build_is_recognised_as_a_thinking_model(monkeypatch) -> None:
    """The name pattern has to match kenn-brain-qwen3-8b, which is the model the Mac actually runs.

    `(?:^|/)qwen3` looked equivalent and matched only stock names, so the fix was live on the GPU box and
    dead on the owner's machine.
    """
    monkeypatch.delenv("KENN_LLM_THINK", raising=False)
    for name in ("kenn-brain-qwen3-8b", "kenn-brain-qwen3-8b:latest", "kenn-brain-qwen3-4b"):
        assert llm_rewrite._ollama_think_off(_cfg(name), None), name


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


def test_think_off_also_covers_prose_answers_from_a_local_brain(monkeypatch) -> None:
    # Stage 1 (local Qwen brain): chat answers should not spend seconds thinking first.
    monkeypatch.setenv("KENN_LLM_THINK", "off")
    assert llm_rewrite._ollama_think_off(_cfg("qwen3:14b"), None)
    payload = llm_rewrite._build_native_ollama_payload(_cfg("qwen3:14b"), [{"role": "user", "content": "hi"}],
                                                       answer_mode="", json_schema=None)
    assert payload["think"] is False and "format" not in payload and payload["options"]["temperature"] == 0.35


# What native /api/chat puts on the wire with stream=true: one bare JSON object per line, no `data:`
# prefix, and the token counts only on the closing line.
NATIVE_STREAM_LINES = [
    '{"model":"kenn-brain-qwen3-8b","message":{"role":"assistant","content":"Cut 2 kHz"},"done":false}',
    '{"model":"kenn-brain-qwen3-8b","message":{"role":"assistant","content":", 4 dB."},"done":false}',
    '{"model":"kenn-brain-qwen3-8b","message":{"role":"assistant","content":""},"done":true,'
    '"prompt_eval_count":2000,"eval_count":12}',
]

OPENAI_STREAM_LINES = [
    'data: {"choices":[{"delta":{"content":"A full answer"}}]}',
    "data: [DONE]",
]


class _Stream:
    """Stands in for httpx's streaming response, replaying fixed wire lines."""

    def __init__(self, lines: list[str]) -> None:
        self._lines = lines

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self) -> None:
        return None

    def iter_lines(self):
        return iter(self._lines)


class _RecordingClient:
    def __init__(self, lines: list[str]) -> None:
        self._lines = lines
        self.sent: dict = {}

    def stream(self, method, url, **kwargs):
        self.sent.update(url=url, payload=kwargs.get("json"))
        return _Stream(self._lines)


def _streaming_call(monkeypatch, client, model: str) -> None:
    # Pin the call to the HTTP path with an empty cache so the test exercises the route and the
    # line parser, not MLX or a cached answer from an earlier run.
    monkeypatch.delenv("KENN_LLM_THINK", raising=False)
    monkeypatch.setenv("KENN_LLM_CACHE", "0")
    monkeypatch.setattr(llm_rewrite, "config", lambda task="rewrite": _cfg(model))
    monkeypatch.setattr(llm_rewrite, "mlx_selected", lambda task: False)
    monkeypatch.setattr(llm_rewrite, "_get_client", lambda: client)


def test_native_ollama_payload_honors_stream_true() -> None:
    # Native /api/chat only streams NDJSON lines when asked to, and the streaming chat path has no
    # other way to hand tokens to the caller as they arrive. The 1 Oct 2026 builder hardcoded False.
    payload = llm_rewrite._build_native_ollama_payload(_cfg("qwen3.5:4b"), [{"role": "user", "content": "hi"}],
                                                       stream=True, answer_mode="", json_schema=None)
    assert payload["stream"] is True and payload["think"] is False


def test_qwen3_stream_uses_native_route_with_thinking_off(monkeypatch) -> None:
    """Streaming chat answers have to reach the native route, the same as the non-streaming ones.

    Found 2 Oct 2026: interactive chat accepted 0 of 29 answers, one stream event and 0 content
    tokens each. The think-off fix from 1 Oct only moved _chat_completion, so every streaming call
    went to Ollama's OpenAI-compatible route, which ignores ``think``, and Qwen3 spent the whole
    token cap thinking and returned nothing.
    """
    client = _RecordingClient(NATIVE_STREAM_LINES)
    _streaming_call(monkeypatch, client, "kenn-brain-qwen3-8b")
    list(llm_rewrite.chat_completion_stream([{"role": "user", "content": "kick and bass fight"}], "rewrite"))
    assert client.sent["url"] == "http://127.0.0.1:11434/api/chat"
    assert client.sent["payload"]["think"] is False and client.sent["payload"]["stream"] is True


def test_native_stream_line_yields_content(monkeypatch) -> None:
    """A bare JSON line, not a `data:` frame, still has to reach the caller as a token.

    Reading only SSE frames here is what silently emptied every answer: the stream ran, produced
    zero chunks, and chat_answer fell back to the template.
    """
    client = _RecordingClient(NATIVE_STREAM_LINES)
    _streaming_call(monkeypatch, client, "kenn-brain-qwen3-8b")
    chunks = list(llm_rewrite.chat_completion_stream([{"role": "user", "content": "how do I de-ess?"}], "rewrite"))
    assert "".join(token for token, _ in chunks) == "Cut 2 kHz, 4 dB."
    usage = chunks[-1][1]
    assert (usage.prompt_tokens, usage.completion_tokens) == (2000, 12)


@pytest.mark.parametrize("model", ["gpt-oss:20b", "llama3.1:8b", "qwen2.5:7b-instruct"])
def test_non_qwen3_stream_still_uses_openai_compatible_route(monkeypatch, model) -> None:
    # Only thinking models move to the native route; everything else keeps the SSE frames it had.
    client = _RecordingClient(OPENAI_STREAM_LINES)
    _streaming_call(monkeypatch, client, model)
    chunks = list(llm_rewrite.chat_completion_stream([{"role": "user", "content": "how do I de-ess?"}], "rewrite"))
    assert client.sent["url"] == "http://127.0.0.1:11434/v1/chat/completions"
    assert "think" not in client.sent["payload"]
    assert [token for token, _ in chunks] == ["A full answer", ""]


def test_kenn_adds_the_sources_a_local_model_forgot() -> None:
    # An 8B answer with every section but "Sources:" used to be discarded for the template.
    results = [(9.0, {"source": "kick-bass-balance-phase.md", "text": "The overlap stacks kick and bass in the same band."}),
               (8.0, {"source": "kick-bass-balance-phase.md", "text": "Phase cancels the low end of a doubled kick."}),
               (7.0, {"source": "sidechain-compression.md", "text": "Key the compressor from the kick for a 4:1 dip."})]
    _block, shown = llm_rewrite.model_evidence(results, lambda chunk: chunk["source"])
    text = "Short answer: cut the overlap.\n\nTry this:\n1. Level-match.\n2. Check phase."
    fixed = llm_rewrite._with_sources(text, shown, lambda chunk: chunk["source"])
    assert fixed.endswith("Sources:\n- kick-bass-balance-phase.md\n- sidechain-compression.md")
    assert llm_rewrite.valid_structure(fixed)
    assert llm_rewrite._with_sources(fixed, shown, lambda chunk: chunk["source"]) == fixed
