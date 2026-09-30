# KENN: advance the North Star plan, and make the GLM loop honest

**Reference document:** `products/kenn/docs/plans/KENN_NORTH_STAR_2026-09-24.md`
**Active progress log:** `monorepo/KENN_PROGRESS.md`
**Operating style:** plain, careful human engineering. No filler, no boilerplate, no AI attribution trailers in
commits (`AGENTS.md`).
**Invariants:**
1. **Live is Jack's.** `FakeLiveBackend`, mocks, offline fixtures. No real Live unless an owner-scheduled soak.
2. **GPU rule:** GPUs 0 and 1 only for KENN. GPUs 2–7 are multi-tenant and off-limits.
3. **Safety model:** the model never writes to Live. proposal → Apply → OSC write → readback → receipt → undo.
4. **The GLM loop is the product:** observe → reason → propose → confirm → act → verify → learn. A step that cannot be
   verified is not done. A step that cannot be undone did not happen. If the loop cannot be honoured, say so and stop.

---

## What this round is for

The plan is 40 ticks deep and the numbers in it are mostly good. The problem now is that **the plan's own record has
drifted from the code**, and one retrieval regression is sitting in the live index where nobody can see it. Both
contradict the plan's own rule: *"Quality is measured, not assumed."*

So this round does not open a new stage. It makes the measurements true again, fixes the two live correctness items
Stage 3b still lists as open, and finishes the in-flight device work that is currently uncommitted.

## Measured state as of this morning (re-run these, don't trust the numbers below)

| Check | Command | Result |
|---|---|---|
| Backend suite | `pytest -q` in `apps/backend` | **2,285 passed, 5 skipped, 0 failed** (213 s) |
| Retrieval, original fixture | `evaluate_retrieval_modes.py` | bm25 0.9655 / hybrid **0.9828** (index `v-07328d9baf04`) |
| Retrieval, describe-it 125 | `--cases src/kenn/evals/device_purpose_retrieval_cases.json` | bm25 0.600 / hybrid **0.7680** |
| Retrieval, technique 50 | `--cases src/kenn/evals/technique_purpose_retrieval_cases.json` | bm25 0.660 / hybrid **0.8600** |
| Retrieval, sealed Qwen8b | `--cases src/kenn/evals/device_purpose_sealed_qwen8b.json` | bm25 0.2133 / hybrid **0.3422** (225 cases scored of 228) |
| Chat coverage | `eval_chat_coverage.py` | applicable **81/84**, abstention **43/44** = **124/128** |
| Route latency | `route_latency_report.py` | 1,053 requests, **no route over the 4 s p95 target** |
| Manual grounding | `evaluate_ableton_manual_grounding.py` | `manual_not_indexed`, 0 `official_ableton_manual` chunks |
| Device coverage | uncommitted map, 78 devices | 10 insertable, 22 qualified parameters, 1 device with no note (Drum Synth) |

Two things to note before you start. The plan's chat coverage correction (line 223) is **confirmed**: 124/128, not
125/128 — 81/84 applicable plus 43/44 abstention. And the plan's "sealed Qwen8b 0.425" (line 251) does **not**
reproduce: today it is 0.3422, which is the plan's *pre-`v1`* number. Read Task 2 before you touch that.

---

## Task 1 — The live index is missing 33 Ableton 12 notes

**This is the most important thing in this prompt.** Found while verifying the plan's retrieval claims.

`data/index/CURRENT` is `v-07328d9baf04` (3,206 chunks, 749 sources). `data/index/PREVIOUS` is `v-4fd17ceb264f`
(3,338 chunks, 782 sources). The 33-note difference is not a rollback artefact — every one of the 33 notes is
`Status: Draft` on disk, and `build_index.py:215` (`status in {"", "approved", "unmarked"}`) correctly skips drafts.

So KENN is running on 3,206 curated notes and has 33 more sitting unapproved. The plan's Stage 2 line at 3,176
curated / 3,308 total is describing the **previous** version, not what is live.

