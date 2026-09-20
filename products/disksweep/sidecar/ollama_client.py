"""Local Ollama client with graceful fallback (KENN-style)."""

import json
import os
import urllib.request

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
TIMEOUT_S = int(os.environ.get("OLLAMA_TIMEOUT_S", "30"))


def ollama_available() -> bool:
    try:
        req = urllib.request.Request(OLLAMA_URL + "/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def _post(path: str, payload: dict, timeout: int) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        OLLAMA_URL + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def label(model: str, system: str, user: str, timeout: int = TIMEOUT_S) -> str | None:
    """Returns raw text or None when Ollama is unreachable (caller falls back)."""
    try:
        out = _post(
            "/api/generate",
            {"model": model, "system": system, "prompt": user, "stream": False},
            timeout,
        )
        return (out.get("response") or "").strip() or None
    except Exception:
        return None
