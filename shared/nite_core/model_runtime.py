"""Process-local coordination for native model runtime initialisation and LLM provider abstractions."""

from __future__ import annotations

import os
import threading
import time
import httpx
from typing import Protocol
from dataclasses import dataclass

ONNX_SESSION_INIT_LOCK = threading.RLock()


@dataclass
class LLMResult:
    """Standardized result of an LLM generation call."""
    content: str
    model: str
    usage: dict[str, int]


class LLMProvider(Protocol):
    """Protocol defining the interface for all LLM providers."""
    def generate(
        self, messages: list[dict[str, str]], timeout: int = 10,
        response_schema: dict | None = None, json_mode: bool = True,
    ) -> LLMResult:
        """Call the LLM with a list of chat messages and return the completion content.

        response_schema, if given, is an OpenAI-style JSON Schema
        (`{"name": ..., "schema": {...}}`) requesting structured output
        constrained to that shape -- stronger than plain JSON-object mode
        (enums/required fields are enforced, not just "valid JSON somewhere").

        json_mode: when True (default, matches every caller until 2026-08-02)
        and response_schema is unset, requests plain JSON-object output.
        Callers that want free-form natural-language text (not JSON at all)
        must pass json_mode=False, or the provider's forced response_format
        will fight the prompt.
        """
        ...


# ---------------------------------------------------------------------------
# Ollama keep-alive pinger — mirrors studio/kenn/kenn/llm/llm_rewrite.py's
# pinger for the same reason: Ollama's OpenAI-compatible /chat/completions
# endpoint ignores a "keep_alive" field (only native /api/generate honours
# it), so a gap between Thursday brain calls longer than Ollama's ~5 min
# default TTL pays a full cold model reload on the next routing decision.
# Started lazily on first real use of OllamaProvider (not at import time),
# so nothing pings Ollama when the brain is disabled or the remote provider
# is the one actually in use. Additive only — never touches routing logic.
# ---------------------------------------------------------------------------

_brain_keep_alive_started = False
_brain_keep_alive_lock = threading.Lock()
BRAIN_KEEP_ALIVE_DURATION = os.environ.get("THURSDAY_OLLAMA_KEEP_ALIVE", "30m")
BRAIN_KEEP_ALIVE_INTERVAL_S = 240  # under Ollama's 5 min default unload timeout


def _brain_native_ollama_base(base_url: str) -> str:
    return base_url[:-3] if base_url.endswith("/v1") else base_url


def _ping_brain_ollama_keep_alive(model: str, base_url: str) -> None:
    try:
        httpx.post(
            f"{_brain_native_ollama_base(base_url)}/api/generate",
            json={"model": model, "prompt": "", "keep_alive": BRAIN_KEEP_ALIVE_DURATION},
            timeout=10.0,
        )
    except Exception:
        pass  # best-effort — a missed ping just means the next real call reloads normally


def _brain_keep_alive_loop(model: str, base_url: str) -> None:
    while True:
        _ping_brain_ollama_keep_alive(model, base_url)
        time.sleep(BRAIN_KEEP_ALIVE_INTERVAL_S)


def _ensure_brain_ollama_keep_alive(model: str, base_url: str) -> None:
    global _brain_keep_alive_started
    if _brain_keep_alive_started:
        return
    with _brain_keep_alive_lock:
        if _brain_keep_alive_started:
            return
        threading.Thread(
            target=_brain_keep_alive_loop, args=(model, base_url), daemon=True
        ).start()
        _brain_keep_alive_started = True


class OllamaProvider:
    """Local Ollama LLM provider (local-first)."""
    def __init__(self, model: str | None = None, base_url: str | None = None):
        self.model = model or os.environ.get("AUDIO_TOO_LLM_MODEL_ROUTE", "qwen2.5:1.5b")
        self.base_url = (base_url or os.environ.get("AUDIO_TOO_LLM_BASE_URL", "http://127.0.0.1:11434/v1")).rstrip("/")

    def generate(
        self, messages: list[dict[str, str]], timeout: int = 10,
        response_schema: dict | None = None, json_mode: bool = True,
    ) -> LLMResult:
        _ensure_brain_ollama_keep_alive(self.model, self.base_url)
        # response_format forces valid JSON output via Ollama's OpenAI-
        # compatible endpoint. Found 2026-07-12: without it, a small local
        # model (qwen2.5:1.5b) reliably produced a correct, well-grounded
        # natural-language answer that brain.py's strict JSON parser then
        # rejected outright -- the model's reasoning was fine, only its
        # output format wasn't machine-parseable. brain.py was the only
        # caller until 2026-08-02, requiring JSON unconditionally, hence
        # json_mode defaulting True. When a full response_schema is given,
        # use Ollama's stronger json_schema mode instead (confirmed
        # 2026-07-12 against a real Ollama instance: it enforces enums/
        # required fields, not just "some valid JSON") -- this is what
        # caught the "kind" field confusion that plain json_object mode
        # didn't. A caller wanting genuine free-form text (e.g. Thursday's
        # conversational reply rewrite, thursday/response_rewrite.py) passes
        # json_mode=False and gets no response_format constraint at all.
        response_format = None
        if response_schema:
            response_format = {"type": "json_schema", "json_schema": response_schema}
        elif json_mode:
            response_format = {"type": "json_object"}
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.1},
            "keep_alive": BRAIN_KEEP_ALIVE_DURATION,
        }
        if response_format is not None:
            payload["response_format"] = response_format

        try:
            with httpx.Client(timeout=httpx.Timeout(float(timeout), connect=5.0)) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
                data = response.json()

                choices = data.get("choices") or []
                if not choices:
                    raise ValueError("Empty choices in response")
                content = choices[0].get("message", {}).get("content", "")
                usage_info = data.get("usage") or {"prompt_tokens": 0, "completion_tokens": 0}

                return LLMResult(
                    content=content,
                    model=self.model,
                    usage={
                        "prompt_tokens": usage_info.get("prompt_tokens", 0),
                        "completion_tokens": usage_info.get("completion_tokens", 0),
                    }
                )
        except Exception as e:
            raise RuntimeError(f"Ollama generation failed: {e}")


