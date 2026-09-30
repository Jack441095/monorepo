# KENN engineering plan: the four weeks after the 30 Sept soak

**Written:** 2026-09-30 · **Owner:** Jack · **Status:** proposal for owner sign-off

The North Star (`KENN_NORTH_STAR_2026-09-24.md`) decides the direction and the gates. The mega plan
(`KENN_MEGA_PLAN_2026-09-29.md`) sets the order across its workstreams (WS1–WS10). This plan takes the next four weeks
of both and says what gets built, in what order, by whom, and which North Star item or gate each piece serves. Where
they disagree the North Star wins. As it asks, tick items there in the same commit as the work, with the date and the
evidence.

Sizes: **S** is up to half a day, **M** one to two days, **L** three to five. "Live night" means a batched session on
Jack's Mac with Live open on a set he has prepared; nothing else touches real Live (Jack needs it for work).

## 1. Where we are, against the North Star's own table

| North Star capability | 24 Sept (North Star) | 30 Sept | Next gate |
|---|---|---|---|
| Understands open phrasing | Rules 80/124; planner in shadow | Rules 1,647 of 1,751 labelled phrasings (94%), but **fresh wording starts near 40%** (below); planner still in shadow, holds until real tester data | ≥ 95% on ≥ 500 natural phrasings (Stage 1) |
| Converses | Template answers; model off for chat | Instant template first; the 8B model's answer takes 7–16 s on the M3 and was used 1 time in 6 | Model-written, cited answers land in ≤ 15 s on ≥ 70% (Stage 1 open item) |
| Knows Live | 74/78 devices, recall@4 0.966 | 77/78 device notes; recall@4 0.98 when the topic is named, **0.752** for "what I want" wording, technique **0.840**, sealed set **0.3333**; **the index has 1,436 `official_ableton_manual` chunks** (see C1) | recall@4 ≥ 0.95 on ≥ 300 questions (Stage 2) |

> **Retrieval numbers re-measured 30 Sept on the live index, because the manual landed and moved it.** Index is now
> **`v-db8c6334cf63`, 4,642 chunks** (3,176 curated + 1,436 official-manual + 28 transcript + 2 reference), not the
> `v-07328d9baf04` / 3,206 chunks these figures were taken on. `evaluate_retrieval_modes.py`, cutoff 4, verified here
> and independently by the C2 branch:
>
> | Fixture | cases | BM25 r@4 | hybrid r@4 | plan said |
> |---|---|---|---|---|
> | describe-it | 125 | 0.600 | **0.752** | 0.74 / 0.768 |
> | technique-purpose | 50 | 0.640 | **0.840** | 0.86 |
> | sealed Qwen8b | **225 scored of 228** | 0.200 | **0.3333** | 0.34–0.45 |
>
> **The prediction that failed.** The NEXT_PROMPT argued the manual "is the one source that speaks the producer's
> language rather than the engineer's, and 0.768 on describe-it against 0.983 on device-named questions is exactly the
> gap a manual would close." The manual is now indexed and **describe-it went 0.768 → 0.752, slightly down**. 1,436
> manual chunks did not move producer-worded recall. So the lever is still note wording — the "Use it when…" lines and
> C4, which are waiting on Jack's ticks — and not more source material. Anyone tempted to add a source to fix recall
> should read this line first.
>
> The sealed denominator is **225 of 228**, not 228: `_expects_public_abstention` drops cases 017, 100 and 209 on
> substring matches ("**mic**" in "What setup should I use?", "**Wwise**"), and all three are genuine retrieval
> questions. `evaluate_retrieval_modes.py` now prints each dropped case and why (C2).
| Controls Live | Mixer, focus, sends, 12 parameters on 9 devices | 14 measured profiles on 8 devices; **built but never run on real Live:** tempo, time signature, return level/pan/mute, scenes by name, the device factory, choosers and switches | ≥ 60 parameters on ≥ 25 devices, all undoable (Stage 3) |
| Thinks in steps | Deliberative planner qualified once | 15 recipes built, **0 run on real Live** | Recipes pass on real Live with exact undo, ≤ 3 s a step (Stage 3) |
| Listens | Rendered captures only | Unchanged | Live capture, masking (Stages 2/3 later) |
| Remembers | Receipts only | Project memory and preferences built (Stage 4 ticked); one preference per key still survives (Stage 3b open) | Visible, editable, deletable |
| Creates | MIDI ideas as clips | Unchanged (Stage 5: 2 done, 8 open) | Owner listening review |
| Integrity (Stage 3b) | 8 defects found 28 Sept | 23 items done, **3 open** | Closed before a second tester runs |
| Ship | — | No Developer ID; 0 testers; release gate needs soak receipts (today) | Qualified gate, 3 testers (Stage 0 exit) |

Open North Star items by stage today: Stage 1 has 2, Stage 2 has 4, Stage 3 has 2, Stage 3b has 3, Stage 5 has 8.

