# Three evaluation rows only passed through a "Related questions" echo — 2 October 2026

A3 diagnosis, no behavior change. It supports [KENN_PLAN.md](../../KENN_PLAN.md) and refines the causes in
[the symptom-report receipt](KENN_SYMPTOM_REPORT_OFFLINE_ADVICE_2026-10-02.md).

## What was found

Commit `f0ebeba6` ("Exclude question-list echoes before retrieval candidate limits", 2 Oct 2026) stops
chunks whose section is `Related questions` from being returned by BM25 or the dense candidate list, because a
question list can repeat a query without giving any answer evidence. Three open rows had been passing only
because of that echo; the question in each is a line in the expected note's own question list:

| Row | Expected source | Where the question appears |
| --- | --- | --- |
| `arrangement-energy-transitions` (coverage) | `arrangement-energy-and-transitions` | "What should I do next if my track feels boring?" |
| `ambiguity-thin-vocal-eq-vs-recording` (coverage) | `thin vocal` (`thin-vocal-body`) | "Can EQ fix a vocal that was recorded too far from the mic?" |
| `eval-followup-snare-layer-mono` (held-out) | `snare-clap-layering` | follow-up to a layered-snare mono complaint |

The first two lines were confirmed by grep in the notes. The third is a multi-turn case that was not grepped line
by line; it is included because it passes in the experiment below.

## Experiment

On a scratch edit that removed both `Related questions` exclusions in `retrieval/retrieval.py` (the dense
candidate filter and the BM25 `continue`), the coverage eval and the wrapper eval were run:

- Coverage: one failure, `bass-processing`. The two coverage rows above pass.
- Wrapper held-out: failures `harsh-after-mastering` and `upgrade-buffer-recording` only. The snare row passes.

So the echo is what made those three rows pass, and allowing it again breaks `bass-processing`, the kind of
echo hit the exclusion was written to stop. The scratch edit was reverted and the file compared byte for byte
with the committed copy. `upgrade-buffer-recording` and `harsh-after-mastering` fail either way, so they are
separate ranking and corpus problems.

## What it means

These are not retrieval regressions to tune away. The rows assert a source that is now reachable only on
answer-bearing chunks, where it ranks lower: `thin-vocal-body` is the 4th distinct note, `arrangement-energy-and-transitions`
11th by chunk. Closing them honestly means one of: add answer-bearing wording to those notes and rebuild the index
(the plan says not to rebuild on this Mac, and the notes are not in git); change what the rows expect; or accept that
the exclusion trades these three for `bass-processing`. That is a decision on eval expectations, so none was made here.

## Verification

- Experiment results above come from `tooling/scripts` (`evaluate()` in `eval_chat_coverage.py`) and
  `packages/chat` (`run_evaluation()`), run once each on the scratch edit.
- No source, test or eval file changed in this slice. `retrieval.py` is byte-identical to `HEAD`.

## Limits

- One experiment per eval, with the semantic model not warmed. Ranking with it warmed was not rechecked.
- It was not checked whether other rows in the larger corpus also depended on an echo and now pass or fail for
  other reasons.
