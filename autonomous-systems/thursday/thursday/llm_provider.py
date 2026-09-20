"""Pluggable LLM provider abstraction for Thursday's brain.

`thursday/brain.py` previously called `audio_too.model_runtime.DEFAULT_LLM`
directly -- a single hard-coupled external singleton with no way to point
Thursday at a local OpenAI-compatible server, MLX-LM, or "no LLM at all"
without editing code. This module gives `decide()` a swappable provider
behind one `.generate(messages, *, timeout, response_schema=None)` call,
selected entirely by environment variables so the default behavior (use
audio_too's existing provider) is unchanged unless someone opts in.

Env vars:
  THURSDAY_LLM_PROVIDER        "audio_too" (default) | "openai_compat" |
                                "mlx_lm" | "none"
  THURSDAY_LLM_MODEL           model name (openai_compat) or repo id/path
                                (mlx_lm). Ignored by audio_too/none.
  THURSDAY_LLM_BASE_URL        base URL for openai_compat, default
                                "http://127.0.0.1:11434/v1" (Ollama's
                                OpenAI-compatible port, matching the default
                                already used by thursday/server.py).
  THURSDAY_LLM_TIMEOUT         default per-call timeout in seconds (10).
  THURSDAY_LLM_FALLBACK_MODEL  if the primary model errors, retry once with
                                this model on the same provider/server
                                before giving up. No effect on audio_too/none.
  THURSDAY_LLM_MAX_TOKENS      mlx_lm and openai_compat: generation cap
                                (default 768). Routing/planning decisions
                                are short JSON, not prose -- lowering this
                                cuts latency by bounding worst-case
                                generation length, at the risk of truncating
                                a genuinely long plan before it reaches
                                valid JSON. openai_compat had NO cap at all
                                before 2026-09-08 (unlike mlx_lm, which
                                always had one) -- found live when an
                                uncapped call to Ollama ran past 120s with
                                no natural stop.
  THURSDAY_LLM_ENABLE_THINKING tri-state (unset/"1"/"0"): whether to send
                                chat_template_kwargs: {"enable_thinking": ...}
                                to a reasoning-capable model (mlx_lm and
                                openai_compat both support this). Unset means
                                each provider's own default: mlx_lm defaults
                                to False (see MLXLMProvider's docstring --
                                Qwen3.5-4B burns its whole token budget on
                                chain-of-thought otherwise), openai_compat
                                defaults to not sending the field at all
                                (most OpenAI-compatible servers, Ollama
                                included, don't recognize it). Real-world
                                test against a vLLM-served Qwen3.5-27B-FP8:
                                a trivial request went from ~7s (full <think>
                                block) to ~2s (clean output) with this off.

Every provider raises `LLMUnavailable` (never a provider-specific exception)
on failure, so `brain.py`'s existing try/except-and-abstain fallback chain
in `decide()` keeps working unmodified regardless of which provider is
selected. Setting THURSDAY_LLM_PROVIDER=none is the rollback switch: it
forces every brain LLM call to fail fast into brain.py's deterministic
abstain path, with no network calls and no model load.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol


class LLMUnavailable(RuntimeError):
    """Raised by any provider when a generate() call cannot be completed.

    Callers (brain.py, etc.) should treat this uniformly regardless of which
    concrete provider raised it -- never branch on provider-specific errors.
    """


@dataclass
class GenerateResult:
    content: str
    latency_s: float = 0.0
    provider: str = ""
    model: str = ""


class LLMProvider(Protocol):
    name: str

    def generate(
        self, messages: list[dict[str, str]], *, timeout: float,
        response_schema: dict[str, Any] | None = None, json_mode: bool | None = None,
    ) -> GenerateResult: ...

    def health_check(self, timeout: float = 5.0) -> bool: ...

    def capabilities(self) -> dict[str, Any]: ...


# ─── audio_too (default, current production behavior) ──────────────────────


class AudioTooProvider:
    """Wraps the existing audio_too.model_runtime.DEFAULT_LLM singleton.

    This is the default provider so THURSDAY_LLM_PROVIDER unset -> byte-for-
    byte the same behavior brain.py had before this module existed.
    """

    name = "audio_too"

    def __init__(self, model: str | None = None, fallback_model: str | None = None):
        # audio_too's DEFAULT_LLM manages its own model selection internally;
        # model/fallback_model are accepted for interface uniformity but are
        # no-ops here, documented in capabilities().
        self._model = model
        self._fallback_model = fallback_model

    def _resolve(self):
        try:
            from audio_too.model_runtime import DEFAULT_LLM
        except ImportError as exc:
            raise LLMUnavailable(f"audio_too.model_runtime not installed: {exc}") from exc
        return DEFAULT_LLM

    def generate(
        self, messages: list[dict[str, str]], *, timeout: float,
        response_schema: dict[str, Any] | None = None, json_mode: bool | None = None,
    ) -> GenerateResult:
        t0 = time.perf_counter()
        # Only forward response_schema/json_mode when a caller actually
        # passed one -- brain.py always passes response_schema (even when
        # it's a real schema dict) and never json_mode; response_rewrite.py
        # always passes json_mode=False and never response_schema. Building
        # the kwargs conditionally reproduces each caller's original exact
        # DEFAULT_LLM.generate(...) invocation shape byte-for-byte, since
        # audio_too's real signature/defaults for these two kwargs together
        # aren't verifiable from this repo (audio_too isn't vendored here).
        call_kwargs: dict[str, Any] = {"timeout": timeout}
        if response_schema is not None:
            call_kwargs["response_schema"] = response_schema
        if json_mode is not None:
            call_kwargs["json_mode"] = json_mode
        try:
            result = self._resolve().generate(messages, **call_kwargs)
        except LLMUnavailable:
            raise
        except Exception as exc:
            raise LLMUnavailable(f"audio_too DEFAULT_LLM.generate failed: {exc}") from exc
        return GenerateResult(
            content=getattr(result, "content", "") or "",
            latency_s=time.perf_counter() - t0,
            provider=self.name,
            model=self._model or "audio_too:default",
        )

    def health_check(self, timeout: float = 5.0) -> bool:
        try:
            self._resolve()
            return True
        except LLMUnavailable:
            return False

    def capabilities(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "model": self._model or "audio_too:default (model selection owned by audio_too)",
            "supports_json_schema": True,  # brain.py already relies on this working
            "supports_tool_calls": False,
            "model_override_supported": False,
            "notes": "Delegates entirely to audio_too.model_runtime.DEFAULT_LLM; "
            "THURSDAY_LLM_MODEL/THURSDAY_LLM_FALLBACK_MODEL have no effect.",
        }


# ─── OpenAI-compatible local server (Ollama, LM Studio, vLLM, etc.) ─────────


class OpenAICompatProvider:
    """Talks to an OpenAI-compatible /chat/completions endpoint.

    Structured output support varies a lot by server/model in practice, so
    this does NOT assume response_format:json_schema works. It tries the
    schema-constrained request first; on any error plausibly caused by an
    unsupported response_format, it retries once as a plain chat completion
    with the schema appended to the prompt as an instruction, and lets the
    caller's own JSON parsing (brain.py already does this) handle the result.
    """

    name = "openai_compat"

    def __init__(self, model: str, base_url: str = "http://127.0.0.1:11434/v1", api_key: str = "",
                 fallback_model: str | None = None, enable_thinking: bool | None = None,
                 max_tokens: int = 768):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.fallback_model = fallback_model
        # Found live 2026-09-08: this provider never sent max_tokens at all
        # (unlike MLXLMProvider, which always has), so every call through
        # Ollama/any OpenAI-compatible server had UNBOUNDED output length --
        # a real specialist-execution call ran past 120s with no natural
        # stop before this was caught. Same THURSDAY_LLM_MAX_TOKENS default
        # (768) as MLXLMProvider, for consistency across providers.
        self.max_tokens = max_tokens
        # None (default) sends no chat_template_kwargs at all -- most
        # OpenAI-compatible servers (Ollama among them) don't recognize this
        # field and some reject unknown fields outright, so it's opt-in, not
        # assumed. Real-world test against a vLLM-served Qwen3.5-27B-FP8
        # found the same thinking-mode-burns-the-budget problem as MLX's
        # Qwen3.5-4B (see MLXLMProvider) -- a bare "ping" cost ~7s and a full
        # <think> block before a 2-word answer; passing
        # chat_template_kwargs: {"enable_thinking": false} (vLLM's standard
        # extension for Qwen-family chat templates) fixed it, dropping the
        # same request to ~2s with clean output.
        self.enable_thinking = enable_thinking
        self._schema_support: bool | None = None  # learned on first real call

    def _append_schema_instruction(self, messages: list[dict[str, str]], response_schema: dict[str, Any]) -> list[dict[str, str]]:
        # Appended as a trailing *user* turn, not a new system message: many
        # chat templates (Qwen's MLX template among them -- see MLXLMProvider)
        # require system to be the first message, so a system message tacked
        # on at the end raises at the tokenizer/template level. A trailing
        # user turn is the compatible-everywhere choice.
        schema = response_schema.get("schema", response_schema)
        instruction = (
            "Respond with ONLY a single valid JSON object (no prose, no markdown "
            f"fences) matching this JSON Schema:\n{json.dumps(schema)}"
        )
        return list(messages) + [{"role": "user", "content": instruction}]

    def _post(self, model: str, messages: list[dict[str, str]], timeout: float,
              response_format: dict[str, Any] | None) -> str:
        payload: dict[str, Any] = {
            "model": model, "messages": messages, "temperature": 0, "max_tokens": self.max_tokens,
        }
        if response_format is not None:
            payload["response_format"] = response_format
        if self.enable_thinking is not None:
            payload["chat_template_kwargs"] = {"enable_thinking": self.enable_thinking}
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}),
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.load(resp)
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise LLMUnavailable(f"openai_compat request to {self.base_url} failed: {exc}") from exc
        choices = body.get("choices") or []
        if not choices:
            raise LLMUnavailable(f"openai_compat response had no choices: {body!r}"[:300])
        return str((choices[0].get("message") or {}).get("content", ""))

    def _generate_once(self, model: str, messages: list[dict[str, str]], timeout: float,
                        response_schema: dict[str, Any] | None) -> str:
        if response_schema is None:
            return self._post(model, messages, timeout, None)
        if self._schema_support is not False:
            fmt = {"type": "json_schema", "json_schema": {
                "name": response_schema.get("name", "response"),
                "schema": response_schema.get("schema", response_schema),
            }}
            try:
                content = self._post(model, messages, timeout, fmt)
                self._schema_support = True
                return content
            except LLMUnavailable:
                self._schema_support = False  # this server/model doesn't take it; stop trying
        augmented = self._append_schema_instruction(messages, response_schema)
        return self._post(model, augmented, timeout, None)

    def generate(
        self, messages: list[dict[str, str]], *, timeout: float,
        response_schema: dict[str, Any] | None = None, json_mode: bool | None = None,
    ) -> GenerateResult:
        # json_mode is accepted for interface uniformity with AudioTooProvider
        # (response_rewrite.py's call site) but unused here: response_schema
        # already fully controls structured-vs-free-text output for this
        # provider, and json_mode=False (free text) is already the default
        # behavior when response_schema is None.
        t0 = time.perf_counter()
        try:
            content = self._generate_once(self.model, messages, timeout, response_schema)
            used_model = self.model
        except LLMUnavailable as first_err:
            if not self.fallback_model or self.fallback_model == self.model:
                raise
            content = self._generate_once(self.fallback_model, messages, timeout, response_schema)
            used_model = self.fallback_model
        return GenerateResult(content=content, latency_s=time.perf_counter() - t0,
                               provider=self.name, model=used_model)

    def health_check(self, timeout: float = 5.0) -> bool:
        try:
            req = urllib.request.Request(f"{self.base_url}/models")
            with urllib.request.urlopen(req, timeout=timeout):
                return True
        except (urllib.error.URLError, TimeoutError, OSError):
            return False

    def capabilities(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "model": self.model,
            "base_url": self.base_url,
            # Best-effort/unknown until a real call has been made; True means
            # a prior call's response_format:json_schema succeeded, False
            # means it was tried and rejected, None means not yet probed.
            "supports_json_schema": self._schema_support,
            "supports_tool_calls": False,  # not used by brain.py's decide(); not implemented here
            "model_override_supported": True,
            "fallback_model": self.fallback_model,
            "enable_thinking": self.enable_thinking,
            "max_tokens": self.max_tokens,
        }


# ─── MLX-LM (in-process, Apple Silicon local inference) ─────────────────────

_mlx_model_cache: dict[str, tuple[Any, Any]] = {}
_mlx_cache_lock = threading.Lock()


def _mlx_load(model_id: str):
    with _mlx_cache_lock:
        if model_id in _mlx_model_cache:
            return _mlx_model_cache[model_id]
        try:
            from mlx_lm import load
        except ImportError as exc:
            raise LLMUnavailable(f"mlx_lm not installed: {exc}") from exc
        try:
            model, tokenizer = load(model_id)
        except Exception as exc:
            raise LLMUnavailable(f"mlx_lm failed to load '{model_id}': {exc}") from exc
        _mlx_model_cache[model_id] = (model, tokenizer)
        return model, tokenizer


class MLXLMProvider:
    """In-process MLX-LM text generation.

    mlx_lm has no built-in grammar-constrained/JSON-schema decoding, so
    response_schema is enforced only via prompt instruction, same as the
    openai_compat fallback path -- capabilities() reports
    supports_json_schema=False so callers/benchmarks don't over-trust it.

    mlx_lm.generate() has no native timeout; `timeout` here is enforced
    by running generation on a worker thread and abandoning it (not
    killing it) on expiry -- documented as an unresolved risk, not
    silently pretended away. A hard `max_tokens` cap bounds how long an
    abandoned generation can run in the background.

    Concurrency is bounded (2026-09-18 audit fix): at most
    _MAX_CONCURRENT_GENERATIONS daemon worker threads may exist at once;
    beyond that generate() fails fast with LLMUnavailable("saturated")
    instead of queueing behind dead work forever (the old
    ThreadPoolExecutor(max_workers=2) let two abandoned generations
    permanently occupy both workers). Abandoned threads are daemonic so
    they can never block process exit; counters are visible in
    capabilities() for monitoring.
    """

    name = "mlx_lm"

    _MAX_CONCURRENT_GENERATIONS = 4

    def __init__(self, model: str, fallback_model: str | None = None, max_tokens: int = 768,
                 enable_thinking: bool = False):
        self.model = model
        self.fallback_model = fallback_model
        self.max_tokens = max_tokens
        # Real-world test against mlx-community/Qwen3.5-4B-MLX-4bit found it
        # is a thinking/reasoning model by default: it burns the entire
        # max_tokens budget on chain-of-thought prose before ever emitting
        # the requested JSON, so a low-latency structured brain-routing call
        # times out or truncates with no parseable output. Default to
        # non-thinking mode for brain-routing use; callers that want
        # reasoning for open-ended chat can pass enable_thinking=True.
        self.enable_thinking = enable_thinking
        self._gen_semaphore = threading.Semaphore(self._MAX_CONCURRENT_GENERATIONS)
        self._timeouts = 0
        self._saturated_rejections = 0

    def _format_prompt(self, tokenizer, messages: list[dict[str, str]], response_schema) -> str:
        msgs = list(messages)
        if response_schema is not None:
            # Trailing *user* turn, not a system message: real-world test
            # against mlx-community/Qwen3.5-4B-MLX-4bit found its chat
            # template raises ("System message must be at the beginning")
            # if a system message isn't first -- appending one at the end
            # broke every call. A trailing user turn works with every chat
            # template tried so far (see docs/LLM_PROVIDER_NOTES.md).
            schema = response_schema.get("schema", response_schema)
            msgs = msgs + [{
                "role": "user",
                "content": ("Respond with ONLY a single valid JSON object (no prose, no "
                            f"markdown fences) matching this JSON Schema:\n{json.dumps(schema)}"),
            }]
        if hasattr(tokenizer, "apply_chat_template") and getattr(tokenizer, "chat_template", None):
            try:
                return tokenizer.apply_chat_template(
                    msgs, tokenize=False, add_generation_prompt=True, enable_thinking=self.enable_thinking
                )
            except TypeError:
                # Chat template doesn't accept enable_thinking (non-reasoning model)
                return tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        return "\n\n".join(f"[{m.get('role', 'user')}] {m.get('content', '')}" for m in msgs)

    def _generate_once(self, model_id: str, messages: list[dict[str, str]], timeout: float,
                         response_schema: dict[str, Any] | None) -> str:
        model, tokenizer = _mlx_load(model_id)
        prompt = self._format_prompt(tokenizer, messages, response_schema)

        if not self._gen_semaphore.acquire(blocking=False):
            self._saturated_rejections += 1
            raise LLMUnavailable(
                f"mlx_lm saturated: {self._MAX_CONCURRENT_GENERATIONS} generations already "
                f"in flight (model '{model_id}'); failing fast instead of queueing behind "
                "work that may never finish"
            )
        box: dict[str, Any] = {}
        done = threading.Event()

        def _run() -> None:
            try:
                from mlx_lm import generate as mlx_generate
                box["value"] = mlx_generate(model, tokenizer, prompt=prompt,
                                            max_tokens=self.max_tokens, verbose=False)
            except Exception as exc:
                box["error"] = exc
            finally:
                done.set()

        worker = threading.Thread(target=_run, daemon=True,
                                  name="mlx-lm-gen")
        try:
            worker.start()
            if not done.wait(timeout=timeout):
                self._timeouts += 1
                raise LLMUnavailable(
                    f"mlx_lm generation exceeded {timeout}s timeout (model '{model_id}'); "
                    "note: the background generation was not killed, only abandoned "
                    "(daemon thread, bounded by the concurrency cap)"
                ) from None
        finally:
            self._gen_semaphore.release()
        if "error" in box:
            raise LLMUnavailable(f"mlx_lm generation failed: {box['error']}") from box["error"]
        return str(box.get("value", ""))

    def generate(
        self, messages: list[dict[str, str]], *, timeout: float,
        response_schema: dict[str, Any] | None = None, json_mode: bool | None = None,
    ) -> GenerateResult:
        # json_mode accepted for interface uniformity, unused -- see
        # OpenAICompatProvider.generate()'s identical note.
        t0 = time.perf_counter()
        try:
            content = self._generate_once(self.model, messages, timeout, response_schema)
            used_model = self.model
        except LLMUnavailable:
            if not self.fallback_model or self.fallback_model == self.model:
                raise
            content = self._generate_once(self.fallback_model, messages, timeout, response_schema)
            used_model = self.fallback_model
        return GenerateResult(content=content, latency_s=time.perf_counter() - t0,
                               provider=self.name, model=used_model)

    def health_check(self, timeout: float = 5.0) -> bool:
        try:
            import mlx_lm  # noqa: F401
        except ImportError:
            return False
        return True

    def capabilities(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "model": self.model,
            "supports_json_schema": False,
            "supports_tool_calls": False,
            "model_override_supported": True,
            "fallback_model": self.fallback_model,
            "enable_thinking": self.enable_thinking,
            "max_concurrent_generations": self._MAX_CONCURRENT_GENERATIONS,
            "timeouts": self._timeouts,
            "saturated_rejections": self._saturated_rejections,
            "notes": "No native structured-output/grammar decoding; JSON is prompt-instructed "
            "only. timeout is soft (abandons, does not kill, the worker thread).",
        }


# ─── Deterministic / no-LLM fallback ─────────────────────────────────────────


class NullProvider:
    """Always fails fast. The explicit rollback switch: THURSDAY_LLM_PROVIDER=none
    forces every brain LLM call through brain.py's existing abstain path with
    zero network calls and zero model loads."""

    name = "none"

    def __init__(self, *_a, **_kw):
        pass

    def generate(self, messages, *, timeout: float, response_schema=None, json_mode=None) -> GenerateResult:
        raise LLMUnavailable("THURSDAY_LLM_PROVIDER=none: no LLM provider configured")

    def health_check(self, timeout: float = 5.0) -> bool:
        return False

    def capabilities(self) -> dict[str, Any]:
        return {"provider": self.name, "model": None, "supports_json_schema": False,
                "supports_tool_calls": False, "model_override_supported": False}


# ─── Factory ─────────────────────────────────────────────────────────────────

_PROVIDER_NAMES = ("audio_too", "openai_compat", "mlx_lm", "none")
_provider_cache: LLMProvider | None = None
_provider_cache_key: tuple | None = None


def _parse_tri_state_bool(value: str) -> bool | None:
    if not value:
        return None
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _build_provider(provider_name: str, model: str | None, base_url: str, fallback_model: str | None,
                     max_tokens: int, enable_thinking: bool | None) -> LLMProvider:
    if provider_name == "audio_too":
        return AudioTooProvider(model=model, fallback_model=fallback_model)
    if provider_name == "openai_compat":
        kwargs: dict[str, Any] = {"max_tokens": max_tokens}
        if enable_thinking is not None:
            kwargs["enable_thinking"] = enable_thinking
        return OpenAICompatProvider(model=model or "default", base_url=base_url, fallback_model=fallback_model, **kwargs)
    if provider_name == "mlx_lm":
        if not model:
            raise ValueError("THURSDAY_LLM_PROVIDER=mlx_lm requires THURSDAY_LLM_MODEL to be set")
        kwargs = {"enable_thinking": enable_thinking} if enable_thinking is not None else {}
        return MLXLMProvider(model=model, fallback_model=fallback_model, max_tokens=max_tokens, **kwargs)
    if provider_name == "none":
        return NullProvider()
    raise ValueError(f"Unknown THURSDAY_LLM_PROVIDER={provider_name!r}; expected one of {_PROVIDER_NAMES}")


def get_llm_provider() -> LLMProvider:
    """Return the process-wide LLM provider selected by env vars, building
    (and caching) it on first use. Re-reads env vars if they've changed
    since the last call, so tests/CLIs that set env vars per-invocation
    don't get a stale cached provider from a different configuration."""
    global _provider_cache, _provider_cache_key
    provider_name = os.environ.get("THURSDAY_LLM_PROVIDER", "audio_too")
    model = os.environ.get("THURSDAY_LLM_MODEL") or None
    base_url = os.environ.get("THURSDAY_LLM_BASE_URL", "http://127.0.0.1:11434/v1")
    fallback_model = os.environ.get("THURSDAY_LLM_FALLBACK_MODEL") or None
    max_tokens = int(os.environ.get("THURSDAY_LLM_MAX_TOKENS", "768"))
    # Tri-state: unset -> each provider's own default (mlx_lm already
    # defaults to False; openai_compat defaults to None, sending no
    # chat_template_kwargs field at all, since most OpenAI-compatible
    # servers don't recognize it and some reject unknown fields).
    enable_thinking = _parse_tri_state_bool(os.environ.get("THURSDAY_LLM_ENABLE_THINKING", ""))
    key = (provider_name, model, base_url, fallback_model, max_tokens, enable_thinking)
    if _provider_cache is not None and _provider_cache_key == key:
        return _provider_cache
    _provider_cache = _build_provider(provider_name, model, base_url, fallback_model, max_tokens, enable_thinking)
    _provider_cache_key = key
    return _provider_cache


def reset_provider_cache() -> None:
    """Test hook: force the next get_llm_provider() call to rebuild from
    current env vars instead of returning a cached instance."""
    global _provider_cache, _provider_cache_key
    _provider_cache = None
    _provider_cache_key = None


def default_timeout() -> float:
    return float(os.environ.get("THURSDAY_LLM_TIMEOUT", os.environ.get("AUDIO_TOO_LLM_TIMEOUT", "10")))


def capability_report(probe: bool = False) -> dict[str, Any]:
    """A model-agnostic capability snapshot for the currently configured
    provider. With probe=True also runs a live health_check() (may make a
    network call / load a model) -- off by default so calling this is cheap
    and side-effect-free."""
    provider = get_llm_provider()
    report = provider.capabilities()
    report["timeout_s"] = default_timeout()
    if probe:
        report["healthy"] = provider.health_check(timeout=min(5.0, default_timeout()))
    return report
