"""Two bounds on a single answer: how many tokens it may emit, and how long it may take.

Caps (Phase 3, 2 Oct 2026). MAX_TOKENS_BY_MODE held only voice and command while
chat_constants.ANSWER_MODES is ten modes with no name in common, so all ten fell through to a
1200-token default -- four times the longest answer on record. The numbers below come from the 29
real captured answers: p50 173 words, p95 220, max 228, which at roughly 1.33 tokens per word is
p50 ~230, p95 ~293, max ~303. That distribution is why the general ceiling is 384 and not the
256 the old _clamped_max_tokens fallback returned: 256 sits below p95, so adopting it would have
truncated the top 10-15% of good answers mid-sentence to save latency the median never spends.

Deadline (Phase 3, 2 Oct 2026). httpx.Timeout(cfg["timeout"]) is a per-read budget. A model that
emits one line every few seconds meets it on every read and holds the request thread indefinitely,
so the streaming loop now also carries a wall-clock ceiling.
"""

import time

import pytest

from kenn.core.chat_constants import ANSWER_MODES
from kenn.llm import llm_rewrite

# 228 words, the longest of the 29 real answers, at ~1.33 tokens per word.
MEASURED_MAX_TOKENS = 303
# quick_fix and voice are held below that on purpose: their own mode instructions ask for a single
# concise paragraph, so a longer answer was already outside the contract the cap is enforcing.
SHORT_MODES = {"quick_fix", "voice"}
# The 1200 all ten modes used to fall through to. Kept as a name so the regression is readable.
UNREACHABLE_DEFAULT = 1200

MESSAGES = [
    {"role": "system", "content": "answer"},
    {"role": "user", "content": "How do I de-ess?"},
]


def _cfg(model: str = "kenn-brain-qwen3-8b", provider: str = "ollama", timeout: int = 20) -> dict:
    return {"provider": provider, "model": model, "base_url": "http://127.0.0.1:11434/v1",
            "timeout": timeout, "api_key": ""}


@pytest.mark.parametrize("mode", sorted(ANSWER_MODES))
def test_every_answer_mode_sends_its_own_cap_and_not_the_1200_default(mode) -> None:
    payload = llm_rewrite._build_payload(_cfg(), MESSAGES, answer_mode=mode)
    assert payload["max_tokens"] == llm_rewrite.MAX_TOKENS_BY_MODE[mode]
    assert payload["max_tokens"] < UNREACHABLE_DEFAULT


def test_the_default_cap_is_the_general_ceiling_and_no_longer_1200() -> None:
    # An unrecognised mode lands here, so this is the value that would have been 1200 for all ten.
    assert llm_rewrite.DEFAULT_MAX_TOKENS == 384
    assert llm_rewrite._build_payload(_cfg(), MESSAGES, answer_mode="")["max_tokens"] == 384


def test_the_eight_modes_expected_to_run_long_clear_the_measured_maximum() -> None:
    # The accuracy half of the cap. A ceiling under 303 cuts a real answer off mid-sentence, which is
    # the loss the old 256-token fallback was about to start causing.
    for mode in sorted(ANSWER_MODES - SHORT_MODES):
        assert llm_rewrite.MAX_TOKENS_BY_MODE[mode] >= MEASURED_MAX_TOKENS, mode


def test_the_two_short_modes_are_capped_below_the_measured_maximum_on_purpose() -> None:
    assert llm_rewrite.MAX_TOKENS_BY_MODE["quick_fix"] == 256
    assert llm_rewrite.MAX_TOKENS_BY_MODE["voice"] == 220
    # 256 tokens is ~192 words, which leaves the measured median of 173 words untouched and only clips
    # answers that were already ignoring "very concise, single-paragraph response".
    assert 256 * (173 / 228) < MEASURED_MAX_TOKENS


def test_native_ollama_payload_carries_the_same_cap_as_the_openai_one() -> None:
    # Two builders, one number: the streaming chat path goes to native /api/chat on every qwen3 model,
    # which is the route the owner's Mac actually takes.
    openai_payload = llm_rewrite._build_payload(_cfg(), MESSAGES, answer_mode="mix_diagnosis")
    native_payload = llm_rewrite._build_native_ollama_payload(_cfg(), MESSAGES, answer_mode="mix_diagnosis",
                                                              json_schema=None)
    assert native_payload["options"]["num_predict"] == openai_payload["max_tokens"] == 384