**What the understanding numbers say.** Today's three blind rounds (fresh phrasing sets written before the parser was
read): phone shorthand started at 42% right and reached 97%; long rambling chat messages started at 38% and reached
78%; chat wording started at 32% and reached 93%. The "after" numbers are no longer blind. Each new way of typing costs
about a day of rule fixes to reach the 80s–90s, so the rule set alone will not get us to ≥ 95% on wording we haven't
seen. The process has to change, not just the rules (Track B).

## 2. Three bets for these four weeks

1. **Verify before adding.** Most of what was built this month has never run on real Live. Until wave 1 of the device
   factory and the 15 recipes are qualified, no new control family starts (North Star principle 1: deterministic code
   owns the dangerous parts, and "promotion by evidence", principle 4).
2. **Learn from wording we haven't seen.** One blind round a week in a new register, scored once, first-run number
   reported, and a second author so it isn't only us. Real tester wording becomes the main source of fixes (Stage 1,
   model programme).
3. **Retrieval before more notes.** Recall on "what I want" wording (0.74) and on the sealed set (0.34–0.45) is the
   weakest measurable link (Stage 2). Fix the ranking and get the manual in before writing more prose.

## 3. The four weeks at a glance

| Week | Live night | Build (no Live) | Exit |
|---|---|---|---|
| **0** (30 Sept–1 Oct) | Tonight: 1-hour soak, tempo/time-signature/return rows | Release, tag, DMG, `kenn-app` sync; F1 sync script; C1 manual ingest; blind round 9 | Qualified gate; release tagged |
| **1** (1–7 Oct) | Night 1 (~2 h): device factory wave 1 | A2 device-zoo set checklist; B2 policy calls; B3 holdout review starts; C2 fixture; C4 lines; D1 Mac timing; F2 measures report; F3 path gate | ≥ 12 devices swept, ≥ 40 parameters qualified |
| **2** (8–14 Oct) | Night 2 (~1 h): the 15 recipes | C3 reranker measure; C5 parameter reference; B4 wording triage; B5 multi-turn; D2 prompt cut; A8 clean-account test | 15/15 recipes with exact undo |
| **3** (15–21 Oct) | Night 3 (~1.5 h): wave 2 devices and first new family | G1–G2 new families; D3 model options; C6 craft notes start; B6 two-changes chips; E3 rollback | Next 13 devices; first new family qualified |
| **4** (22–28 Oct) | Night 4 (1 h): release soak for the four-week build | Gate report against every number in section 7; blind round; decide the next phase | Phase-1 exit reported, good and bad |

## 4. Tracks

Each task names the North Star item or gate it serves and what it needs beyond a laptop.

### Track A: verify on real Live
Serves: Stage 3 "device qualification factory" and its gate (recipes pass on real Live, exact undo, ≤ 3 s a step,
0 unauthorised writes); Stage 0 exit; the Controls Live row.

| ID | Task | Size | Needs |
|---|---|---|---|
| A1 | Tonight: soak and real-Live rows; commit receipts, tag `kenn-beta-2026-09-30`, build the DMG, sync `kenn-app` | S | Live night 0 |
| A2 | Device-zoo set: a checklist (one track per wave-1 device, named as the scripts expect) and a preparation script, dry-run on the fake backend | S | **Done 30 Sept** on branch `kenn-device-zoo-wave1`; reaches `main` with the next release |
| A3 | Wave 1: `measure_all_devices.py`, then `build_device_profiles.py`, then `qualify_device_candidates.py` for EQ Eight, Compressor, Utility, Limiter, Reverb, Hybrid Reverb, Delay, Echo, Saturator, Auto Filter, Glue Compressor, Multiband Dynamics. Follow `docs/runbooks/KENN_DEVICE_FACTORY.md`; the qualifier writes each value, reads it back and restores it | M | Live night 1 |
| A4 | Sign-off queue: Jack reviews each batch's candidate profiles (units, ranges, display strings) before they load | S per batch | Jack |
| A5 | The 15 recipes on real Live, each with exact undo and per-step latency recorded | M | Live night 2 |
| A6 | Return-track rename (the bridge already has the endpoint) and solo (needs a small Remote Script addition), scenes by name; add walkthrough rows | S | Live night 3 |
| A7 | Wave 2: the next 13 devices | M | Live night 3 |
| A8 | Clean-account test: install the DMG on a fresh macOS user, first successful command in under 15 minutes | M | Jack creates the test user |

