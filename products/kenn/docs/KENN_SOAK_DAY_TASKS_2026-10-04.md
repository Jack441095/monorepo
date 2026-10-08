# KENN tasks while the soak runs, 4 October 2026

Ticked as each one is done. Nothing here is committed; the code drafts are in the worktree `workspace/worktrees/kenn/answer-fits-128` (branch `draft/answer-fits-128-tokens`).

## Light tasks (no model, no GPU)

- [x] 1. "Educate me on compression" no longer opens as a symptom trace. Learn openers (educate me, teach me, tell me about, walk me through, help me understand, i want to learn, describe) now classify as `deep_explanation`; "my vocal sounds harsh" and the other symptom reports still get the diagnosis shape. Seven new regression cases in `tests/test_answer_mode_advice.py`; the 62 routing tests pass. Patch: `learn-openers.patch` in the scratchpad.
- [x] 2. Audit of the low-recall questions: the notes mostly exist, so the misses are ranking and tokenising, not missing content, and a reranker would not help (details below).
- [x] 3. Review sheet at `/tmp/kenn-run4-review-sheet.md`: the 23 model answers from run 4, with Supported / Applicable / Useful / Cut off boxes. Not committed. Still waiting on Jack to fill it in.
- [x] 4. Reference-matcher fallback is already fixed on this branch, so no failing test to write. Empty, missing or 39-value spectra all come back `available False` with no recipe; only two 40-value spectra give a recipe. The agent tool and the agent loop pass the empty case through the same check. `test_reference_matcher.py` passes (22). The plan ticks this under B1 (that is the plan's B1 "Listening usefulness" section, which has an unticked part still open).

## Task 2 findings: why the low-recall questions missed

Checked against the current index (v-db8c6334cf63) and the probe sources, no model involved.

| Question | Right note exists? | What went wrong |
| --- | --- | --- |
| psy-itd-ild | Yes: "Sound localization through binaural cues and HRTF" | Its Short answer chunk matches "interaural" and "time", but the topic multiplier is 0.45 because the query's topics (mixing, stereo_width, monitoring) are not the note's. It never reaches the top results. Ranking. |
| live-pdc | Yes: "Ableton Live Plugin Delay Compensation (PDC)" and "Device Delay Compensation" | The query also says "limiter" and "return", which pull in Sends And Returns and the manual; the device note ranks 9th by BM25, the plugin one is not in the top 400. The question is also routed to mastering_safety. Ranking and routing. |
| syn-aliasing-osc | Partly: "Sample Rate, Bit Depth, and Aliasing" | The question says "alias", the note says "aliasing", and BM25 does no stemming, so it matches nothing. Nothing in the notes covers band-limited oscillators (polyBLEP etc.), so that half is a missing note. |
| psy-precedence | Partly: Haas content in the two stereo notes | The right notes were retrieved; the answer was the template, and "precedence" is barely in the notes. Mostly missing content. |
| space-haas-mono, dyn-dynamic-eq-vs-multiband | Yes, and retrieved | Retrieval was fine. Recall is low because of the answer (cut off at 128 tokens, or the template). |
| vague-vocals | n/a | Underspecified on purpose; keyword recall is not the right test. |

One real tokenizer bug found on the way: the word pattern keeps a trailing full stop, so a word at the end of a sentence is indexed as "aliasing." and never matches "aliasing". 3,262 of 16,218 index terms end in punctuation. I rebuilt the terms in memory only (no index written) with the stop stripped and ran BM25 on the technique and device-purpose cases (175): hits in the top 4 went from 98 to 103 (technique 29 to 27, device 69 to 76). That is BM25 alone, not the hybrid path the app uses, so it is a hint, not a result. Fixing it needs an index rebuild and the retrieval evals, which is Jack's call. Script: `tokfix_ab.py` in the scratchpad.

Reranker verdict: no. The right notes are not in the candidate list, so reordering the list cannot help. The levers are the topic multiplier on rare exact terms, stemming, and the tokenizer.

## Prompt fixes (drafted, not yet measured)

- [x] Numbers rule and "finish inside the cap" length rule in `llm_rewrite.py`, with tests (241 prompt tests pass). Patch: `answer-fits-128.patch`.
- [x] Measured on the model, 15:08 to 15:19 (results below): no measurable gain, so the drafts are not adopted.

## Soak

- [x] Run 1 of 6 done (11:48, cold start).
- [x] Runs 2 to 6 done (last one 15:06).

## Soak results (six spaced runs, 11:37 to 15:06, fake Live, Live open, 40 minutes apart)

| Run | Model answers / 47 | Accepted / attempted | p50 / p95 / max | Model answers inside 15 s |
| --- | ---: | ---: | --- | ---: |
| 1 (cold start) | 19 | 41% | 12.1 / 16.1 / 16.1 s | 15 of 19 |
| 2 | 19 | 41% | 10.1 / 12.1 / 14.2 s | 19 of 19 |
| 3 | 22 | 48% | 10.1 / 12.1 / 12.2 s | 22 of 22 |
| 4 | 20 | 43% | 10.1 / 12.1 / 12.2 s | 20 of 20 |
| 5 | 20 | 43% | 10.1 / 12.1 / 12.1 s | 20 of 20 |
| 6 | 21 | 46% | 10.1 / 12.1 / 12.1 s | 21 of 21 |

- Speed is stable: after the cold start every model answer came in at 10 to 14 s over five runs. Run 1's cold start had four model answers over 15 s (max 16.1 s).
- Acceptance is stable and low: 41% to 48% of attempts, against the plan's 70%. The gate is still failed on acceptance, not speed.
- It is the same questions each time: 13 of 47 were model-answered in all six runs, 19 in none, 15 sometimes. Never accepted: scope and robustness (0 of 12 each), psychoacoustics 2 of 24, synthesis 2 of 12, diagnosis 4 of 12. Mostly accepted: ableton_advanced 18 of 24, recording 19 of 30, space_and_width 9 of 12.
- Zero unsupported measurements and zero fabricated sources in every run; one forbidden-name hit each in runs 4 and 6. Mean keyword recall 0.61 to 0.67.
- Memory: swap rose from 1.6 GB to 2.0 GB across the day; free memory 21% to 26%.

## Draft prompt probe (15:08 to 15:19, worktree code, hybrid retrieval, same settings)

| | Run 4 (main code) | Draft prompt |
| --- | ---: | ---: |
| Model answers / 47 | 23 | 21 |
| Accepted / attempted | 23 / 46 (50%) | 21 / 46 (46%) |
| p50 / max, all 47 | 10.1 / 12.2 s | 12.1 / 16.2 s |
| Model answers inside 15 s | 23 of 23 | 19 of 21 |
| Ended mid-sentence (last-character check) | 21 of 23 | 18 of 21 |
| Mean words in a model answer | 83 | 81 |
| Unsupported measurements delivered / fabricated sources | 0 / 0 | 0 / 0 |
| Mean keyword recall | 0.65 | 0.62 |

Rejections in the draft window (route log, 41 logged): 9 unsupported measurements (run 4: 12), 5 insufficient evidence overlap (3), 5 no answer (2), 1 attributes a measurement to an excerpt, 21 accepted.

- Unsupported measurements fell from 12 to 9 and "no answer" rose from 2 to 5; with one pass each that is inside the run-to-run spread we saw in the soak (41% to 48% acceptance), so it shows nothing.
- The length rule did not shorten answers (81 words against 83) and 18 of 21 still end mid-sentence, so the cut-off problem is not fixed by asking the model to be brief.
- The gate is still failed on acceptance (46% against 70%). The drafts stay on the draft branch, unmerged.

## After the soak (Jack: "do this all after the soak")

- [x] Analyse the six soak runs (results in the section below).
- [x] Run the 47 questions once on the draft prompt (worktree) and compare with run 4 (results below).
- [x] Local fast-forward merge of `fix/review-critical-2026-10-02` into main, no push: main is now 372df8f1 (GIT_NOTES.md committed first). origin/main is still ce8e2a49.
- [ ] **Stopped, not pushed.** Split 6c031560 is clean (descends from 9b9ccc9c, tree equals main:products/kenn, no AI trailers, no secrets) but `ci_verification.sh` on a fresh worktree fails: 7 backend tests fail there and pass in the main tree (338 passed), the same missing-ignored-data cause as the draft worktree, and step 4 points at `chat/tests`, which no longer exists in the tree (it moved to `packages/chat`). Waiting on Jack. kenn-app sync from main: subtree split, ancestor check, secrets/trailer scan, `ci_verification.sh` on a fresh worktree, tree-hash compare. Jack said yes to pushing the latest to kenn-app for the collaborator group, so push (fast-forward only, never forced) once every check is clean; stop and report if any check fails. kenn-app main is at the 30 Sept commit 9b9ccc9c, 428 files behind.

## Cleanup

- [ ] Stop caffeinate PID 61077 (ends itself about 16:27), companion PID 57233, soak driver PID 61079 if still alive.
- [ ] Remove temp state dirs in /tmp.

## Waiting on Jack

- [ ] Review the uncommitted receipt, KENN_PLAN.md note and worktree drafts; show the diff before any commit.
- [ ] MLX / speculative decoding stay parked until Jack says go.

## Known, not ours

- `test_streamed_generation_prefix_guard.py` has 4 failures in the worktree but passes in the main tree. They fail the same with all three of today's diffs reverted, so they are not from these changes; cause not yet found (probably something the worktree lacks that the main tree has).

## kenn-app sync, second attempt (4 Oct, after the CI fixes)

- Fixed in c9b04818 (local, not pushed): the four prefix-guard failures were the template being built from real retrieval while the stream used fixtures (now both use the fixtures); three tests that read the real corpus now skip without it; step 4 of `ci_verification.sh` points at `packages/chat/tests`. Step 3 now passes on a fresh checkout (4092 passed, 130 skipped).
- Correction: my earlier "descends from 9b9ccc9c" was wrong; the ancestor line never printed. The subtree split shares no history with kenn-app/main (different roots, 665 vs 371 commits). The content matches, though: split commit f9eb82a9 has exactly kenn-app/main's tree. So a plain fast-forward of the split is impossible without a force push.
- `packages/chat/tests`, now actually run by step 4, has 2 failures in the main tree (full evaluation receipt, chat coverage receipt) and 8 on a fresh checkout (the other 6 need the corpus). Never run before because the old path did not exist.
- Nothing pushed to kenn-app or origin.

## Tokenizer A/B on the hybrid path (4 Oct, in memory only, no index written)

The 175 technique and device-purpose retrieval cases, source in the top 4 / top 8, using the real hybrid search with the embedding index. Script: `tokfix_ab2.py` in the scratchpad.

| Variant | Hybrid top 4 | Hybrid top 8 | BM25 top 4 / top 8 |
| --- | ---: | ---: | ---: |
| Today | 128 | 137 | 98 / 112 |
| Strip trailing full stops | 131 | 143 | 103 / 121 |
| Strip + light stemming | 131 | 141 | 108 / 133 |

- Stripping the trailing full stop is a small, safe gain on the path the app uses (+3 top 4, +6 top 8). Stemming helps BM25 a lot but adds almost nothing once the embeddings are in, so it is not worth the risk on its own.
- Neither gets acceptance from 46% to 70%: retrieval finds the right notes most of the time already. The gate loses its answers to the model's invented numbers (9 to 12 of about 41 attempts), cut-offs and "no answer".
