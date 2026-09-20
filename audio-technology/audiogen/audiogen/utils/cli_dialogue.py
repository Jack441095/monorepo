from __future__ import annotations

from typing import Optional

def parse_on_off(s: str) -> Optional[bool]:
    """Parse CLI on/off tokens (interactive dialogue/melody toggles)."""
    t = (s or "").strip().lower()
    if t in {"on", "1", "true", "yes"}:
        return True
    if t in {"off", "0", "false", "no"}:
        return False
    return None