> **A2, 30 Sept** (branch `kenn-device-zoo-wave1`): `docs/runbooks/KENN_DEVICE_ZOO_WAVE1.md` is the checklist and
> `tooling/scripts/prep_device_zoo.py` the preparation script. It checks all twelve names against the exact browser
> names in `core/stock_devices.py`, prints which ones have to be dragged in by hand, and rehearses the measure, the
> candidate build and the unapplied qualifier against `FakeLiveBackend` on a new `device_zoo_wave1.json` fixture:
> **12 of 12 devices measured, 35 candidate profiles, 17 choosers, 1 unmapped** (EQ Eight's Q, which Live shows as a
> bare `1.00` with no unit). 14 tests in `test_device_zoo_wave1_prep.py`; `ci_verification.sh` green on the branch
> (backend 2,451 passed / 125 skipped, chat 38, Mix Review 66, AutoMix 4 + 4). Two things came out of it:
> **four of the twelve cannot be inserted by KENN** (Utility, Limiter, Reverb, Delay — two because AbletonOSC's browser
> search resolved "Reverb" to Convolution Reverb and "Delay" to Align Delay), so that part of the set is a hand drag;
> and `pick_raw_values` walked an all-positive dB control down to 0 dB and collapsed its three test points onto one
> value, so **Saturator's Base and Multiband Dynamics' Range could never have qualified at all** — fixed, with the
> clamp still holding for controls that do go below 0 dB. Unrelated and pre-existing: `test_mlx_inference.py::
> test_mlx_inference_latency_and_output` fails on `main` too, so MLX inference is not currently covered by the suite.

**Gate (week 4):** ≥ 12 devices and ≥ 40 parameters qualified (North Star end state: ≥ 25 and ≥ 60); 15/15 recipes with
exact undo; 0 unauthorised writes.

### Track B: understanding
Serves: Stage 1 gate (≥ 95% on ≥ 500 natural phrasings, human-review packet passes); the model programme (sealed sets,
promotion only through the gate).

| ID | Task | Size | Needs |
|---|---|---|---|
| B1 | One blind round a week, a different register each time (voice, beginner, second-language, other-DAW, long message, phone), plus one written by a person who did not write the parser fixes. Score once, report the first-run number, then fix | S weekly | Colleague or Jack writes |

> **B1, round 9** (branch `kenn-blind-round-9`; register **mix notes**, uppercase targets and labels instead of verbs):
> **74 / 118 right (62.7%), 40 asked, 4 wrong** on the first run, scored once before any rule change. After
> correcting three labels: **77 / 118, 38 asked, 3 wrong**. First-run accuracy across registers now reads 42% → 38% →
> 32% → 69.2% → **62.7%**. Write-up in
> `docs/evidence/KENN_BLIND_PHRASINGS_ROUND9_MIXNOTES_2026-09-30.md`.
> **One of the four wrong plans was a real silent wrong write, and it is fixed.** "Lead Vocal off solo" soloed the
> vocal: every negation pattern in `live_intent.py` required a verb, so a bare mix-note negation fell through to the
> positive branch. It read back clean and was journalled as verified, which is the worst class of bug in that file.
> "no solo", "solo off" and "off mute" failed the same way. Fixed on `kenn-solo-negation` with 14 tests; the
> curated holdout re-scores **492/505 both with and without the change**, so it costs no phrasings.
> Two of the other three were bad labels, not bad answers: bare "Delay" is a pinned policy conflict (Deliberately
> not insertable because the browser search resolved it to Align Delay), and the three-change list is documented
> working behaviour that the round measured one layer too high. The fourth, "set the vocal compressor knee to 3 dB",
> is **unresolved and is the owner's call**: there is no qualified Knee profile on any of the 9 measured devices, and
> the question is whether that refusal belongs at parse time or at write time.
> **The second author was this session, not a person who had not written the parser fixes**, which is weaker evidence
> for register-independence than the plan intends; the evidence doc says so rather than burying it. Seven cases are
> held unscored in `natural_blind_round9_mixnotes_pending_owner_2026-09-30.jsonl` because they are the pinned policy
> conflicts that are the owner's to rule on. **B1 stays open**: the plan asks for one round a week, so round 10 wants
> a human author picking the register.


| B2 | Settle the three pinned policy conflicts (bare "X to -N", "kill playback", "reverb on the vocal": device or send) and encode each with tests | S | Jack decides |
| B3 | Grow the curated holdout from 24 toward 500: review the 481 drafted candidates; two people check each label; the sealed sets stay out of training | M plus review time | Jack and colleague |
| B4 | Real-wording loop: verify the opt-in "requests KENN didn't understand" log in the installed app, then a weekly triage script that clusters the misses and proposes rule fixes | M | **Script done 30 Sept** on branch `kenn-wording-triage`; the real log needs testers (E2) |

