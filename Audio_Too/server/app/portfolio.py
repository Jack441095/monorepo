"""Portfolio content loaded from a local JSON file."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORTFOLIO_PATH = ROOT / "portfolio" / "portfolio_data.json"


def load_portfolio() -> dict:
    if not PORTFOLIO_PATH.exists():
        return {"codebases": [], "audio": [], "stats": []}
    payload = json.loads(PORTFOLIO_PATH.read_text(encoding="utf-8"))
    return {
        "codebases": [
            {key: item.get(key) for key in ("type", "title", "description", "tags")}
            for item in (payload.get("codebases") or [])
            if isinstance(item, dict)
        ],
        "stats": [
            {key: item.get(key) for key in ("value", "label")}
            for item in (payload.get("stats") or [])
            if isinstance(item, dict)
        ],
        "audio": [
            {key: item.get(key) for key in ("title", "description", "src")}
            for item in (payload.get("audio") or [])
            if isinstance(item, dict) and str(item.get("src", "")).startswith("/portfolio/audio/")
        ],
    }
