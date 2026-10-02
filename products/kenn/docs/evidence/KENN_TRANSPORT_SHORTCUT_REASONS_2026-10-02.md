# Play/stop shortcut refusals — 2 October 2026

A4 slice, in [KENN_PLAN.md](../../KENN_PLAN.md). It finishes the audit of
`chat_answer._short_circuit_evaluator` started in [KENN_CHAT_STATUS_2026-10-02.md](KENN_CHAT_STATUS_2026-10-02.md).

## Audit result for `_short_circuit_evaluator`

- Status text: already fixed (configured inference and cached Live observations only).
- Cancel reply: already fixed ([dismissal](KENN_CONFIRMATION_DISMISSAL_2026-10-02.md)).
- Transport branches: both call `LiveActionService.propose_transport_action`, which validates the
  action, reads a Live snapshot and issues a token bound to the exact proposal. They are not a bypass.
  The one unconditional claim left was in their refusal.

## Changed behavior

Typing "play" or "stop" when the service refused answered "Ableton Live is not currently reachable on
OSC port 11000" every time. The service refuses only for an unsupported action or when Live is offline
or returned no usable snapshot, so the text hard-coded a port and said "not reachable" for a Live that
had answered. Both branches now go through one `_transport_shortcut` helper that repeats the service's
own error ("I can't start playback: Ableton Live is offline or returned no usable snapshot."). The
accepted path is unchanged, including the proposal and token.

## Verification

From `products/kenn/apps/backend/src`:

```sh
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_transport_shortcut_reasons.py kenn/tests/test_chat_status_observations.py
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests
```

- Scoped: 25 passed, 4 of them new (`test_transport_shortcut_reasons.py`).
- Full backend: 3,524 passed, 12 skipped, no failures (124.00 s), the earlier 3,520 plus the four new cases.
- Putting the fixed sentence back made the two refusal cases fail; the file was restored and byte-compared.

No model was loaded, nothing was written to Live, no dependency or CI file changed.

## Limits

- The service is a fake. The wording of a real refusal comes from `propose_transport_action` and can change with it.
- This does not probe Live; the answer is only as current as the service's snapshot.

## Exact changed files

Paths are relative to `products/kenn`.

- `apps/backend/src/kenn/core/chat_answer.py`: `_transport_shortcut`, replacing two copied branches.
- `apps/backend/src/kenn/tests/test_transport_shortcut_reasons.py` (new, 4 cases).
- `docs/evidence/KENN_TRANSPORT_SHORTCUT_REASONS_2026-10-02.md`: this receipt.
- `KENN_PLAN.md`: A4 sub-bullet and tick.