> **B4, 30 Sept** (branch `kenn-wording-triage`): the log the plan calls "not yet verified" **does exist** — it is
> `core/asked_log.py`, writing `kenn/data/asked_log.jsonl` on every ask or refusal, with `setup_page.html:56` carrying
> the opt-in wording. The catch: the opt-in is on the way **out**, not in — rows are written automatically and the
> checkbox only decides whether they ride along in a diagnostics file. `triage_unparsed_requests.py` clusters on
> `(signal, action)` plus a track-substitution probe that makes `needs_track` a real claim, ranks by size, and proposes
> rule fixes as text for a human — it never edits the parser. It reconciles against the scorer's own counts rather
> than duplicating scoring. 21 tests. Two things it surfaced that are worth more than the script: the top cluster
> (`no_action/taste`, 8 rows, "make the drums slap") has **no measurable target**, so the honest proposal is a recipe
> or a question, not a regex; and `add 2 dB to the reverb return` reports `insert_device` when it should be a send.

| B5 | Multi-turn: "the other one" after KENN listed two matching tracks; corrections on device parameters; wrong-plan tests first | M | |
| B6 | Two changes in one sentence and "adjust that": answer with buttons ("Do the first, then the second?") instead of a refusal | M | Frontend |
| B7 | Planner: stays in shadow. Retrain (run 14) only when about 500 owner-labelled tester requests exist, and promote only through `live_llm_promotion.py` | hold | Tester data |

**Gate (week 4):** first-run ≥ 85% on a round of real wording (mega plan Phase 2 exit), 0 wrong plans; curated
holdout ≥ 200 reviewed. With no testers yet, B4's log has only our own use; the second author in B1 stands in.

### Track C: knowledge and retrieval
Serves: Stage 2 (parameter-level knowledge, craft notes, source tiers, the recall gate) and the Knowledge programme's
trust table (manual and Live measurements above notes above general advice).

| ID | Task | Size | Needs |
|---|---|---|---|
| C1 | Ingest the Live manual locally: `download_training_pdfs.py` for Live 11, export Live 12 from Live's Help menu, rebuild with `--include-local-manuals`, qualify with `evaluate_ableton_manual_grounding.py`. PDFs stay in the git-ignored `Training_Data_PDF/`. Moves the index from 0 official-manual chunks and brings the "grounded in the authorized manual" path to life | S | **Already done before this row was written** — re-measured 30 Sept, see below |

> **C1, re-measured 30 Sept: this is already done, and four plan records saying otherwise are stale.** Measured on
> the live index with `evaluate_ableton_manual_grounding.py`: **`official_manual_chunk_count: 1436`**, not 0.
> `all_cases_passed: true`, **16 / 16** reference cases, every one selecting evidence class
> `official_ableton_manual`, `status: evaluated`. `--require-manual` exits **0**, not the 2 this plan and the North
> Star both record. Counted straight from the index: 4,642 chunks = 3,176 `curated_kenn_note` + **1,436
> `official_ableton_manual`** + 28 `youtube_transcript` + 2 `reference_document`, all 1,436 from
> `Training_Data_PDF/live11-manual-en.pdf` (96,881,315 bytes, file dated 30 Sept 01:09). That PDF is git-ignored
> (`.gitignore:101`), so no licensed manual is tracked — the hygiene half of C1 holds.
> **So the claims "the manual is not in the index at all", "0 `official_ableton_manual` chunks", "the whole
> official-manual pathway is dead", "`session_intelligence.py:554`'s 'Grounded in the authorized Ableton manual' is
> unreachable" and "`manual_grounding_evaluation` can never pass" are all wrong as of 30 Sept.** Those appear in the
> North Star's Stage 2 note, the Stage 3b open list, the NEXT_PROMPT's Task 5, and this row.
> **Two things the owner needs to know, neither a blocker.** The ingest ran at 01:09 on 30 Sept — during the night-0
> soak work — while this row still said the work was blocked on his sign-off, so **the North Star's "Ingest the Ableton
> Live Reference Manual now?" decision box is unticked while the work behind it exists**; the decision now is whether
> to keep it. And **the manual indexed is Live 11's**, while he runs **Live 12 Suite**: the Knowledge programme ranks
> the manual *above* curated notes, so KENN will now cite Live 11 documentation for a Live 12 product. Exporting the
> Live 12 manual from Live's Help menu and rebuilding is the fix, and it is the same `build --include-local-manuals`
> path once the PDF is in place. Live 11's PDF is also present in `Training_Data_PDF/` and would not need re-fetching.
> This also resolves a C2 caveat: the index these numbers come from, `v-db8c6334cf63`, **is** the live index.
| C2 | Retrieval fixture to ≥ 300 questions with a **sealed half** nobody tunes on; baseline with `evaluate_retrieval_modes.py` | M | **Built 30 Sept** on branch `kenn-sealed-fixture`; fixture awaiting Jack's review |

