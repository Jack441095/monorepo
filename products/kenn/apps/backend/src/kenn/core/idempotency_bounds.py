"""Shared bound for the per-service confirmed-action idempotency sets.

Each Live-mutating service (live_action_service, midi_clip_service,
clip_audition_service, sample_import_service, live_recipe) tracks its own
confirmed/in-flight action ids in a module-level ``set[str]`` so a replayed
confirmation can never repeat a write. Left unpruned, that set grows for the
life of the process -- a real, unbounded-memory-growth gap found in four of
these five services during the 2026-09-06 beta-sprint review (only
live_action_service.py had ever been given a cap). When the set exceeds a
generous bound, evicting only part of the unordered window keeps memory
bounded without erasing all recent replay protection. Action ids are fresh
``uuid4`` values; durable protection across restarts remains a separate
product requirement.
"""

from __future__ import annotations

MAX_TRACKED_KEYS = 10_000


def prune_if_needed(used_keys: set[str]) -> None:
    """Evict roughly half of ``used_keys`` in place once it exceeds the bound.

    Call this under the same lock that guards writes to the set.

    A previous revision called ``used_keys.clear()``, which wiped the entire
    replay-protection window and allowed any of the last 10k action ids to
    replay a write. Evicting half keeps memory bounded while retaining
    protection for recently issued action ids.
    """
    if len(used_keys) > MAX_TRACKED_KEYS:
        for _ in range(MAX_TRACKED_KEYS // 2):
            used_keys.pop()
