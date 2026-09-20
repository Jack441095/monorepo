# composition/section_planner/observability.py
"""Structured debug logging for degraded paths (Phase 2 observability)."""
from __future__ import annotations

import logging
from typing import Any, Optional

# Dedicated logger so operators can enable DEBUG without the whole app:
#   logging.getLogger("audiogen.section_planner").setLevel(logging.DEBUG)
log = logging.getLogger("audiogen.section_planner")


def log_degraded(
    where: str,
    exc: BaseException,
    *,
    section_index: Optional[int] = None,
    section_role: Optional[str] = None,
    **extra: Any,
) -> None:
    """
    Log a best-effort fallback path with full traceback (DEBUG only).

    Pass section_index / section_role when the planner knows them; otherwise omit.
    """
    bits: list[str] = [f"where={where!r}"]
    if section_index is not None:
        bits.append(f"section_index={int(section_index)}")
    if section_role is not None and str(section_role).strip():
        bits.append(f"section_role={str(section_role).strip()!r}")
    for k, v in extra.items():
        if v is None:
            continue
        bits.append(f"{k}={v!r}")
    msg = "degraded: " + " ".join(bits)
    log.debug(msg, exc_info=exc)
