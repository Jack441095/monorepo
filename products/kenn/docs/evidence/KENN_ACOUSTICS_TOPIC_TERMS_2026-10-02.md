# Room-mode and bass-null questions route to the acoustics topic — 2 October 2026

A3 slice. It supports [KENN_PLAN.md](../../KENN_PLAN.md) and closes one of the four held-out rows listed
in [the symptom-report receipt](KENN_SYMPTOM_REPORT_OFFLINE_ADVICE_2026-10-02.md).

## Reproduced defect and changed behavior

`upgrade-room-null` asks about "a very narrow bass null at my chair" and a monitor-EQ boost. The question
never says "room" or "acoustic", so `query_topics` returned `bass, mixing, eq, monitoring` and the
`acoustics` topic never fired. `room-acoustics-monitor-placement.md` (tags: acoustics, room modes,
listening position) ranked 4th behind three EQ notes. The `acoustics` topic terms in
`retrieval/retrieval.py` gained `"room mode"`, `"room modes"`, `"listening position"`, `"bass null"` and
`"bass trap"`. Nothing else in ranking, weights, notes or expected outputs changed.

## Verification

From `products/kenn/apps/backend/src`:

```sh
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_acoustics_topic_room_modes.py
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests
```

From `products/kenn/packages/chat`:

```sh
../../apps/backend/.venv/bin/python -m pytest -q -p no:randomly tests
```

- Scoped: 4 new cases (three room-mode or null phrasings are `acoustics`; a plain thin-vocal question is
  not). On the `HEAD` copy of `retrieval.py` the three acoustics cases fail and the control passes.
- Full backend: 3,544 passed, 12 skipped, no failures (123.07 s).
- Package wrapper: `upgrade-room-null` now passes the held-out run. The same two tests
  (`test_full_evaluation_receipt_passes`, `test_full_chat_coverage_receipt_passes`) still fail, with 3 held-out
  rows (`harsh-after-mastering`, `eval-followup-snare-layer-mono`, `upgrade-buffer-recording`) and 2 coverage rows
  (`arrangement-energy-transitions`, `ambiguity-thin-vocal-eq-vs-recording`) open. 72 passed, 2 failed, as before.

## Limits

- The row passes because the room note is now among the cited sources, which is what the case checks. The
  answer is not good. The first source is still a FabFilter note, and the generated steps mix room-treatment
  advice with unrelated ones (an HPF on the monitors, a gate in ducking mode). It does not say that a narrow
  null caused by cancellation should not be EQ-boosted, which the room note does say. Fixing that is about
  how the wrapper composes an answer from its top sources, not routing, and was left alone.
- The new terms are a judgement about what these phrasings mean, tested on three wordings. Other
  null or room-mode wordings were not surveyed.
- The semantic model was not warmed for this run; ranking with it warmed was not measured for this row.

## Exact changed files

Paths are relative to `products/kenn`.

- `apps/backend/src/kenn/retrieval/retrieval.py`: five terms in the `acoustics` topic.
- `apps/backend/src/kenn/tests/test_acoustics_topic_room_modes.py` (new, 4 cases).
- `docs/evidence/KENN_ACOUSTICS_TOPIC_TERMS_2026-10-02.md`: this receipt.
- `KENN_PLAN.md`: A3 sub-bullet.
