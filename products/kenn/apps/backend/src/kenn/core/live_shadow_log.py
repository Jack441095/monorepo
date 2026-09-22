"""Bounded local JSONL evidence log for observational Live LLM plans."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from threading import Lock
from typing import Any


SHADOW_LOG_PATH = Path(
    os.environ.get(
        "KENN_LIVE_LLM_SHADOW_LOG",
        str(Path(__file__).resolve().parents[1] / "data" / "live_llm_shadow.jsonl"),
    )
).expanduser()
MAX_SHADOW_ROWS = 10_000
_LOCK = Lock()


def record_shadow_result(result: dict[str, Any], *, path: Path | None = None) -> bool:
    llm = result.get("llm") if isinstance(result, dict) else None
    if not isinstance(llm, dict) or llm.get("mode") != "shadow":
        return False
    target = path or SHADOW_LOG_PATH
    row = {
        "schema": "kenn.ableton_llm_shadow_log.v1",
        "timestamp": time.time(),
        "command": str(result.get("command") or "")[:4000],
        "status": str(result.get("status") or "")[:64],
        "llm": llm,
        "deterministic_intent": result.get("intent") if isinstance(result.get("intent"), dict) else None,
    }
    try:
        encoded = json.dumps(row, ensure_ascii=True, separators=(",", ":"))
        with _LOCK:
            target.parent.mkdir(parents=True, exist_ok=True)
            lines = target.read_text(encoding="utf-8").splitlines() if target.is_file() else []
            lines.append(encoded)
            lines = lines[-MAX_SHADOW_ROWS:]
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, prefix=".shadow-", delete=False) as handle:
                temporary = Path(handle.name)
                handle.write("\n".join(lines) + "\n")
            os.chmod(temporary, 0o600)
            os.replace(temporary, target)
            os.chmod(target, 0o600)
        return True
    except (OSError, TypeError, ValueError):
        return False


__all__ = ["MAX_SHADOW_ROWS", "SHADOW_LOG_PATH", "record_shadow_result"]
