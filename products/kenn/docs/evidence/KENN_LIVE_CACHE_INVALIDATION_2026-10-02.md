# Live-state cache invalidation audit and gain-staging fix — 2 October 2026

A3 slice for [KENN_PLAN.md](../../KENN_PLAN.md): "Live-change cache invalidation for any remaining
state-describing routes". Source-read audit by a read-only agent, then the findings I could check
myself were read directly. Nothing was run against Live.

## What invalidates what

`live_receipt_journal.record_receipt` is the only caller of `invalidate_world_state()`, and that clears only
the world-state cache (2 s TTL, `core/live_world_state.py`). The HTTP routes, recipe apply, undo and MCP
apply all journal their receipts, so they invalidate. The agent tool writes were fixed earlier
([autonomous tool receipts](KENN_AUTONOMOUS_TOOL_RECEIPTS_2026-10-02.md)).

## Fixed: gain staging that fails readback

`LiveActionService.execute_gain_staging` writes every track volume, reads back, and on any mismatch writes
the old volumes back and returns `{"ok": False, "error": "...rolled back.", "step_receipts": [...]}` with no
top-level `receipt`. Callers journal only a top-level receipt, so the cached world state was never dropped
after volumes had moved and moved back, and the rollback writes swallow their own errors. The failure branch
now calls `invalidate_world_state()`. Read directly in the source; the new test reproduces it.

Not changed: the journal, the receipt shape, the rollback itself (see limits).

## Verification

From `products/kenn/apps/backend/src`:

```sh
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_gain_staging_failure_drops_cached_state.py
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests
```

- Scoped: 2 passed (new file), plus the 7 existing gain-staging tests still pass.
- Full backend: 3,532 passed, 12 skipped, no failures (124.29 s), the earlier 3,530 plus two new cases.
- Mutation check: with `live_action_service.py` reverted to HEAD, the failed-readback case fails and the
  refused-run control passes (1 failed, 1 passed). The edited file was restored and byte-compared.

## Open findings, not fixed

Agent-reported from reading source; items marked "read" I checked myself.

- `mixing_doctor._latest_session_state` (read): refreshed by a 2 s poll thread with no timestamp, and
  `LiveActionService.snapshot()` falls back to it when the live read is offline, returning it as connected.
  If the poll thread died, that data would never age out. Clearing it on a write would show "unknown" until
  the next poll, so this needs an age stamp, not an invalidation; left alone.
- `server.py` `_RETURNS_CACHE` (20 s, no invalidation): stale after a return-track create or rename, which
  affects `_chat_wants_live` routing. Not read by me.
- `ableton_osc_bridge.load_browser_preset` uses a query path rather than send-only, so the bridge's 1.5 s
  session cache is not cleared; and a poll thread can re-cache pre-write state between a write and its
  lock. Suspected, forced readback usually heals it. Needs real-Live timing.
- `live_command.handle_command` fail-safe wrapper: an exception after a write leaves no receipt, so nothing
  is journaled. Suspected.
- `describe_recent_changes` reads only the journal, so writes with no journaled receipt are invisible to
  "what changed".
- Edits made directly in Live invalidate nothing; the TTLs apply. By design per the `live_world_state.py`
  docstring.
- Session-memory semantic cache (1 h) is not tied to receipts; guarded only for follow-up-type queries.
  Whether it ever stores Live-state answers at runtime is unverified.

## Limits

- The gain-staging rollback still ignores errors, so a failed rollback leaves Live changed with no journal
  entry or Undo target. This slice drops the stale cache only.
- The agent could not verify `ControlDeckMCPBackend` caching or the midi_clip, clip and sample-import
  services' failure shapes beyond their call sites.

## Exact changed files

Paths are relative to `products/kenn`.

- `apps/backend/src/kenn/core/live_action_service.py`: invalidate in the `execute_gain_staging` failure branch.
- `apps/backend/src/kenn/tests/test_gain_staging_failure_drops_cached_state.py` (new, 2 cases).
- `docs/evidence/KENN_LIVE_CACHE_INVALIDATION_2026-10-02.md`: this receipt.
- `KENN_PLAN.md`: A3 progress note.
