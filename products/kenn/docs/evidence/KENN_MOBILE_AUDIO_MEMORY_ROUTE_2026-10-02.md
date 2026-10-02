# Mobile-build audio memory questions route as game audio — 2 October 2026

Part of the A3 package-wrapper evaluation item in [KENN_PLAN.md](../../KENN_PLAN.md). It follows
[KENN_ACTIVE_PATH_CLEANUP_2026-10-02.md](KENN_ACTIVE_PATH_CLEANUP_2026-10-02.md), which recorded the failures.

## Diagnosis of the eight failing rows

Run from `packages/chat` with `eval_chat_coverage.evaluate()` and `eval_runner.run_evaluation()`
(no LLM, no index rebuild):

| Row | Cause found |
| --- | --- |
| `wwise-mobile-ambience-memory` | **Routing gap, fixed here.** The wrapper refuses game audio by route. This one ("mobile build runs out of audio memory…") did not route to `game_audio`, because it names none of the existing terms, so the wrapper answered it instead of abstaining. |
| `arrangement-energy-transitions` | Retrieval ranking: three other arrangement notes outrank `arrangement-energy-and-transitions.md`. The answer is plausible; the note is just not in the top three. Open. |
| `ambiguity-thin-vocal-eq-vs-recording` | Retrieval ranking: `harsh-vocal-fix.md` and the iZotope EQ notes outrank `thin-vocal-body.md` for "recorded too far from the mic". Open. |
| `harsh-after-mastering` | Abstains (low confidence, no sources) where the case wants a limiter/clipper/saturation diagnosis. Open. |
| `new-topic-does-not-inherit-old-diagnosis` | Answers with high confidence but zero sources, and without the expected diagnosis lines. Open. |
| `eval-followup-snare-layer-mono` | Follow-up retrieves three sources, none is `snare-clap-layering`. Open. |
| `upgrade-buffer-recording` | Answer lacks any of "64", "128", "buffer". Open. |
| `upgrade-room-null` | Answer lacks "null/cancellation/position/room" and the `room-acoustics-monitor-placement` source. Open. |

The seven open rows are retrieval ranking or answer-content problems. Fixing them means changing
ranking or notes, which needs the sealed-holdout and provenance checks and should not be tuned
against these same rows, so they were left alone.

## Changed behavior

`game_audio` topic terms in `retrieval/retrieval.py` gain "mobile build" and "audio memory". The question now
classifies as `game_audio` and routes there in the backend as well as in the wrapper, so the wrapper
refuses it like its siblings. The coverage receipt goes from 125 of 128 to 126 of 128.

Not changed: expected outputs, grounding guards, index contents or any note.

## Verification

From `products/kenn/apps/backend/src`:

```sh
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_game_audio_routing_mobile_memory.py
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests
```

From `products/kenn/packages/chat`:

```sh
../../apps/backend/.venv/bin/python -m pytest -q -p no:randomly tests
```

- Scoped: 3 passed (new file).
- Full backend: 3,527 passed, 12 skipped, no failures (137.22 s), the earlier 3,524 plus the three new cases.
- Package wrapper: 72 passed, 2 failed, the same two tests as before. Their failing rows are now two (coverage) and five (held-out).
- Mutation check: with `retrieval.py` reverted to the previous commit, the two positive cases fail and the negative control passes (2 failed, 1 passed). The edited file was restored and the diff is empty.

No model was loaded, nothing was written to Live, the index was not rebuilt, no dependency or CI file changed.

## Limits

- Two new substrings can over-match: any question containing "audio memory" or "mobile build" becomes
  game audio. Neither phrase is common in the mix or Ableton corpus, but only the cases in the suite were checked.
- The two package tests still fail, so that A3 item stays open.

## Exact changed files

Paths are relative to `products/kenn`.

- `apps/backend/src/kenn/retrieval/retrieval.py`: two terms in the `game_audio` topic list.
- `apps/backend/src/kenn/tests/test_game_audio_routing_mobile_memory.py` (new, 3 cases).
- `docs/evidence/KENN_MOBILE_AUDIO_MEMORY_ROUTE_2026-10-02.md`: this receipt.
- `KENN_PLAN.md`: A3 progress note.
