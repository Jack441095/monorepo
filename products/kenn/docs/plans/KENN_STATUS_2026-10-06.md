# KENN status, 6 Oct 2026

KENN is the local AI assistant for Ableton Live. It answers audio and Live questions from approved notes, using a
small model running on the Mac, and it can inspect and control Live. The current milestone is the 70% gate.
`KENN_PLAN.md` stays the roadmap; this page is a snapshot.

## The gate

Both halves are run on the Mac, with the gate index pinned at `v-5f6964698b76`. An answer counts only if the model's
answer is accepted within 15 s.

| Half | Needed | Where we are | State |
| --- | --- | --- | --- |
| Probe: 44 hard questions, 3 runs in a row | 31 or more each run | 32 / 33 / 31 | **Passed** on 5 Oct, 4B with allowed figures |
| Held-out: 72 unseen questions | 51 | 42 | **9 short** |

The probe pass is thin: run 3 landed exactly on 31.

The main reason held-out answers fail is unsupported measurements. The model states a figure (a frequency, a level,
a time) that the excerpts don't print, and the grounding gate rejects the answer. There are 15 of these on main.
Showing the model which figures the notes do contain ("allowed figures") helped the probe but didn't move this
count.

## What's on main (local, not pushed)

Merged on 5 Oct after adversary review:

- allowed figures
- shipping the Ollama brain
- the suggest test

The full suite passed on the merged tree: 4389 passed, 9 skipped. The kenn-app sync is still at the earlier main
`681dc674`.

## In flight

**Retrieval ranking** (`draft/retrieval-ranking`, reviewed, not merged)

- Hyphenated words now search their parts too, so "linear-phase" finds a note that writes "linear phase".
- A note found by meaning but outside BM25's top 60 keeps its own keyword score, instead of scoring 0 and being
  dropped.
- Result: the probe went to 35 / 35 / 32 against about 32. The held-out set went to 38 against 42, which is within
  the noise we've seen.
- Next: repeat the benchmark on a quiet Mac. The last run overlapped Time Machine and other jobs, so its timings
  don't count. Merge if it holds up.

**Answer fine-tune on the 4B** (`draft/answer-tune`). Full record in `KENN_ANSWER_TUNE_2026-10-06.md`.

- Teaches the 4B the answer habits the gate checks for: short answers, built from the excerpts, with no figures the
  excerpts don't print. The 32B teacher writes the examples.
- Questions: 977, with a strict filter that keeps probe and held-out material out.
- Teacher answers: stopped at 329 questions today, giving 174 kept examples (156 train, 18 valid). Targets no
  longer include the Sources block KENN appends itself.
- Grading page for 40 of them: https://claude.ai/artifact/BrcSDREy6ZLLRxskoDdq3J
- Training on GPU 0 is staged but not started. Copying data to the box needs Jack's go-ahead.
- The tune is kept only if the probe and held-out both rise, the median time is no slower, and the negative-advice
  guard still holds.

## Open items on the gate path

- Treat an explicit "Insufficient context" reply as an honest decline, not a dropped answer.
- Leftovers from the allowed-figures review, none blocking:
  - list specialist figures first;
  - give stem-scan figures more than 300 characters of context;
  - add a test that `make_answer` passes the specialist text through.
- Advice questions that name a track ("advice on drum bus compression") should go to the model, not to Live
  inspection.
- Stop a template counting as a model answer when the quality check swaps it in after generation.
- Answers that fit in 128 tokens instead of being cut off and rejected (`draft/answer-fits-128-tokens`).
- Lower the prose temperature, measured on its own.
- A reference-numbers note for the values the model keeps inventing. Needs Jack and a box rebuild.

## Decisions waiting on Jack

1. **Answer tune.** Start training now on 156 examples, or finish the teacher pass first: about 4 more hours, for
   about 510 examples. Also, grade before training as the plan says, or train while grading.
2. **Retrieval ranking.** Schedule a quiet-Mac benchmark so it can be merged or dropped.
3. **Box housekeeping.** Still with Jack from earlier:
   - the box cleanup;
   - the notes rebuild;
   - replacing the 6 notes on the Mac;
   - the old copies on the box (`kenn-GPU`, `kenn-regression-20260910`, `kenn_retrieval`).

## Parked, by Jack's call

These are not on the path until KENN is good enough:

- the Developer ID and the 3-tester pilot
- MLX and speculative decoding
- hosted escalation, which is still Jack's open call
