# A symptom report with Live offline falls through to advice — 2 October 2026

Part of the A3 package-wrapper evaluation item in [KENN_PLAN.md](../../KENN_PLAN.md). Follows
[KENN_MOBILE_AUDIO_MEMORY_ROUTE_2026-10-02.md](KENN_MOBILE_AUDIO_MEMORY_ROUTE_2026-10-02.md).

## Reproduced defect

Held-out case `new-topic-does-not-inherit-old-diagnosis` sends "New topic: my vocal is buried in the
chorus." through the engine with a session id. The answer was "I cannot control Ableton until the
AbletonOSC-backed KENN companion returns a fresh Live snapshot", at high confidence.

Cause: `SubjectiveTranslator.can_translate` matches symptom wording ("buried") as well as commands
("make the vocal cut through"). `KennOrchestrator.classify` therefore sent the statement to
`ableton_controller`, `_dispatch_ableton` ran it through `handle_command`, and with no Live snapshot
the control error became the whole answer. The same plain question without a session id gave the same
reply, so it was not a session effect.

## Changed behavior

In `_dispatch_ableton` (`orchestrator.py`), when the command gateway reports `offline` and the query has
no write verb (`_ABLETON_WRITE_INTENT_RE`), it returns `None`, so `dispatch` falls through to the normal
advice path. An explicit write ("mute the vocal track") with Live offline still says Live is offline.
With Live connected, nothing changes: a symptom report still reaches `handle_command` and can come back
as a confirmation proposal.

Not changed: `classify`, the subjective patterns, the proposal/confirmation gate, expected eval outputs.

## Verification

From `products/kenn/apps/backend/src`:

```sh
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_subjective_symptom_offline_falls_to_advice.py
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests
```

- Scoped: 3 passed (new file).
- Full backend: 3,530 passed, 12 skipped, no failures (124.25 s), the earlier 3,527 plus the three new cases.
- Mutation check: with `orchestrator.py` reverted to HEAD, the symptom-offline case fails and the other two
  pass (1 failed, 2 passed). The edited file was restored and byte-compared.
- Held-out `eval_runner.run_evaluation()` from `packages/chat`: `new-topic-does-not-inherit-old-diagnosis`
  now passes; five failures become four.

No model was loaded for the evaluation (`allow_llm=False`), nothing was written to Live, the index was
not rebuilt, no dependency or CI file changed.

## Diagnosis of the four held-out rows still failing

Checked with the semantic embedder warmed (`warm_index()`, mode `hybrid`) as well as the default
`bm25_only`; the same four fail either way, so this is not a warm-up effect.

| Row | Finding |
| --- | --- |
| `harsh-after-mastering` | The engine answers it with the right diagnosis (limiter/clipper/saturation first). The public wrapper abstains because its retrieval-only gate finds no strong source, and the top lexical hits are mix-bus and low-mid notes, not a mastering-harshness note. Looks like a corpus gap: the abstention follows the stated rule not to answer ungrounded. Fixing it means a new reviewed note and an index rebuild. |
| `eval-followup-snare-layer-mono` | `snare-clap-layering.md` is in the active index but ranks 13th for the combined question (stereo-width and layering notes outrank it). |
| `upgrade-buffer-recording` | `audio-interface-buffer-latency.md` ranks 5th (vocal-recording notes outrank it); the answer is a generic vocal-recording workflow with no buffer figure. |
| `upgrade-room-null` | `room-acoustics-monitor-placement.md` ranks 4th behind three EQ notes, and the answer built from the top three recommends boosting bass bands. That is the more worrying of the four, since a null should not be EQ-boosted. |

None of these were tuned: ranking weights, multipliers, notes and expected outputs are untouched.

## Limits

- The fall-through applies to any query that reaches `_dispatch_ableton` with no write verb and Live
  offline, not only symptom reports. Other subjective phrasings ("make the vocal cut through") now also
  get advice when offline instead of the offline notice.
- The orchestrator is reached from the full engine, not from the public wrapper's retrieval-only path.
- Live was not touched; the connected case is covered by a stub, not a real session.

## Exact changed files

Paths are relative to `products/kenn`.

- `apps/backend/src/kenn/orchestrator.py`: offline fall-through in `_dispatch_ableton`.
- `apps/backend/src/kenn/tests/test_subjective_symptom_offline_falls_to_advice.py` (new, 3 cases).
- `docs/evidence/KENN_SYMPTOM_REPORT_OFFLINE_ADVICE_2026-10-02.md`: this receipt.
- `KENN_PLAN.md`: A3 progress note.