> **C2, 30 Sept** (branch `kenn-sealed-fixture`): the **228-case sealed Qwen8b set was not split — it is burned.**
> The North Star records it being scored four times to choose between wordings (0.338 / 0.417 / 0.386 / 0.447), so a
> half of it would be development data too. Instead a **new 150-case sealed holdout** over 75 notes, marked
> `"sealed": true` with a policy block. The marker is read from the file's **contents**, not its name, so renaming
> cannot unseal it; `tooling/scripts/sealed_fixtures.py::tunable_cases()` refuses before reading a case, and two real
> tuning paths go through it (`measure_use_it_when_lines.py`, `measure_chat_routing.py`). Verified by execution: the
> guard raises on the holdout, and the holdout is still readable for scoring. Corpus split is now **303 tuned :
> 150 sealed**. Also fixed: `evaluate_retrieval_modes.py` silently scored 225 of 228 and now prints every dropped case
> and why, to stderr so stdout JSON stays clean. 19 tests.
> **Two caveats, both his to close.** The holdout's baseline (**hybrid recall@4 0.42**, bm25 0.2933) was measured
> against a *worktree* index (`v-db8c6334cf63`, 4,642 chunks), **not the live one** (`v-07328d9baf04`, 3,206 chunks),
> so it must be re-measured before it is recorded; and 0.42 is higher than the 228's 0.333 for scoring-policy reasons,
> not retrieval gains. Separately, **3 of the 228 are genuine retrieval questions lost to substring matching** in
> `_expects_public_abstention` ("What setup **should I use**?" + "**mic**"; "**Wwise**"). Left alone because fixing it
> changes scoring — it is his call.

| C3 | Reranker decision: measure the cross-encoder on the box and on the Mac with Live open. Adopt only if sealed recall@4 gains ≥ 0.10 at ≤ 150 ms on the Mac | M | Mac, box |
| C4 | "Use it when…" lines: Jack ticks the drafts, then `measure_use_it_when_lines.py` | S | Jack |
| C5 | Parameter reference from Live's own displays after A3: `build_parameter_reference.py`, then `check_notes_against_measurements.py`; anything outside a measured range is fixed or drafted back | M | A3 |
| C6 | Craft notes for the first three genres: draft on the notes model on the box, check against cited sources, review before approval; third-party material only with rights | L | Jack picks genres; review |
| C7 | Answer audit: 100 answers, count those with no citable source (must be 0) and the grounding-gate rejections and their top warning | S monthly | |
| C8 | Stage 3b leftovers: `_clean_chunk_for_synthesis` cutting mid-word or mid-fence; only one preference per key surviving, with no way to list or restore the rest | S each | |

**Gate (week 4):** sealed-set recall@4 ≥ 0.60 (the end-state gate is ≥ 0.95 on the full fixture and ≥ 0.80 on the
sealed set); manual chunks in the index and grounding-qualified; 0 uncited claims in the audit.

### Track D: speed and the brain
Serves: Stage 1's open item (answers written by the brain, cited, with templates as the offline fallback) and the
monthly "how often the model's answer lands" measure.

| ID | Task | Size | Needs |
|---|---|---|---|
| D1 | Measure on the Mac with Live open: start with `KENN_LLM_BACKGROUND=1`, ask 30+ knowledge questions, run `route_latency_report.py` (attempts, accepted rate, median and p95 of accepted) | S | Mac |
| D2 | Cut the prompt (fewer, shorter excerpts) and reuse the prompt cache between turns; tokens a second before and after | M | Box, then Mac |
| D3 | Model options on the sealed chat set (grow it from 84 to 200): Qwen3 4B vs 8B, quantisation levels, MLX vs Ollama; one change at a time with `evaluate_chat_brain.py` | M | Box |
| D4 | Style fine-tune of the 8B: hold until there are ≥ 500 owner-approved answers (the first attempt was worse) | hold | |

**Gate (week 4):** timing measured and written down for the M3; the target stays ≥ 70% of knowledge answers upgrading
within 15 s with the grounding check passing.

### Track E: ship and testers
Serves: Stage 0 exit (qualified gate, 3 testers) and the beta plan.

| ID | Task | Size | Needs |
|---|---|---|---|
| E1 | **Parked to the very end** (owner, 30 Sept: KENN isn't good enough yet). Developer ID, then wire signing and notarisation into `build_kenn_app.py` | S after ID | Jack |
| E2 | **Parked** (owner, 30 Sept: not worth testing yet). Choose 3 testers with their own projects; the invite, reviewer brief and supervised session script already exist | S | Jack |
| E3 | Rollback and update path: keep the last two DMGs, a "how to go back" note, the version shown in the app | M | |
| E4 | Check on the installed build that diagnostics send receipts and timings only, never audio or typed text | S | |
| E5 | A weekly review of what KENN did not understand, fed into B4 (starts when testers do) | S weekly | E2 |

### Track F: engineering health and working together
Serves: Stage 3b, the North Star risk "a gate quietly stops gating" (an audit is a recurring cost, not a one-off), and
the monthly measures.

| ID | Task | Size | Needs |
|---|---|---|---|
| F1 | `sync_kenn_app.sh`: the monorepo-to-`kenn-app` sync as one command: split `products/kenn`, check the fast-forward, scan the new commits for secrets and attribution lines, run the CI script on a fresh worktree, then push. It does by script what was done by hand on 30 Sept | S–M | Done 30 Sept on branch `kenn-sync-script`; reaches `main` with the next release |
| F2 | A monthly measures report: one command printing the North Star's list (understanding, answer quality, recall, latency by stage, unauthorised writes, undo success, how often the model's answer lands) and the two added on 28 Sept (answers with no citable source; grounding-gate rejections and why) | M | **Done 30 Sept** on branch `kenn-measures-report` |

