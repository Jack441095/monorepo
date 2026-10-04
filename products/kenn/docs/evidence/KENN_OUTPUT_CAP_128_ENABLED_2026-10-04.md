# Output cap 128 enabled, 4 October 2026

Jack asked for the cap to be turned on. It is on for every prose answer mode; the 15 s gate is not claimed.

## What changed

`apps/backend/src/kenn/llm/llm_rewrite.py`: the ceiling for the ten chat modes and `voice` goes from 384, 256 for `quick_fix` and 220 for `voice` to 128. `command` keeps 256 because a truncated command plan is not a plan. Paraphrase, follow-up and confirm limits are untouched (they were already at or under 128). The MLX path reads the same table, so it follows.

Tests: `test_llm_generation_bounds.py` now pins 128 for prose and 256 for command, in place of the old "must clear the 303-token maximum" test. Two cache-key tests relied on quick_fix and the general mode having different caps; they set a smaller cap with `monkeypatch` so the case still exercises a changed cap.

## What the earlier evidence says about it

From the [cap trial](KENN_C2_MODEL_PHASES_AND_OUTPUT_CAP_2026-10-03.md) and the [Mac baseline](KENN_MAC_BASELINE_PROBE_AND_OUTPUT_CAP_2026-10-03.md), five questions per surface, one pass, Live closed:

- Accepted within 15 s went from 2/5 and 1/5 to 4/5 and 4/5 in the Mac baseline run. The earlier trial was 2/5 to 4/5 on stream and 2/5 to 1/5 on payload, so the payload gain did not repeat.
- Every accepted capped answer stopped on `length`. The last step or the explanation was cut mid-sentence in most of the ones read, and one citation marker was cut.
- Decode rate is unchanged, so the gain is fewer tokens, not a faster model.

## Not done, and what it means

- The gate (at least 70% accepted model answers inside 15 s, Live open) has not been rerun with the cap on. C1, C2 and C3 stay open.
- Cut-off answers are delivered as they come. Trimming a capped answer back to its last whole sentence is the obvious next change and was not made.
- To undo: set `_GENERAL_MAX_TOKENS` back to 384 and `voice` to 220 in `llm_rewrite.py`.
- Next check on the Mac: rerun the 47-question probe with this commit and read the review sheet for cut-off answers.
