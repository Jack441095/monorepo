"""Append-only activity log for Audio_Too agents and website."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG_PATH = ROOT / "data" / "activity.jsonl"


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log_event(event: str, detail: str = "", actor: str = "system") -> dict:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "at": now(),
        "actor": actor,
        "event": event,
        "detail": detail,
    }
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def list_events(limit: int = 100) -> list[dict]:
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
    events: list[dict] = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
        if len(events) >= limit:
            break
    return events
