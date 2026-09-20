"""Loopback-only Ollama transport for KENN's compact deliberative sketches."""

from __future__ import annotations

import json
from typing import Any, Callable, Iterable
import urllib.error
import urllib.parse
import urllib.request

from kenn.core.deliberative_plan import deliberative_plan_sketch_json_schema


OpenURL = Callable[..., Any]
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


_NO_REDIRECT_OPENER = urllib.request.build_opener(_NoRedirect())


def open_loopback_ollama(request: urllib.request.Request, *, timeout: float):
    return _NO_REDIRECT_OPENER.open(request, timeout=timeout)


def validate_ollama_base_url(value: str) -> str:
    candidate = str(value or "").strip().rstrip("/")
    parsed = urllib.parse.urlsplit(candidate)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in _LOOPBACK_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("Ollama planner URL must be an uncredentialed loopback HTTP origin.")
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("Ollama planner URL has an invalid port.") from exc
    return candidate


class OllamaDeliberativeGenerator:
    """Generate one constrained sketch without granting any execution power."""

    def __init__(
        self,
        *,
        model: str = "qwen2.5:7b-instruct",
        base_url: str = "http://127.0.0.1:11434",
        timeout: float = 45.0,
        max_output_tokens: int = 320,
        opener: OpenURL = open_loopback_ollama,
    ) -> None:
        clean_model = str(model or "").strip()[:128]
        if not clean_model:
            raise ValueError("An Ollama deliberative model is required.")
        self.model = clean_model
        self.base_url = validate_ollama_base_url(base_url)
        self.timeout = max(1.0, min(120.0, float(timeout)))
        self.max_output_tokens = max(128, min(1_024, int(max_output_tokens)))
        self._opener = opener

    def __call__(self, prompt: str) -> str:
        return self.generate(prompt)

    def generate(self, prompt: str, *, allowed_actions: Iterable[str] | None = None) -> str:
        clean_prompt = str(prompt or "")
        if not clean_prompt.strip():
            raise ValueError("A deliberative prompt is required.")
        request = urllib.request.Request(
            self.base_url + "/api/chat",
            data=json.dumps({
                "model": self.model,
                "messages": [{"role": "user", "content": clean_prompt}],
                "stream": False,
                "format": deliberative_plan_sketch_json_schema(
                    max_steps=3, max_list_items=4, allowed_actions=allowed_actions,
                    allow_clarification=False,
                ),
                "options": {
                    "temperature": 0,
                    "seed": 0,
                    "num_ctx": 8192,
                    "num_predict": self.max_output_tokens,
                },
                "keep_alive": "30m",
            }, separators=(",", ":")).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._opener(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Ollama planner returned HTTP {exc.code}.") from exc
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            raise RuntimeError("The configured local Ollama planner is unavailable or timed out.") from exc
        message = payload.get("message") if isinstance(payload, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Ollama planner returned no assistant content.")
        return content


__all__ = ["OllamaDeliberativeGenerator", "open_loopback_ollama", "validate_ollama_base_url"]