> **F2, 30 Sept** (branch `kenn-measures-report`): `tooling/scripts/monthly_measures.py` runs the **existing** evaluation
> scripts and quotes their output verbatim — it never recomputes a measure, because a measure that quietly changes
> definition is the "a gate quietly stops gating" failure this task exists to stop. On a fresh worktree it prints 13
> measures in ~10 s (slowest `e2e_demo_commands.py`, 7.9 s) and **exits 2**, because one required-zero measure cannot
> be measured with no retrieval index. Two traps it found and refuses to walk into: `evaluate_retrieval_modes.py`
> with no index prints recall **0.0 and exits 0** (a green look for nothing), and `eval_chat_coverage.py` with no
> index reports `found: false` on all 128 rows, so counting rows would give a confident **0 = PASS** on a retrieval
> path that is not running. Both now report "not measured" with the reason. **Undo success reads 292 / 297 = 98.3%,
> a FAIL against the North Star's "must be 100%"** — all 5 are "Track creation has no safe automatic inverse", so KENN
> asks to undo rather than lose one. Reported, not gated, and it is a real gap in the number we claim.
> Two bugs in its own draft were exactly the target failure and are now regression-tested: a fully unmeasured run
> exited **0**, and both "could not count it" branches dropped the measure from the gate list entirely.
> 18 tests. `docs/runbooks/MONTHLY_MEASURES_RUNBOOK.md`.

| F3 | A personal-path gate for KENN like SLO's, and scrub the 52 files and 156 places that name a home path, the Live volume or the GPU host | M | **Done 30 Sept** on branch `kenn-path-gate`; reaches `main` with the next release |

> **F3, 30 Sept** (branch `kenn-path-gate`): measured before touching anything, the plan's "52 files and 156 places"
> was close but not exact — **47 tracked files, 164 occurrences** of a home, volume or `/home/` path, of which **40
> files and 140 occurrences were real** (`/Volumes/Jack_Gandy_1TB_SSD/` ×134, `/Users/Ganders4/` ×6). The other 24
> were already placeholders (`/Volumes/X`, `/Users/example`, `/Users/Shared`, `/Volumes/...`). The 140 were rewritten
> to `~/`, which is how a person writes a path anyway, so the gate below needed no debt list — unlike SLO's, which
> ships a 124-file / 34,722-occurrence ratchet precisely because that debt was never scrubbed.
> **The GPU host was still committed, which the plan's own wording ("or the GPU host") had not been matched
> against:** `ubuntu@www.haoee.com` appeared in 6 tracked box scripts and 1 evidence doc, against AGENTS.md's "never
> commit remote hostnames". `run_tests_on_box.py`, `sync_gpu_notes.sh`, `sync_gpu1_notes.sh`,
> `notes_server_preflight.sh`, `deploy-and-run-notes.sh` and `run_kenn_command_pilot_remote.sh` now read
> `KENN_SERVER_TARGET` / `KENN_SERVER_PORT` and fail loudly when unset, so **they will not run until that is
> exported** — that is the cost of not having the hostname in git. Also found: `phase4_testing_assets_stem_matrix.json`
> listed the contents of a private stem library (`al_james/01_Kick.wav` and 57 siblings), which AGENTS.md's "zero
> private audio, user stems" also forbids; the paths are now `~/`-relative.
> The gate is `tooling/scripts/check_personal_paths.py`, run as step **[9/9]** of `ci_verification.sh`, which both
> `kenn-core.yml` and `kenn-ci.yml` already invoke — so unlike SLO's, which no workflow calls despite two SLO docs
> claiming it "fails the build", this one actually stops the build. Current state: `personal-path-gate=pass
> tracked_files=1218 findings=0`. `test_personal_path_gate.py` (24 tests) checks both directions against the nine
> lines that actually leaked, and fails if a placeholder is added to the allowlist that nothing uses.
> `ci_verification.sh` green on the branch: backend **2,461 passed / 125 skipped**, chat 38, Mix Review 66, AutoMix
> 4 + 4. **History still contains the original paths and hostname**; rewriting history is an owner decision and the
> gate says so rather than implying otherwise. Also noted, not acted on: 290 of `deploy-and-run-notes.sh`'s 319 lines
> are unreachable behind an `exec`, so that file is a tombstone pointing at the read-only preflight.


