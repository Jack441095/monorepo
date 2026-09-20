"""Creative Lab: storage functions.

Split out of creative_lab.py (was 1,261 lines) — see docs/BACKLOG.md.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path


from .constants import (
    DATA_PATH,
    MAX_FEEDBACK,
    MAX_SESSIONS,
    ROOT,
)


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load() -> dict:
    if not DATA_PATH.exists():
        return {"sessions": [], "feedback": []}
    try:
        data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"sessions": [], "feedback": []}
    return {
        "sessions": data.get("sessions", []) if isinstance(data.get("sessions"), list) else [],
        "feedback": data.get("feedback", []) if isinstance(data.get("feedback"), list) else [],
    }


def _save(data: dict) -> None:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["sessions"] = list(data.get("sessions", []))[-MAX_SESSIONS:]
    data["feedback"] = list(data.get("feedback", []))[-MAX_FEEDBACK:]
    DATA_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _slug(value: str, fallback: str = "creative-repair") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
    return slug[:80] or fallback


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(float(value or default))
    except (TypeError, ValueError):
        return default