class RemoteProvider:
    """Remote fallback LLM provider (e.g. OpenAI compatible)."""
    def __init__(self, model: str | None = None, base_url: str | None = None, api_key: str | None = None):
        self.model = model or os.environ.get("AUDIO_TOO_LLM_MODEL", "gpt-4o-mini")
        self.base_url = (base_url or os.environ.get("AUDIO_TOO_LLM_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.api_key = api_key or os.environ.get("AUDIO_TOO_LLM_API_KEY", "")

    def generate(
        self, messages: list[dict[str, str]], timeout: int = 10,
        response_schema: dict | None = None, json_mode: bool = True,
    ) -> LLMResult:
        # See the matching note in OllamaProvider.generate() -- json_mode
        # defaults True to preserve brain.py's (the only caller until
        # 2026-08-02) unconditional strict-JSON requirement; OpenAI supports
        # the same json_schema structured-output mode. A plain-text caller
        # (json_mode=False) gets no response_format constraint at all.
        response_format = None
        if response_schema:
            response_format = {"type": "json_schema", "json_schema": response_schema}
        elif json_mode:
            response_format = {"type": "json_object"}
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "temperature": 0.1,
        }
        if response_format is not None:
            payload["response_format"] = response_format

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            
        try:
            with httpx.Client(timeout=httpx.Timeout(float(timeout), connect=5.0)) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
                
                choices = data.get("choices") or []
                if not choices:
                    raise ValueError("Empty choices in response")
                content = choices[0].get("message", {}).get("content", "")
                usage_info = data.get("usage") or {"prompt_tokens": 0, "completion_tokens": 0}
                
                return LLMResult(
                    content=content,
                    model=self.model,
                    usage={
                        "prompt_tokens": usage_info.get("prompt_tokens", 0),
                        "completion_tokens": usage_info.get("completion_tokens", 0),
                    }
                )
        except Exception as e:
            raise RuntimeError(f"Remote generation failed: {e}")


class EnvGatedProvider:
    """Wrapper that resolves dynamically between local and remote LLM providers based on environment."""
    def __init__(self, local: LLMProvider, remote: LLMProvider):
        self.local = local
        self.remote = remote

    def generate(
        self, messages: list[dict[str, str]], timeout: int = 10,
        response_schema: dict | None = None, json_mode: bool = True,
    ) -> LLMResult:
        provider = os.environ.get("AUDIO_TOO_LLM_PROVIDER", "").strip().lower()

        if provider in ("remote", "openai"):
            return self.remote.generate(
                messages, timeout=timeout, response_schema=response_schema, json_mode=json_mode
            )
        elif provider == "ollama":
            return self.local.generate(
                messages, timeout=timeout, response_schema=response_schema, json_mode=json_mode
            )

        # Default auto-resolve: check if local Ollama is reachable.
        # Found 2026-07-12: a 1.0s timeout here was flaky whenever Ollama was
        # busy loading a larger model into memory for the first time -- the
        # reachability check itself would time out, silently falling back to
        # the remote provider (which has no API key configured here and
        # always 401s), even though Ollama was genuinely available a moment
        # later. 5s is still a small, one-time cost against a local service,
        # and the failure is now logged instead of silently swallowed --
        # this exact "except Exception: pass" shape is the same class of bug
        # this codebase's own reliability-hardening pass already fixed
        # broadly elsewhere, just missed here.
        try:
            base_url = os.environ.get("AUDIO_TOO_LLM_BASE_URL", "http://127.0.0.1:11434/v1").rstrip("/")
            native_base = base_url[:-3] if base_url.endswith("/v1") else base_url
            with httpx.Client(timeout=5.0) as client:
                res = client.get(f"{native_base}/api/tags")
                if res.status_code == 200:
                    return self.local.generate(
                        messages, timeout=timeout, response_schema=response_schema, json_mode=json_mode
                    )
        except Exception as e:
            import logging
            logging.getLogger("audio_too.model_runtime").warning(
                f"Local Ollama reachability check failed, falling back to remote: {e}"
            )

        return self.remote.generate(
            messages, timeout=timeout, response_schema=response_schema, json_mode=json_mode
        )


DEFAULT_LLM = EnvGatedProvider(OllamaProvider(), RemoteProvider())
