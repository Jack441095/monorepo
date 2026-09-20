"""Shared bound for the per-service confirmed-action idempotency sets.

Each Live-mutating service (live_action_service, midi_clip_service,
clip_audition_service, sample_import_service, live_recipe) tracks its own
confirmed/in-flight action ids in a module-level ``set[str]`` so a replayed
confirmation can never repeat a write. Left unpruned, that set grows for the
life of the process -- a real, unbounded-memory-growth gap found in four of
these five services during the 2026-09-06 beta-sprint review (only
live_action_service.py had ever been given a cap). Clearing the set once it
passes a generous bound keeps memory bounded without weakening replay
protection in practice: action ids are fresh ``uuid4`` values, so a replay
would have to reuse one from more than MAX_TRACKED_KEYS actions ago, which
never happens.
"""

from __future__ import annotations

MAX_TRACKED_KEYS = 10_000


def prune_if_needed(used_keys: set[str]) -> None:
    """Clear ``used_keys`` in place once it exceeds the bound. Call this
    under the same lock that guards writes to the set."""
    if len(used_keys) > MAX_TRACKED_KEYS:
        used_keys.clear()
