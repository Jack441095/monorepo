"""Each Live-mutating service tracks confirmed action ids in a module-level
set so a replayed confirmation can never repeat a write. Four of the five
such services (clip_audition_service, midi_clip_service, sample_import_service,
live_recipe) never capped that set -- only live_action_service.py had a bound
-- so it grew for the life of the process. This verifies the shared
kenn.core.idempotency_bounds.prune_if_needed fix actually keeps each one
bounded.

A previous revision of prune_if_needed called set.clear(), which wiped the
entire replay-protection window. The corrected behavior evicts roughly half
(prune-before-add at the call sites), so memory stays bounded while recently
issued action ids -- including the just-finished key -- remain protected.
"""

from __future__ import annotations

from kenn.core.idempotency_bounds import MAX_TRACKED_KEYS, prune_if_needed


def test_prune_if_needed_keeps_set_bounded_without_wiping_replay_protection() -> None:
    keys = {f"action-{i}" for i in range(MAX_TRACKED_KEYS)}
    prune_if_needed(keys)
    assert len(keys) == MAX_TRACKED_KEYS

    keys.add("action-overflow")
    before = set(keys)
    prune_if_needed(keys)
    # Bounded: roughly half evicted, never the whole window.
    assert len(keys) <= MAX_TRACKED_KEYS
    assert len(keys) >= MAX_TRACKED_KEYS // 2 - 1
    assert keys != set()
    assert keys <= before


def test_clip_audition_service_finish_prunes_a_bloated_key_set() -> None:
    from kenn.core import clip_audition_service as module

    module._USED_IDEMPOTENCY_KEYS.clear()
    module._IN_FLIGHT_IDEMPOTENCY_KEYS.clear()
    try:
        module._USED_IDEMPOTENCY_KEYS.update(f"stale-{i}" for i in range(MAX_TRACKED_KEYS + 1))
        module._finish("fresh-key")
        assert len(module._USED_IDEMPOTENCY_KEYS) <= MAX_TRACKED_KEYS + 1
        assert "fresh-key" in module._USED_IDEMPOTENCY_KEYS
    finally:
        module._USED_IDEMPOTENCY_KEYS.clear()
        module._IN_FLIGHT_IDEMPOTENCY_KEYS.clear()


def test_midi_clip_service_finish_idempotency_prunes_a_bloated_key_set() -> None:
    from kenn.core import midi_clip_service as module

    module._USED_IDEMPOTENCY_KEYS.clear()
    module._IN_FLIGHT_IDEMPOTENCY_KEYS.clear()
    try:
        module._USED_IDEMPOTENCY_KEYS.update(f"stale-{i}" for i in range(MAX_TRACKED_KEYS + 1))
        module._finish_idempotency("fresh-key")
        assert len(module._USED_IDEMPOTENCY_KEYS) <= MAX_TRACKED_KEYS + 1
        assert "fresh-key" in module._USED_IDEMPOTENCY_KEYS
    finally:
        module._USED_IDEMPOTENCY_KEYS.clear()
        module._IN_FLIGHT_IDEMPOTENCY_KEYS.clear()


def test_sample_import_service_finish_idempotency_prunes_a_bloated_key_set() -> None:
    from kenn.core import sample_import_service as module

    module._USED_IDEMPOTENCY_KEYS.clear()
    module._IN_FLIGHT_IDEMPOTENCY_KEYS.clear()
    try:
        module._USED_IDEMPOTENCY_KEYS.update(f"stale-{i}" for i in range(MAX_TRACKED_KEYS + 1))
        module._finish_idempotency("fresh-key")
        assert len(module._USED_IDEMPOTENCY_KEYS) <= MAX_TRACKED_KEYS + 1
        assert "fresh-key" in module._USED_IDEMPOTENCY_KEYS
    finally:
        module._USED_IDEMPOTENCY_KEYS.clear()
        module._IN_FLIGHT_IDEMPOTENCY_KEYS.clear()


def test_live_recipe_mark_used_prunes_a_bloated_key_set() -> None:
    from kenn.core import live_recipe as module

    module._USED_IDEMPOTENCY_KEYS.clear()
    module._IN_FLIGHT_IDEMPOTENCY_KEYS.clear()
    try:
        module._USED_IDEMPOTENCY_KEYS.update(f"stale-{i}" for i in range(MAX_TRACKED_KEYS + 1))
        module._mark_used("fresh-key")
        assert len(module._USED_IDEMPOTENCY_KEYS) <= MAX_TRACKED_KEYS + 1
        assert "fresh-key" in module._USED_IDEMPOTENCY_KEYS
    finally:
        module._USED_IDEMPOTENCY_KEYS.clear()
        module._IN_FLIGHT_IDEMPOTENCY_KEYS.clear()