@pytest.mark.parametrize("mode", sorted(ANSWER_MODES | {"voice", "command", ""}))
def test_the_mlx_clamp_and_the_ollama_payload_read_one_table(mode) -> None:
    # The defect: _clamped_max_tokens was called only from the MLX branch, so the HTTP path that every
    # non-MLX call takes never saw a clamp at all. If these two ever disagree again the drift is back.
    assert llm_rewrite._clamped_max_tokens("rewrite", mode, 512) == llm_rewrite._build_payload(
        _cfg(), MESSAGES, answer_mode=mode)["max_tokens"]


# --- MLX: the clamp has to stay wired in, and the task bounds have to stay put ---------------


class _RecordingEngine:
    """Stands in for MLXInferenceEngine, recording the generation budget it was handed."""

    model_id = "kenn-mlx-test"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def format_chat_prompt(self, user_msgs, system_prompt=None) -> str:
        return " ".join(m["content"] for m in user_msgs)

    def generate(self, prompt, max_tokens=None, temperature=None) -> dict:
        self.calls.append({"max_tokens": max_tokens})
        return {"text": "A short answer.", "model": self.model_id}

    def stream_generate(self, prompt, max_tokens=None, temperature=None):
        self.calls.append({"max_tokens": max_tokens})
        yield "A short "
        yield "answer."


def _mlx_engine(monkeypatch) -> _RecordingEngine:
    from kenn.llm import mlx_inference_engine

    engine = _RecordingEngine()
    monkeypatch.setattr(llm_rewrite, "mlx_selected", lambda task: True)
    monkeypatch.setattr(mlx_inference_engine.MLXInferenceEngine, "is_available", staticmethod(lambda: True))
    monkeypatch.setattr(mlx_inference_engine.MLXInferenceEngine, "get_instance", staticmethod(lambda: engine))
    monkeypatch.setenv("KENN_LLM_CACHE", "0")
    return engine


def test_mlx_generation_still_receives_the_clamped_budget(monkeypatch) -> None:
    engine = _mlx_engine(monkeypatch)
    llm_rewrite._chat_completion(MESSAGES, task="rewrite", answer_mode="mix_diagnosis")
    assert engine.calls == [{"max_tokens": llm_rewrite._clamped_max_tokens("rewrite", "mix_diagnosis", 512)}]


def test_mlx_streaming_still_receives_the_clamped_budget(monkeypatch) -> None:
    engine = _mlx_engine(monkeypatch)
    list(llm_rewrite.chat_completion_stream(MESSAGES, "rewrite", answer_mode="deep_explanation"))
    assert engine.calls == [{"max_tokens": 384}]


@pytest.mark.parametrize("task,answer_mode,expected", [
    ("intent", "command", 64),            # a plan is a machine-readable contract
    ("confirm", "action_preview", 64),    # a confirmation prompt, likewise
    ("followups", "", 128),               # three follow-up questions
    ("paraphrase", "", 128),              # a rewritten note
    ("command", "command", 256),          # the prose cap, not the plan cap
])
def test_the_plan_and_short_task_bounds_are_unchanged(monkeypatch, task, answer_mode, expected) -> None:
    # None of these are answer lengths, so none of them move with the measured answer distribution.
    # The 64 bound is reached by task ("intent", "confirm") or by the action-preview modes, not by the
    # command *mode*: that one was 256 before this change and is still 256.
    engine = _mlx_engine(monkeypatch)
    llm_rewrite._chat_completion(MESSAGES, task=task, answer_mode=answer_mode)
    assert engine.calls == [{"max_tokens": expected}]


# --- Wall-clock deadline ----------------------------------------------------------------------