What to do, in this order:

1. **Read all 33 drafts and decide.** They are `ableton12-*` notes demoted from Approved, with the reason recorded in
   their `Reviewed:` line (for example `ableton12-mixing-manual-pt3.md`: *"fixed return and main levels as rules, and
   the crossfader doesn't blend returns with the main track"*). That is a real correctness demotion and should stay
   demoted unless the note was fixed. **Do not blanket-approve.** For each one: fix the wording if the problem is
   small, or leave it Draft and say why in the plan.
2. **Fix the crossfader claim wherever it still appears.** The demotion reason says the crossfader does not blend
   returns with the main track. If any approved note, any recipe, or any advice generator still says it does, that
   is a wrong answer in front of a producer. Grep for it and check.
3. **Rebuild and re-measure.** `python main.py build` from `apps/backend`, then re-run all three retrieval fixtures
   and `eval_chat_coverage.py`. Record the before/after in the plan. If recall drops, that is the correct outcome for
   a smaller, more accurate index — say so rather than re-approving notes to make a number go up.
4. **Make the drift impossible to repeat.** The reason this was invisible is that nothing compares
   `chunk_count`/`source_manifest` in the active manifest against the notes on disk. Add a check to the retrieval
   qualification path (`assemble_intelligence_qualification.py` or a sibling) that reports approved-note count on
   disk versus chunks in the active index, and fails when they disagree by more than the expected draft/unreviewed
   set. A test that reproduces the drift.

Do not promote the index by hand. It goes through the normal build and the candidate evaluation.

## Task 2 — Re-measure the retrieval gate and correct the plan's numbers

The plan's Stage 2 gate needs recall@4 ≥ 0.95. Today's truth is **0.9828 / 0.768 / 0.860 / 0.342**. The gate is met on
the original fixture and missed by a wide margin on producer-worded questions.

The plan's line 251 says *"sealed Qwen8b set 0.425 (was 0.346, +7.9pp)"* for the `v1` "Use it when" lines. That 0.425
was measured **in a throwaway in-memory index** — the review doc says so twice (*"measured in memory (the index is
untouched)"*). The live index has 1 chunk containing "use it when" out of 3,206. So the gain is real but **unshipped**,
and the plan quotes it as if it were live. Fix that wording wherever it appears, and state the live number separately
from the candidate number.

Also worth recording: `evaluate_retrieval_modes.py` silently drops 3 of the 228 sealed cases (017, 100, 209) because
`_expects_public_abstention` filters them out. That is defensible — they are abstention cases, not retrieval cases —
but the denominator silently changes from 228 to 225 with nothing in the output saying so. Print the dropped count.

**The lever is note wording, not a bigger model.** Both bake-offs say this and the evidence is in the plan: bge-base
topped out at 0.81, bge-reranker-base at 0.808, and the right note is in the top 20 for only 87.2% of describe-it
questions. The gap is that notes describe devices technically and producers describe goals. The 114 "Use it when"
lines exist and are measured; they are waiting on Jack's ticks in
`docs/reviews/KENN_USE_IT_WHEN_REVIEW_2026-09-25.md`. Leave the ticks to him. What you can do is measure honestly and
say clearly what is blocked on him.

## Task 3 — Close the two Stage 3b items still marked open

### 3a. `_clean_chunk_for_synthesis` truncates into a broken tag

Plan line 421. **Reproduced this morning.** Two distinct defects in
`apps/backend/src/kenn/llm/llm_rewrite.py`:

- **Mid-word cut** (`_clean_chunk_for_synthesis`, line 528-534). A 240-char cap on a long note returns
  `'...across a sixty decibel s...'` — the word is severed and the ellipsis glued to a fragment. It also collapses a
  fenced code block into one line: `'\`\`\`python KENN_LLM_CONTEXT_CHARS=650 \`\`\` Some prose...'`, which changes the
  meaning of the source text KENN is about to reason over.
- **Truncation lands inside the opening tag** (`build_raw_context_block`, line 561). The `block[:remaining]` cut is
  applied to the *whole* block including `<source_excerpt label="..." relevance="9.4">`, then a closing
  `</source_excerpt>` is appended. With a realistic-length label and `max_chars=260` the model receives:

  ```
  <source_excerpt label="Ableton Live 12 Reference Manual — Mixing Dynamics chapter (curated note, section Dry/Wet para
  </source_excerpt>
  ```

  An unterminated attribute, and the label can be cut in half mid-word. This is the same class of bug the 28 Sept
  audit found in the answer path: **the model is being shown malformed, boundary-crossing source text, and the
  excerpt boundary is the thing that tells it where untrusted evidence stops.** Cut on a word boundary, never inside
  the opening tag, and drop or truncate a fence safely rather than splicing it. Tests for all three, named for the
  behaviour.

### 3b. One preference per key, and no way back

Plan line 412. `record_preference` (`core/assistant_profile_memory.py:159`) deactivates every other row for that key,
and `GET /api/memory` (`routes/chat_routes.py:82`) only returns active rows. So a producer who says *"actually, I
master to -9, not -12"* loses the old value with no way to see it, compare it, or put it back. That directly
contradicts the Stage 4 gate: *"testers can find and delete any memory."*

Add a history read (inactive rows for a session, newest first) and a restore path that reactivates a chosen
`preference_id` and deactivates the current one, so restoring is a move, not a second row. Expose both through the
existing `/api/memory` surface. Test: record A, record B, list both, restore A, confirm B is inactive and A is
active. Note the retention `DELETE` at line 171 keeps the newest `MAX_PREFERENCES` inactive rows per session — the
restore path has to work inside that window, so check the bound is not silently eating the history it needs.

## Task 4 — Finish and land the in-flight device work

There is uncommitted work on `main` right now. It is good work and the suite is green, but it is not landed, and the
plan does not mention it. It is Stage 3's "device qualification factory" and Stage 2's "parameter-level knowledge"
moving in the right direction.

- `core/stock_devices.py` (new) — the 78 Live 12 Suite devices by exact browser name, with the honest-reply path so
  *"add wavetable to synth"* says KENN can't add it yet instead of pretending it does not exist. That directly
  addresses the 2026-09-05 finding that AbletonOSC's browser search resolves "Reverb" to Convolution Reverb.
- `core/device_units.py` — Dry/Wet profiles for Saturator, Drum Buss, Auto Filter, Glue Compressor, Compressor;
  `_canonical_parameter` folds Echo's "Dry Wet" and the sixteen EQ Eight band names onto one profile each.
- `core/live_intent.py` — band-qualified EQ resolution (`"1 Frequency A"` used to collapse to bare "frequency" and
  miss all 16 band controls; `"2 Q A"` once read as Adaptive Q, a real wrong-control write), and pronoun inheritance
  across `then` steps in a recipe.
- `core/live_command.py` — Utility's level trim is Output, not Gain; the planner prompt and `validate_llm_plan`
  now agree on the widened Dry/Wet setup set and still refuse Limiter.
- `test_full_stock_device_control.py` (new, 318 lines) and the coverage map.

**While you are in there, one thing the map exposes.** `DEVICE_INSERTION_ALLOWLIST` has 10 devices and
`CANDIDATE_DEVICE_INSERTION_ALLOWLIST` is an empty `frozenset()` with a comment saying the candidate set *"is
currently empty"* — but the map lists 68 devices that cannot be inserted. The comment is accurate about the set and
misleading about the situation. The real blocker is stated in the comment above it: a name may only move into the
allowlist after a real-Live reversible parameter qualification, and Live belongs to Jack. **Do not move a name into
the allowlist without that evidence.** What you can do is make the gap measurable: a script that takes the map and
emits the shortest ordered list of devices whose qualification would add the most, with the exact
`qualify_ableton_live_device.py` invocation per device, so Jack can run one supervised session and land many
devices at once. `measure_device_parameters.py` (read-only, every parameter of one device) and
`qualify_device_profiles.py` (write, read Live's display back, restore exactly) are both ready.

The 2026-09-21 unit probe found `Utility | Gain` had zero usable points and the real control is `Output`. That probe
is the template for the batch: `docs/research/results/qual-glm-2026-09-21-raw/unit-probe2.json` has 21-point
threshold tables. Utility Output has no profile at all — 20 profiles cover 10 devices out of 78.

## Task 5 — The manual pathway, and the decision that is not yours

Every official-manual path in the product is dead and has been for the whole life of the plan:
`evaluate_ableton_manual_grounding.py` returns `manual_not_indexed` with `official_manual_chunk_count: 0`, so
`manual_grounding_evaluation` can never pass, `retrieval_index_shadow` filters on a class that does not exist, and
`session_intelligence.py:554`'s "Grounded in the authorized Ableton manual" is unreachable. The Knowledge programme
ranks the manual above curated notes, so this is the one content gap that contradicts the plan's own trust table.

The code is done and tested. `download_training_pdfs.py` is real, the Live 11 catalog entry is `local_opt_in` with a
verified CDN URL, and `python main.py build --include-local-manuals` is the path. **What is missing is a licensed PDF
in a gitignored directory, and that is Jack's to place.** Live 12's manual is not in the installed app bundle — only
the third-party EULA is — so it comes from Live's Help menu.

Do not go looking for a copy, do not download one, and do not change a catalog entry to make the class appear. Write
the exact command sequence into the plan so the moment he drops the PDF in, this is a five-minute job. Make sure
`evaluate_ableton_manual_grounding.py --require-manual` (exit 2 today) is wired into whatever gates a promotion —
right now nothing runs it, so an index with no manual promotes cleanly.

Then re-measure the describe-it set with the manual in it. It is the one source that speaks the producer's language
rather than the engineer's, and 0.768 on describe-it against 0.983 on device-named questions is exactly the gap a
manual would close.

## Task 6 — Housekeeping, and the tick discipline

1. **Tick the North Star boxes in the same commit as the work**, with the date and the measured evidence. Where a
   number in the plan is wrong, correct it in place and say what you measured instead — the plan is a record, and a
   record that has drifted from the tooling is worse than no record.
2. **Record the in-flight device work in the plan.** It is not there. Stage 3's device qualification factory and
   Stage 2's parameter knowledge both moved and neither says so.
3. **Add a "measured on" line to every number in the plan** that can be re-derived from a script. Most already are;
   the ones that are not (the sealed 0.425, the chat 125/128) are exactly the ones that went stale.
4. Update `KENN_PROGRESS.md`. It is at 2026-09-28 and the plan is at 2026-09-29; both are behind `main`.
5. Single-line plain commit message, no AI attribution trailers. Never commit hostnames, IPs, credentials, licensed
   manuals, or private audio.

## What is blocked on Jack, and should not be started

Say these are blocked; do not work around them.

- **Sign-off on the direction** (plan line 527) and the three open decisions (530, 531, 534).
- **The "Use it when" ticks** — 114 drafted lines, measured, waiting on his review.
- **The phrasing labels** in `tooling/data/natural_holdout_candidates.jsonl`, especially rows with a `note`. The
  Stage 1 gate counts owner-checked labels.
- **Two reviewers** for the human-review packet, and the **real-mix listening set**. Both Stage 1 and Stage 3 gates
  need them; no amount of engineering closes that.
- **Any real-Live device qualification.** Prepare the batch, then wait for a scheduled session.
- **Code signing**, deferred to just before shipping with the Developer ID.

## The one-line test for whether this round worked

Someone reading the plan can re-run the commands in the table at the top of this prompt, get the numbers the plan
claims, and find nothing surprising.
