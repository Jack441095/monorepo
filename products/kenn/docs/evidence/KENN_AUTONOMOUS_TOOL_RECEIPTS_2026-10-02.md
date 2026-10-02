# Autonomous-tool writes and the receipt journal — 2 October 2026

A3 slice. It supports [KENN_PLAN.md](../../KENN_PLAN.md) and follows
[KENN_CONFIRMATION_TOKEN_ALIAS_2026-10-02.md](KENN_CONFIRMATION_TOKEN_ALIAS_2026-10-02.md).

## Reproduced defect and changed behavior

The HTTP apply routes record every receipt with `record_receipt(receipt, session_id=...)`, and Undo
looks receipts up in that journal. The agent tools in `autonomous_agent.py` (`_safe_track_action`,
`_safe_transport_action`, and `tool_set_ableton_parameter`'s device path) ran the same confirmed
writes but only handed the receipt back to the model. A volume, pan, mute, solo, arm, transport or
device-parameter change made that way was in Live and in the chat, but not in the journal, so Undo
had nothing to find. The journal write also clears the cached world state, so those writes left
stale Live state in the cache too.

New `_journal_receipt` in `autonomous_agent.py` records the receipt after each of the three execute
calls. A failed write is journaled as well, matching the HTTP routes: Live may have moved even
though readback disagreed. A result with no receipt journals nothing.

Not changed: the proposal and confirmation checks, the exact-binding checks, `_daw_write_denied`, and
the shape returned to the model.

## Verification

From `products/kenn/apps/backend/src`:

```sh
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_autonomous_tool_receipts.py
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests
```

- Scoped: 6 passed (new file `test_autonomous_tool_receipts.py`).
- Full backend: 3,518 passed, 12 skipped, no failures (121.69 s), the earlier 3,512 plus the six new cases.
- Each of the three `_journal_receipt` calls was deleted in turn and the file failed every time
  (2, 1 and 1 failures). The edited file was restored and byte-compared.

No model was loaded, nothing was written to Live, no dependency or CI file changed.

## Limits

- The service is a fake that returns a canned receipt. This proves the journal call, not that the
  real `LiveActionService.execute` returns a receipt Undo can reverse for every action.
- `tool_set_ableton_macro` goes through `tool_set_ableton_parameter`, so it is covered; no other
  agent tool writes to Live through a different path.
- Undo itself was not exercised end to end here.

## Exact changed files

Paths are relative to `products/kenn`.

- `apps/backend/src/kenn/autonomous_agent.py`: `_journal_receipt` and its three call sites.
- `apps/backend/src/kenn/tests/test_autonomous_tool_receipts.py` (new, 6 cases).
- `docs/evidence/KENN_AUTONOMOUS_TOOL_RECEIPTS_2026-10-02.md`: this receipt.
- `KENN_PLAN.md`: A3 sub-bullet.
