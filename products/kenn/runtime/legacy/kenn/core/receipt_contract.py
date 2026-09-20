"""Shared, purely-additive receipt-envelope helpers for KENN's Live action
services.

Existing receipt fields, schemas, and call sites are never changed or
removed by this module -- every helper here is opt-in and backward
compatible, so a service can adopt it incrementally without breaking its
existing tests. This exists to close three real, code-only gaps found in
the 2026-09-06 beta-sprint P0 audit (see
docs/KENN_BETA_SPRINT_PLAN_2026-09-06.md and the matching entry in
docs/ABLETON_ASSISTANT_CURRENT_STATE.md):

1. No correlation id threads a request through proposal -> confirm ->
   execute -> readback -> receipt, making a single real-world failure hard
   to trace across logs/support diagnostics.
2. No receipt records whether retrying the exact same request is safe,
   unsafe, or needs a human/inspection first -- only a free-text error.
3. No stage-level timing (snapshot, write, readback) is captured anywhere,
   so a slow step can't be distinguished from a stuck one in diagnostics.

This intentionally does NOT introduce the full
offline/inspecting/proposal_ready/awaiting_confirmation/applying/verified
state-machine vocabulary from the sprint plan -- that's a schema-level
decision that should be made together with whoever is building the
companion UI that consumes it (the plan explicitly separates backend
contracts from UI work), not invented unilaterally in one pass.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Literal

RetrySafety = Literal["safe", "unsafe", "requires_inspection"]


def new_correlation_id() -> str:
    return f"corr-{uuid.uuid4().hex}"


def resolve_correlation_id(explicit: str | None) -> str:
    """Use a caller-supplied correlation id verbatim (bounded), or mint a
    fresh one. Never silently drops an id a caller is already tracking."""
    cleaned = str(explicit or "").strip()[:128]
    return cleaned or new_correlation_id()


def classify_retry_safety(*, verified: bool, status: str) -> RetrySafety:
    """Best-effort default classification for a receipt that doesn't set
    its own. A call site with more specific knowledge (e.g. "this exact
    failure means the write never left this process") should pass an
    explicit, more accurate value instead of relying on this default.
    """
    if verified and status == "applied":
        return "safe"  # nothing to retry -- the action already succeeded
    if status in {"failed_verification", "transport_uncertain"}:
        # The write may or may not have reached Live; retrying blindly
        # risks a duplicate mutation. A human/caller should inspect a
        # fresh Live snapshot before deciding what to do next.
        return "requires_inspection"
    return "unsafe"  # rejected before any write was attempted (stale state,
    # bad token, etc.) -- safe to retry only after making a brand new
    # proposal, never with the same confirmation token or idempotency key.


class StageTimer:
    """Bounded, ordered stage-timing capture for one request's lifecycle.

    Never claims to time a stage that didn't run: only ``mark()`` calls
    that actually happen appear in the result. Usage:

        timer = StageTimer()
        ... take a Live snapshot ...
        timer.mark("snapshot")
        ... send the write ...
        timer.mark("write")
        ... read back ...
        timer.mark("readback")
        receipt["stage_timings_ms"] = timer.as_ms()
    """

    def __init__(self) -> None:
        self._marks: list[tuple[str, float]] = [("start", time.monotonic())]

    def mark(self, stage: str) -> None:
        self._marks.append((str(stage)[:64], time.monotonic()))

    def as_ms(self) -> dict[str, float]:
        result: dict[str, float] = {}
        for (_prev_name, prev_t), (name, t) in zip(self._marks, self._marks[1:]):
            result[name] = round((t - prev_t) * 1000.0, 3)
        if len(self._marks) > 1:
            result["total"] = round((self._marks[-1][1] - self._marks[0][1]) * 1000.0, 3)
        return result


__all__ = [
    "RetrySafety",
    "StageTimer",
    "classify_retry_safety",
    "new_correlation_id",
    "resolve_correlation_id",
]
