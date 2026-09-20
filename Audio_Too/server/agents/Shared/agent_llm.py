#!/usr/bin/env python3
"""Lightweight Ollama LLM client for agent generation.

Calls Ollama's REST API (default http://localhost:11434) to generate responses.
Falls back gracefully if Ollama is unavailable.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("AUDIO_TOO_AGENT_MODEL", "qwen2.5:1.5b")
FAST_MODEL = os.environ.get("AUDIO_TOO_AGENT_FAST_MODEL", "qwen2.5:1.5b")
TIMEOUT = int(os.environ.get("AUDIO_TOO_LLM_TIMEOUT", "60"))


def _ollama_request(
    endpoint: str,
    payload: dict[str, Any],
    timeout: int = TIMEOUT,
) -> dict[str, Any] | None:
    """Make a request to the Ollama API. Returns parsed JSON or None on failure."""
    url = f"{OLLAMA_HOST.rstrip('/')}/api/{endpoint.lstrip('/')}"
    data = json.dumps(payload).encode("utf-8")
    try:
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError):
        return None


def _ollama_generate_stream(
    payload: dict[str, Any],
    timeout: int = TIMEOUT,
) -> str | None:
    """Stream a generation from Ollama and concatenate the response."""
    url = f"{OLLAMA_HOST.rstrip('/')}/api/generate"
    data = json.dumps(payload).encode("utf-8")
    try:
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            full_text: list[str] = []
            for line in resp:
                if not line.strip():
                    continue
                try:
                    chunk = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    continue
                if chunk.get("response"):
                    full_text.append(chunk["response"])
                if chunk.get("done"):
                    break
            return "".join(full_text).strip() or None
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError):
        return None


def _ollama_chat(
    messages: list[dict[str, str]],
    model: str = DEFAULT_MODEL,
    temperature: float = 0.3,
    max_tokens: int = 600,
    timeout: int = TIMEOUT,
) -> str | None:
    """Call Ollama chat API. Returns generated text or None."""
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }
    result = _ollama_request("chat", payload, timeout=timeout)
    if result is None:
        return None
    message = result.get("message", {})
    return message.get("content", "").strip() or None


def _ollama_generate(
    prompt: str,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.3,
    max_tokens: int = 600,
    timeout: int = TIMEOUT,
) -> str | None:
    """Call Ollama generate API (simpler than chat). Returns generated text or None."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }
    result = _ollama_request("generate", payload, timeout=timeout)
    if result is None:
        return None
    return result.get("response", "").strip() or None


def _ollama_available() -> bool:
    """Check whether Ollama is reachable AND has the model this module
    actually generates with pulled.

    A reachable-but-model-less Ollama server (confirmed possible: the
    server responds to /api/tags with an empty "models" list) used to pass
    this check, then every real generate_llm() call failed and returned
    None -- tests gated on this check ran instead of skipping, and failed
    on a confusing "assert None" rather than a clear "Ollama not
    available" skip.
    """
    try:
        req = urllib.request.Request(f"{OLLAMA_HOST.rstrip('/')}/api/tags")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return False
    available = {str(m.get("name", "")) for m in data.get("models", [])}
    return any(model.split(":")[0] == wanted.split(":")[0] for wanted in (DEFAULT_MODEL, FAST_MODEL) for model in available)


def generate_llm(
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 600,
    fast: bool = False,
) -> str | None:
    """Generate a response using Ollama.

    Args:
        system_prompt: System-level instructions defining agent behavior.
        user_prompt: The user's task/request.
        model: Override model name. If None, uses DEFAULT_MODEL or FAST_MODEL.
        temperature: Creativity (0.0 = deterministic, 1.0 = creative).
        max_tokens: Maximum output tokens.
        fast: If True, use the smaller fast model.

    Returns:
        Generated text string, or None if generation failed.
    """
    if not _ollama_available():
        return None

    resolved_model = model or (FAST_MODEL if fast else DEFAULT_MODEL)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    return _ollama_chat(
        messages=messages,
        model=resolved_model,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def generate_llm_simple(
    prompt: str,
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 600,
) -> str | None:
    """Simpler generation without system/user split (single prompt)."""
    if not _ollama_available():
        return None
    resolved_model = model or DEFAULT_MODEL
    return _ollama_generate(
        prompt=prompt,
        model=resolved_model,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def extract_structured_field(text: str, field: str) -> str | None:
    """Extract a field like 'Subject: ...' or 'Lead: ...' from LLM output.

    Works with both markdown and plain text formats the LLM might produce.
    """
    import re

    # Try "Field: value" at start of line
    pattern = rf"^{re.escape(field)}\s*[:=-]\s*(.+?)$"
    match = re.search(pattern, text, re.M)
    if match:
        value = match.group(1).strip()
        if value and not value.startswith("["):
            return value

    # Try "**Field:** value" (markdown bold)
    pattern = rf"\*\*{re.escape(field)}\*\*\s*[:=-]?\s*(.+?)$"
    match = re.search(pattern, text, re.M)
    if match:
        value = match.group(1).strip()
        if value and not value.startswith("["):
            return value

    return None


def extract_structured_fields(text: str, fields: list[str]) -> dict[str, str]:
    """Extract multiple structured fields from LLM output."""
    result = {}
    for field in fields:
        value = extract_structured_field(text, field)
        if value:
            result[field] = value
    return result