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

from collections.abc import Iterable, Iterator, MutableSet

MAX_TRACKED_KEYS = 10_000

__all__ = ["MAX_TRACKED_KEYS", "IdempotencyTrackingSet", "prune_if_needed"]


class IdempotencyTrackingSet(MutableSet[str]):
    """An order-preserving set that evicts oldest entries (FIFO) on pop().

    Python's built-in set does not record insertion order, so set.pop()
    removes arbitrary hash bucket entries. Under pruning, a standard set
    can evict keys inserted milliseconds ago while retaining stale keys
    from hours ago. Backing this set with a dict preserves insertion order
    in Python 3.7+, allowing FIFO eviction of the oldest tracked action ids.
    """

    def __init__(self, iterable: Iterable[str] | None = None) -> None:
        self._data: dict[str, None] = {}
        if iterable is not None:
            for item in iterable:
                self._data[str(item)] = None

    def add(self, value: str) -> None:
        self._data[str(value)] = None

    def discard(self, value: str) -> None:
        self._data.pop(str(value), None)

    def pop(self, last: bool = False) -> str:
        """Remove and return an element in FIFO order by default (oldest first)."""
        if not self._data:
            raise KeyError("pop from an empty set")
        key = next(reversed(self._data) if last else iter(self._data))
        del self._data[key]
        return key

    def clear(self) -> None:
        self._data.clear()

    def __contains__(self, value: object) -> bool:
        return value in self._data

    def __len__(self) -> int:
        return len(self._data)

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def update(self, *others: Iterable[str]) -> None:
        for other in others:
            for item in other:
                self.add(item)

    def __repr__(self) -> str:
        return f"IdempotencyTrackingSet({list(self._data.keys())})"


def prune_if_needed(used_keys: set[str] | MutableSet[str]) -> None:
    """Evict roughly half of ``used_keys`` in place once it exceeds the bound.

    Call this under the same lock that guards writes to the set.

    When ``used_keys`` is an ``IdempotencyTrackingSet``, calling ``pop()``
    evicts the oldest entries first (FIFO), ensuring recently issued action
    ids remain protected against duplicate replays.
    """
    if len(used_keys) > MAX_TRACKED_KEYS:
        for _ in range(MAX_TRACKED_KEYS // 2):
            used_keys.pop()

