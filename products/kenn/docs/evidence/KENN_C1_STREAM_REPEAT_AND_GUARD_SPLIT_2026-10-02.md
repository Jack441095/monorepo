# Stream repeat, and a guard that cut good answers at "dB" — 2 October 2026

Recorded source: `f87a6662` plus the guard change below. The [numeric receipt](KENN_C1_STREAM_REPEAT_2026-10-02.json) is
a second run of the [30-question stream baseline](KENN_C1_STREAM_30Q_2026-10-02.md): same Mac, model, index, questions,
order and isolation, run after the payload run finished. This run also captured answer text with `--capture-answers`;
that file stays in scratch and is not committed.

## Run to run

| | run 1 | run 2 |
| --- | ---: | ---: |
| Accepted of 29 attempted | 22 | 23 |
| Rejected | 7 | 6 |
| Completion median, all 30 | 18.9 s | 17.5 s |
| Completion p95, all 30 | 28.5 s | 25.2 s |
| First token median / p95 | 3.4 / 8.9 s | 3.2 / 4.2 s |
| Accepted within 15 s (of 30) | 0 | 3 |
| Accepted within 20 s (of 30) | 10 | 14 |

The 15 s gate is still failed (3 of 30, fastest 12.4 s). The two runs differ by a few seconds in most rows, so a gap
under about 3 s in the medians is within noise on this evidence (two runs). Rejections are not random: `home-vocal-recording`,
`streaming-loudness`, `gain-staging`, `sidechain-bass-disappears` and `delay-fade-glitch` were rejected in both runs,
with a different number cited in some. Run 1's `bass-processing` was rejected and run 2's was accepted.

## Reading the rejected rows against their sources

For each rejected question we pulled the measurements the retrieved evidence actually contains (the guard's allowed
set, from real retrieval, no model call):

| Question | Evidence has | Guard stopped on |
| --- | --- | --- |
| why does my bass disappear when the kick plays | no measurements | `60hz`, `80hz` / `100hz`, `60hz` |
| gain staging before mixing | no measurements | `-6db` / `-0.1db` |
| what LUFS target for streaming mastering | `-14 LUFS`, `-1 dBFS`, `-0.3 dBTP` | `-1db` / `-0.3db` |
| tips for recording vocals at home | `-6 dBFS` | `-6db` (both runs) |
| glitchy delay fade mode effect | no measurements | `0.5hz` (both runs) |

Three questions have sources with no numbers, so any number the model writes there is unsupported and the guard is
right. The other two are not that: the sources contain the number and the guard stopped anyway.

We ran those two questions through the real model with a log on the guard. The model writes "-6" then " dB" then "FS",
and "-0.3" then " dB" then "TP", as separate tokens. After the " dB" token the guard's window ends in "-6 dB", which is
a complete `-6db` to the regex (its `(?![a-z0-9])` lookahead sees the end of the window, not the next token), and
`-6db` is not in the allowed set that holds `-6dbfs`. So it cut an answer whose number the sources support.

## Change

`core/chat_grounding.py`, `StreamedAnswerGuard.check`: when the window ends in "db" the last two characters are left
out of the judgment. The carry keeps the text, so the next token's window sees "dBFS" or "dBTP" whole. A plain "-3 dB" the
sources lack is still caught as soon as anything other than FS/TP follows. A "dB" that is the very last thing the model
writes is not judged by the guard; the full gate at completion still judges it.

Tests (`test_streamed_generation_prefix_guard.py`):
`test_a_unit_the_tokenizer_splits_after_db_is_not_judged_as_plain_db` and
`test_a_plain_db_the_sources_do_not_have_is_still_caught_once_the_unit_is_finished`. Both fail without the change.
With the change, the two real questions above are accepted with no warnings (one run each).

## Verification

KENN suite with pytest's cache plugin off (`-p no:cacheprovider`): 3,557 passed, 5 skipped, 0 failed. With the plugin
on, `test_server_smoke.py::test_main_chat_can_combine_explicit_mix_review_and_plugin_evidence` fails in the full run
(it passes alone). It fails the same way with this change removed, so it is not caused by it. We did not find the cause;
it passed in an earlier full run the same night. Not deleted or changed: `apps/backend/.pytest_cache`.
On 3 Oct a full run with `-o cache_dir=<fresh temp dir>` passed too (3,557 passed, 5 skipped, 0 failed, 109 s), so the
failure goes away without the old cache dir and the plugin turned off, which points at state in `apps/backend/.pytest_cache`
(its `lastfailed` lists 27 old entries). We have not worked out how that state breaks the test, and the repo has no pytest
`addopts` that would reorder tests from it. Still not deleted.

## Limits

Two stream runs. Two of the five rejected questions were affected by the split; across run 1's seven rejections the
same pattern covers `-0.3db` and `-6db`, so about two of seven rejections per run were this bug, which would move
acceptance from 76% towards 83%. We have not re-run all 30 with the fix. The three unaffected measurement rejections
stand. The Live-change rejection (`wwise-events`) was not examined. Gate speed is unchanged by this fix: it removes
rejections, not seconds.

## Run 3, with the guard fix (3 October 2026)

Recorded source: `6368d5cb`. [Receipt](KENN_C1_STREAM_RUN3_GUARD_FIX_2026-10-03.json). Same Mac, model, index, questions,
order and isolation as runs 1 and 2, run alone after the L2 audit was committed.

| | run 1 | run 2 | run 3 (fix) |
| --- | ---: | ---: | ---: |
| Accepted of 29 attempted | 22 | 23 | 25 |
| Rejected | 7 | 6 | 4 |
| Completion median, all 30 | 18.9 s | 17.5 s | 16.7 s |
| Completion p95, all 30 | 28.5 s | 25.2 s | 27.2 s |
| First token median / p95 | 3.4 / 8.9 s | 3.2 / 4.2 s | 3.0 / 3.8 s |
| Accepted within 15 s (of 30) | 0 | 3 | 4 |
| Accepted within 20 s (of 30) | 10 | 14 | 18 |

- `home-vocal-recording` and `streaming-loudness`, the two false positives, are both accepted now (16.9 s and 11.3 s).
- The four rejections are `bass-processing` (`120hz`), `gain-staging` (`-6db`), `cpu-overload` (`80%`) and
  `delay-fade-glitch` (`0.5hz`). Gain staging and the glitchy delay have no numbers in their sources, so those two
  stand as real fabrications. `bass-processing` was accepted in run 2 and rejected in run 1, so it moves between runs.
  `cpu-overload` was accepted in run 2 and is new here. We did not read the `120hz` or `80%` rejections against their
  sources, so we can't say whether the guard was right on those.
- The 15 s gate is still failed: 4 of 30, fastest accepted 11.3 s. Acceptance went up by about two, which matches the
  two rows the fix was written for, but one run is inside the noise we saw between runs 1 and 2, so we are not claiming
  more than that. The faster medians are within that noise too.
- C1 stays open.