class _WireStream:
    """Base for the streaming fakes: the httpx response shape chat_completion_stream drives."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self) -> None:
        return None


# Native /api/chat streams one bare JSON object per line, with no `data:` prefix, and that is the
# route every qwen3 model takes -- including kenn-brain-qwen3-8b on the owner's Mac.
def _native_line(content: str) -> str:
    return '{"message":{"role":"assistant","content":"%s"},"done":false}' % content


class _DribblingStream(_WireStream):
    """Never finishes, and never stalls: one line every 10 ms for as long as anything lets it.

    The 200-line backstop is what makes the mutation check cheap. With the wall-clock deadline
    removed, the loop runs out of this generator's patience and fails in about two seconds instead of
    wedging the whole test run on a stream that never ends.
    """

    MAX_LINES = 200
    GAP_S = 0.01

    def __init__(self) -> None:
        self.lines_sent = 0

    def iter_lines(self):
        for _ in range(self.MAX_LINES):
            self.lines_sent += 1
            yield _native_line("tick ")
            time.sleep(self.GAP_S)
        raise AssertionError(f"still streaming after {self.MAX_LINES} lines: nothing stopped the loop")


class _SlowButFiniteStream(_WireStream):
    """A whole answer, dribbled out over 30 ms -- inside any sane deadline."""

    LINES = [
        _native_line("Cut 2 kHz"),
        _native_line(", 4 dB."),
        '{"done":true,"prompt_eval_count":2000,"eval_count":12}',
    ]

    def iter_lines(self):
        for line in self.LINES:
            time.sleep(0.01)
            yield line


class _RecordingClient:
    def __init__(self, stream) -> None:
        self._stream = stream
        self.sent: dict = {}

    def stream(self, method, url, **kwargs):
        self.sent.update(url=url, payload=kwargs.get("json"))
        return self._stream


def _offline_stream(monkeypatch, stream) -> None:
    # Pin the call to the HTTP path with an empty cache so these tests exercise the deadline and the
    # line parser, not MLX or an answer cached by an earlier run.
    monkeypatch.setenv("KENN_LLM_CACHE", "0")
    monkeypatch.setattr(llm_rewrite, "config", lambda task="rewrite": _cfg())
    monkeypatch.setattr(llm_rewrite, "mlx_selected", lambda task: False)
    monkeypatch.setattr(llm_rewrite, "_cache_get", lambda key: None)
    monkeypatch.setattr(llm_rewrite, "_get_client", lambda: _RecordingClient(stream))


def test_a_dribbling_stream_is_stopped_by_the_wall_clock_deadline(monkeypatch) -> None:
    # Every read here is 10 ms, twenty times inside the 20 s httpx budget, so nothing about this
    # stream is a timeout until the wall clock says so.
    stream = _DribblingStream()
    _offline_stream(monkeypatch, stream)
    seen: list[str] = []
    with llm_rewrite.stream_deadline(0.25):
        with pytest.raises(TimeoutError) as excinfo:
            for token, _usage in llm_rewrite.chat_completion_stream(MESSAGES, "rewrite", answer_mode="mix_diagnosis"):
                seen.append(token)
    # The deadline must read as a timeout, not as the cut-short-connection the broad handler would
    # otherwise report it as.
    assert not isinstance(excinfo.value, RuntimeError)
    assert "LLM stream timed out after 20s per read / 0.25s total" in str(excinfo.value)
    assert seen, "tokens produced before the deadline still reach the caller"
    assert stream.lines_sent < _DribblingStream.MAX_LINES


def test_a_stream_that_finishes_inside_the_deadline_is_untouched(monkeypatch) -> None:
    stream = _SlowButFiniteStream()
    _offline_stream(monkeypatch, stream)
    with llm_rewrite.stream_deadline(5.0):
        chunks = list(llm_rewrite.chat_completion_stream(MESSAGES, "rewrite", answer_mode="deep_explanation"))
    assert "".join(token for token, _ in chunks) == "Cut 2 kHz, 4 dB."
    assert chunks[-1][1] is not None, "the usage signal still closes the stream"


def test_the_default_deadline_is_three_times_the_per_read_budget(monkeypatch) -> None:
    monkeypatch.delenv("KENN_LLM_STREAM_DEADLINE", raising=False)
    # 20 s per read -> 60 s total on the ask path.
    assert llm_rewrite.resolve_stream_deadline(20) == 60.0
    # background_budget() above lifts the per-read budget to 120 s, and the total follows it, so the
    # background answer upgrade gets 360 s rather than inheriting the interactive ceiling.
    with llm_rewrite.background_budget(120):
        cfg_timeout = llm_rewrite.config("rewrite")["timeout"]
        assert cfg_timeout == 120
        assert llm_rewrite.resolve_stream_deadline(cfg_timeout) == 360.0


def test_the_deadline_is_configurable_by_env_and_by_context(monkeypatch) -> None:
    monkeypatch.setenv("KENN_LLM_STREAM_DEADLINE", "90")
    assert llm_rewrite.resolve_stream_deadline(20) == 90.0
    with llm_rewrite.stream_deadline(12.5):
        assert llm_rewrite.resolve_stream_deadline(20) == 12.5
    assert llm_rewrite.resolve_stream_deadline(20) == 90.0, "the context has to be released again"


def test_a_misspelt_deadline_override_stops_the_run_instead_of_falling_back(monkeypatch) -> None:
    # Same call resolve_context_chars() makes, and for the same reason: a typo in a measurement run
    # should fail that run, not quietly re-run it on the derived default and report a latency nobody
    # asked for.
    monkeypatch.setenv("KENN_LLM_STREAM_DEADLINE", "sixty seconds")
    with pytest.raises(ValueError):
        llm_rewrite.resolve_stream_deadline(20)
