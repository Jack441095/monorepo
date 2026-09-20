"""Validation helpers for identifiers and user-derived filesystem paths.

Ported into this standalone repository (not a live dependency on the old
NITE DSP platform): pure stdlib, no external calls.
"""

from __future__ import annotations

import re
from pathlib import Path

IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")


def validate_identifier(value: object, *, label: str = "identifier") -> str:
    """Return a normalized identifier or raise ``ValueError``.

    IDs are deliberately limited to a small portable alphabet so they can be
    used safely in URLs, SQLite lookups, logs, and directory names.
    """
    normalized = str(value or "").strip()
    if not IDENTIFIER_RE.fullmatch(normalized):
        raise ValueError(
            f"Invalid {label}. Use 1-64 letters, numbers, underscores, or hyphens."
        )
    return normalized


def safe_child(root: str | Path, *parts: object) -> Path:
    """Resolve a child path and prove it remains under ``root``."""
    resolved_root = Path(root).resolve()
    target = resolved_root.joinpath(*(str(part) for part in parts)).resolve()
    try:
        target.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError("Path escapes its configured storage root.") from exc
    return target