| F4 | One `chat` package: `chat/` and `packages/chat/` both exist with their own `app.py`, `eval_runner.py` and `index_runtime.py`, and tooling loads the wrong one under the bare name `app`. Pick the canonical copy, remove the other | M | **Analysis done 30 Sept** on branch `kenn-chat-copies`; **the decision is Jack's** (plan decision 8) |

> **F4, 30 Sept** (branch `kenn-chat-copies`, `docs/reviews/KENN_CHAT_PACKAGE_DUPLICATION_2026-09-30.md`): all three
> claims in the task row are true, and the third is worse than stated. `chat/` is 11 files, `packages/chat/` is 23;
> `index_runtime.py` is byte-identical, `packages/chat/app.py` is a **strict superset** (310 insertions / 17 deletions —
> `POST /chat`, `/mix-review`, `/feedback`, request-ID middleware, 29 more `MIX_ADVICE_TERMS`, and the handler that
> turns the retrieval layer's `SystemExit` into an abstention). Measured independently: with
> `PYTHONPATH=apps/backend/src:tooling:packages/chat:...`, **all three of `app`, `eval_runner` and `index_runtime`
> resolve to `packages/chat/`** while `ci_verification.sh:22` runs `chat/tests`. So the copy CI exercises is the one
> nothing imports, and the copy everything imports has **never been run by CI** — `packages/chat/tests` is 41 test
> functions against `chat/`'s 16, and it holds the only coverage of `/mix-review`, `/feedback`, the 50 MB upload
> ceiling, path traversal and prompt injection.
> **Recommendation in the review: make `packages/chat/` canonical** (it owns all 13 runtime call sites; `chat/` wins
> only on CI, which is one line). **The flip is not one line, though, and this is the part that would have bitten
> us:** `packages/chat/tests` has **zero `pytest.skip` calls**, so 8 of its tests hard-fail on a fresh checkout where
> the git-ignored index is absent — verified here, `8 failed, 57 passed` — and `chat/tests/test_app.py:189` has the
> guard the other copy lacks (`if not client.get("/health").json()["retrieval"]["available"]: pytest.skip(...)`).
> So the removal needs those 8 guards (or an index build in CI) **before** line 22 flips, plus three hand-written
> target lists that move together (`qualify_internal_beta.py:504`, `run_tests_on_box.py:35`,
> `test_internal_beta_gate.py:357`). The review lists every file and line that breaks, six docs already pointing at
> `chat/` for files that only exist in `packages/chat/` (`OPERATIONS.md:85` cites a `chat/tests/test_public_api.py`
> that does not exist), and the same `mix-review/` / `automix/` duplication. Nothing was deleted — that is decision 8.


| F5 | CI: a fresh-clone "skips budget" (fail if the skip count grows), a weekly scheduled run of the chaos suite and phrasing scorer, a pull-request template | S | |
| F6 | Each release, audit every gate with a test that reproduces its bypass (the 28 Sept lesson) | S per release | |
| F7 | Point the 10 old plan docs that are still linked at the North Star, then delete them | S | |
| F8 | GitHub Team so `main` on `kenn-app` can be protected (rulesets are not enforced on a private repo today) | — | Jack decides |

### Track G: new control and capability families
Serves: Stage 3 breadth and Stage 5. **Starts in week 3, and only after A3 has passed.** Order by value over effort:

| ID | Task | Size |
|---|---|---|
| G1 | Return-track rename and solo (with A6) | S |
| G2 | Clip gain and transpose, then loop points, then warp: each with readback and exact undo | M each |
| G3 | Groups and ungroup; routing | M each |
| G4 | Automation write | L |
| G5 | Save (Accessibility, hash-checked) | L |
| G6 | Live capture path: spike resample track vs Max for Live vs loopback, licence-checked (the Listens row) | M |
| G7 | MIDI ideas as preview, then insert with undo (Stage 5) | L |

Every family ships the same way: proposal, stale check, write, readback, receipt, exact undo, fake-Live tests, a
walkthrough row, and a Live-night qualification before it is called supported.

## 5. Working together

- **Lanes.** Jack: Live nights, the owner decisions, Mac timing, reviews, testers. Colleague: blind rounds as the
  second author, the retrieval fixture (C2), the path scrub and CI work (F3, F5) with no Live needed. Claude sessions:
  implementation, GPU-box training and evaluation, the dry runs.
- **Repo.** Work happens on branches with pull requests in `Nite-DSP/kenn-app`, and the monorepo takes `main` back at
  each release with F1. Nothing is committed to `main` between starting a soak and committing its receipts.
- **Tests.** Everything except Live nights runs on the fake backend (`KENN_LIVE_BACKEND=fake`). A change is not done
  until the CI script passes on a fresh checkout.
- **Evidence.** Blind rounds report the first-run number and the wrong plans first; nothing is promoted because it
  demos well.

## 6. Live nights

| Night | When | Length | Contents | Needs before |
|---|---|---|---|---|
| 0 | Tonight | 1 h soak | Tempo, time signature, return rows; the soak with one Live pause | Approved |
| 1 | Week 1 | ~2 h | Device factory wave 1 | Device-zoo set (A2) |
| 2 | Week 2 | ~1 h | The 15 recipes | Fake-Live dry run passes |
| 3 | Week 3 | ~1.5 h | Wave 2, return rename/solo, first new family | Wave 1 signed off |
| 4 | Week 4 | 1 h | Release soak and a full regression of everything qualified | Code frozen on `main` |

Each night starts when Jack says "ready", and a Live pause needs his approval for that run.

## 7. Gates and measures

| Measure | Now | Week-4 target | North Star end state |
|---|---|---|---|
| Qualified devices and parameters | 8 devices, 14 profiles | ≥ 12 and ≥ 40 | ≥ 25 and ≥ 60, then all 78 |
| Recipes on real Live | 0 of 15 | 15 of 15, exact undo | Same, ≤ 3 s a step |
| First-run understanding on a fresh register | about 40% | ≥ 85% on real wording | ≥ 95% on ≥ 500 phrasings, 3+ authors |
| Wrong plans in a blind round | 0 in the last rounds (found ones fixed before commit) | 0 | 0 |
| Retrieval recall@4, sealed set | 0.34–0.45 | ≥ 0.60 | ≥ 0.80 sealed, ≥ 0.95 on ≥ 300 |
| Official-manual chunks in the index | 0 | > 0, grounding-qualified | Manual above notes in trust order |
| Model answer lands within 15 s (16 GB M3, Live open) | about 1 in 6 (26 Sept) | Measured, plan set | ≥ 70% |
| Answers with no citable source | not counted | 0 in a 100-answer audit | 0 |
| Testers onboarded | 0 | Parked | 5–10 |
| Sign and notarise | waiting on Developer ID | Parked to the end | Done |
| Unauthorised writes | 0 | 0 | 0 |
| Undo success | 100% on what is qualified | 100% | 100% |

## 8. Risks

| Risk | What we do |
|---|---|
| Real Live behaves differently from the fake backend | The qualifier writes, reads back and restores every value; nothing is marked supported until a Live night passes it |
| Live is only on Jack's Mac and is needed for work | Four batched nights, each with a written checklist and a fake-Live dry run first |
| A device sweep leaves a parameter changed | The sweep is read-only first; the qualifier restores each value and the walkthrough checks the set is back to its baseline |
| Wording accuracy stalls | Tester wording and a second author, not more synthetic rules; the planner stays in shadow |
| A gate quietly stops gating | F6: a test that reproduces each bypass, audited every release |
| Two repos drift apart | F1 makes the sync a checked one-liner; the monorepo stays the source of truth |
| Knowledge with a confident tone and a wrong number | Measured ranges from Live, source tiers, and the 100-answer audit |
| Small team | Track G waits for A3; nothing in it starts on hope |

## 9. Decisions needed from Jack

1. Sign off this plan and the North Star's direction (still open in the North Star).
2. The three pinned policy calls: bare "X to -N", "kill playback", "reverb on the vocal" (B2).
3. Ingest the Live manual now, as a local-only index? (C1; open in the North Star.)
4. Which genres first for craft notes (C6; open in the North Star).
5. The reranker rule: adopt only for ≥ 0.10 sealed recall@4 at ≤ 150 ms on the Mac (C3).
6. Stage 3b: work the three open items now (C8); the cross-project cache leak and the `validate_llm_plan` range gaps
   are already fixed, and these three do not block the beta.
7. ~~The Developer ID (E1) and three tester names (E2).~~ Parked by the owner on 30 Sept: revisit when KENN is good enough, Developer ID last.
8. Which copy of `chat` is canonical (F4).
9. GitHub Team for branch protection, or keep pull requests as a convention (F8).
10. The Live-night schedule in section 6.

## 10. First ten tasks, none needing Live

1. **F1** the sync script. *Done 30 Sept, on `kenn-sync-script`.*
2. **C1** the manual ingest (after decision 3).
3. **A2** the device-zoo checklist and preparation script. *Done 30 Sept, on `kenn-device-zoo-wave1`.*
4. **B1** blind round 9 in a new register, written by a second author.
5. **C2** the retrieval fixture with a sealed half.
6. **F3** the personal-path gate and scrub. *Done 30 Sept, on `kenn-path-gate`.*
7. **D1** the Mac timing measurement.
8. **F2** the monthly measures report.
9. **B4** the wording triage script.
10. **F4** the analysis of the two `chat` copies, ready for review. *Done 30 Sept, on `kenn-chat-copies`; the choice is decision 8.*
