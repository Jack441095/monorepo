# KENN progress: where we are

**Updated:** 2026-09-26 01:40 · Ticked as each step finishes. Full detail lives in the two plans:
[beta plan](products/kenn/docs/plans/KENN_BETA_PLAN_2026-09-24.md) (Stage 0) and the
north-star plan (`products/kenn/docs/plans/KENN_NORTH_STAR_2026-09-24.md`, merged into `main` 26 Sept).

## Right now

- **Soak #3 passed** (00:43 Sat): 721/721 samples, 0 errors, one Live reconnect (3 min out), Live connected at the end,
  median reply 26 ms. It qualifies the code it ran on (`98581b2`).
- **Merged and pushed:** receipts committed, the north-star branch merged into `main` (1,902 tests pass), main pushed
  (`10f4f3d`). New app built: `workspace/builds/kenn-app/KENN-beta-8c32b1f.dmg` (220 MB; smoke test passed incl. the
  in-app tester guide). Frontend rebuilt, 24/24 frontend tests.
- **The merge moved the code, so the gate wants fresh evidence:** the soak and the real-Live assistant task passed on
  `98581b2`, not on the merged code, and the gate only accepts evidence from the exact release code. Needs Live open:
  re-run the real-Live assistant task (minutes), then soak #4 on the current main (12 h, one Live quit-and-reopen).
  The review packet was stale too; rebuilt on the merged code, so reviewers score the right answers.
- **Chat model on this Mac: off.** Qwen 8B took 7–16 s an answer through the companion (and far longer under load),
  and KENN used its answer only 1 time in 6; 4B was no better. Chat is back to instant template answers; run 11 stays
  in shadow for commands. Qwen 8B stays the choice for a faster machine or the box GPU (2.8 s there).
- **Live is closed** at the moment; the companion reconnects on its own when it's reopened.
- **Next (needs Live open):** real-Live assistant task on the current main, then start soak #4.
- **Needs you:** testers, two reviewers, Apple Developer ID; the drafts to send are in `products/kenn/docs/beta/`
  (tester invite, reviewer brief, supervised-session script).

## Qualified beta gate: 7 / 15 on the current main (`10f4f3d`)

- [x] artifacts · real_live · support_matrix · planner_bakeoff · real_live_assistant · automated_suite ·
      intelligence · source_snapshot (the engineering gates; source_snapshot re-passes once the soak change is committed)
- [ ] companion_soak — running (12 h)
- [ ] human_review — needs two reviewers (parked)
- [ ] real_mix — needs a consented listening set and reviewers (parked)
- [ ] supervised_pilot — needs testers (parked)
- [ ] plugin_distribution — signed, notarized archive; needs Developer ID (parked)
- [ ] release_provenance — passes automatically once all the others do
- Not a gate but tracked: demo rehearsals — 3 of 10 done

## Beta plan (Stage 0)

### Phase 1 — installable
- [x] Broken `KENN_Bridge` Remote Script fixed
- [x] `KENN.app` with its own Python, no repo paths or env vars (DMG 207 MB, smoke-tested every build)
- [x] Set up KENN page installs AbletonOSC into the user's Live User Library
- [x] First-run checks (Live installed, AbletonOSC current, Live connected)
- [x] Uninstall and update path
- [x] Tester guide rewritten (`products/kenn/docs/BETA_TESTER_GUIDE.md`)
- [ ] Sign and notarize — parked (Developer ID)
- [ ] Exit: clean macOS account, download → "Live connected" in < 15 min — after the soak

### Phase 2 — reliability
- [x] Refusals survive typos
- [x] Audio-analysis cache survives a companion restart
- [x] Stale evidence regenerated (gate 3 → 8/14)
- [x] Human-review packet rebuilt on the hybrid index
- [ ] Idle-wake: code done; real 2-hour idle test folds into the soak
- [ ] 12-hour soak — running
- [ ] Exit: every engineering gate passing — only the soak left
- [x] Test suite runs on the GPU box too (`tooling/scripts/run_tests_on_box.py`): **1,789 passed**, 12 skipped
      (Apple-only MLX, optional extras), ~2 min. Fixed on the way: the smoke tests' fixed port 8099 now picks a free one

### Phase 3 — capability gaps
- [x] Rule parser ≥ 80% of 124 cases, 0 wrong plans — **90.3%** (112/124); now also "kick to -12 dB"
- [x] Value check: the scorer now checks the dB/pan KENN would write, not just the action (rule parser 15/16)
- [x] Swept all 124 phrasings through the full command path (not just the parser) and found a **wrong plan**:
      "cut 2k on the bass by 3 dB" became a −3 dB *fader* cut on Bass. Now "2k"/"2 kHz" are EQ frequencies, a named
      band ("band 2A") is honoured, and any request naming a frequency can never become a fader change (branch `3549d9e`)
- [x] Adversarial sweep (29 phrasings that sound like a fader change but mean something else): 3 more wrong plans —
      "lower the bass by 3 dB below the kick" turned the *Kick* down; "drop the hats high end by 3 dB" cut the fader;
      "bring the kick down 3 dB in the verse" changed the whole song. Now all ask first; 29/29 (branch `b6eca2a`)
- [x] Second sweep, beyond the fader (sends, devices, inserts, transport, rename, arm; 32 phrasings): **1 more wrong
      plan** — "mute everything except the kick" muted the kick. Now asks; "play from the chorus" asks instead of
      ignoring "from the chorus"; "set the tempo to 128" says KENN can't change tempo instead of just reading it out.
      Compressor threshold "lower by 6 dB" checked against the real-Live table: correct (branch `b2138fe`, `c98480d`)
- [x] C6 planner run 7 trained, kept in shadow (not promoted: "bass" solos Drum Bus)
- [x] C6 run 8 trained and evaluated — **not promoted**: 60.5% vs run 7's 78.2%. It picks the right track but
      leaves out the track name, so KENN's safety check rejects the plan. Run 7 got every value right (16/16) on the
      new value probe. Run 4 stays in shadow. Next run needs a demo-style validation set and less training
- [x] C6 run 9: run 8's two changes tested separately. The contrast rows caused the regression; **9b** (confusable
      track names only) is the **best planner so far: 85.5% / 87.1%** (run 4, today's shadow model: 84.7%), 3 wrong
      plans accepted (fewest yet), values 16/16. Still reads 12 of 29 "sounds like a fader change" traps as fader
      changes, so it stays shadow-only (the rule parser gets all 29)
- [x] 9b is the shadow model (your OK, 25 Sept), 4-bit copy on this Mac's Ollama
- [x] C6 run 10 (trap examples): safest yet — 1 wrong plan accepted (9b: 3), traps 24/32 — but asks too often
      (77.4% vs 85.5%). 9b stays in shadow
- [x] C6 run 11 (trap examples at lower weight): **first run with zero wrong plans accepted** (both modes), asks on
      30/30 questions that need it, 29/32 traps, 16/16 values; 80.6% / 83.9% (asks a bit more than 9b). Strongest
      candidate for promotion so far
- [x] **Swap run 11 into shadow** (you approved, 25 Sept). Created on the Mac as `kenn-c6-run11` (4-bit, sha
      51bcf34d…), ~3–4 s a plan once loaded; the companion script now uses it. It takes effect when the companion
      restarts after the soak (the soak's companion keeps 9b until then). Still observation only
      25 Sept: on three fresh phrasing sets, 9b as a fallback added 7–17 wrong plans; run 11 added 2–7 and more
      right answers. The case for swapping is stronger now
- [x] "Use it when…" lines drafted for 114 Ableton notes on the GPU notes model (it saw only each note). Measured in a
      throwaway index: describe-it questions 0.744 → **0.760**, better ranking, nothing worse — a small gain, not the big
      lever hoped for. Sharper lines matter more than more lines
- [ ] **Needs you:** review them — tick, edit or delete each line in
      `products/kenn/docs/reviews/KENN_USE_IT_WHEN_REVIEW_2026-09-25.md` (on the branch). Only ticked lines go in
- [x] Rack notes indexed — index `v-4fd17ceb264f` (3,338 chunks, embeddings on the GPU box); retrieval unchanged
      (0.983 / 0.744); review packet rebuilt on it (`98581b2`). 77/78 devices; Drum Synth is not in the manual
- [ ] D1 device measurements on real Live — tool ready (`measure_device_parameters.py`); run after the soak
- [x] Advice → next step (see step 3 above)
- [ ] Exit: every tester-guide command works on the demo set and one real project — **demo set 13/13 on real Live
      (25 Sept)**; real project still needs you. Earlier (24 Sept) 10/11:
      **"Bring the bass down 2 dB" (the guide's first example) failed** — KENN skipped reading the fader for that
      wording and answered "not sure". Fixed on the branch (`d902c4f`), and the guide's commands now run in the test
      suite against a demo backend that behaves like real Live. Re-check on real Live after the soak; real project
      still to do (needs you)

### Phase 4 — human evidence (parked, needs people)
- [ ] Rehearsals 4–10 · [ ] two reviewers · [ ] real-mix listening · [ ] supervised pilot

### Phase 5 — launch (parked)
- [x] Save diagnostics for support (redacted counts + timings; toolbar **Setup & Support**) — click-test after the soak
- [x] Known limitations + support runbook: the tester guide (with its known-limitations section) now opens inside the
      app from Setup & Support; support runbook rewritten for the app beta, incl. the "must never happen" list
      (branch `223a353`; in the app after the post-soak rebuild)
- [x] Rollback: install the previous `KENN-beta-<commit>.dmg` (app and index together; builds are kept)
- [ ] Feedback channel (parked) · [ ] first 3 testers (parked)

## After the soak (~08:16 Fri)
- [x] 12-hour gate change committed on `main` (`c40532b`); branch merged into `main` (fast-forward)
- [ ] Check the soak receipt passes; commit it with the real-Live receipt on `main` (both bound to `c40532b`)
- [ ] Merge the branch's post-soak fixes into `main` (fast-forward); re-run the tester-guide walkthrough on real Live
- [x] Pushed `main` (`c40532b`) and the branch (`da336e6`) — 24 Sept evening
- [ ] Push the post-soak merge (ask first)
- [x] Rebuild the index with the rack notes; rebuild the review packet (done before the soak)
- [ ] Measure Compressor, EQ Eight, Reverb, Delay parameters on real Live
- [ ] Rebuild the frontend in the main checkout (`npm run build` with `/opt/homebrew/bin/node` — the node on PATH is
      Intel-only), then the app (Support button, in-app guide, Ask KENN button); DMG test on a clean account (you)
- [x] Companion restarted on the new code (20:15 Thu)

## North star (Stages 1–5)
- [x] Plan written (hybrid brain: local planner + hosted brain for conversation; stages with measured gates)
- [x] Brain decision (you, 25 Sept): **local Qwen only** — nothing leaves the Mac. You can also run a bigger Qwen on
      the box GPU for your own KENN (through the SSH tunnel); testers use a local Qwen on their Mac
- [x] Stage 1 step 1: Qwen brains compared on KENN's real answer path (84 questions, box GPU). **Qwen3 8B** (2.8 s) and
      **14B** (3.8 s) both write answers that pass the same checks as today's templates, with sources
- [x] Brain picked (you delegated it): **Qwen3 8B**. Same quality as 14B on KENN's checks, a third faster, and
      half the memory, which a 16 GB Mac needs. Copied to the Mac; speed check after the soak
- [ ] Next (me): 8B speed on your Mac after the soak
- [x] 8B style fine-tune tried: **worse, so plain 8B stays** (KENN used the model's answer 36/84 vs 40, and the
      slowest answers went 3.4 s → 9.7 s). Training on the model's own accepted answers taught it nothing
      new; worth retrying only with answers you've reviewed. Details in the brain review doc
      solo the Synth), so it stays in shadow. Run 11 is much safer: rules then run 11 get 89–95% right on the fresh
      sets (the beginner set goes 75% → 89%), with 2–7 wrong plans per set (e.g. "the track that has the bass" →
      Drum Bus). Better, but not "95% with zero wrong"
- [ ] **Needs you (when you have 20 min):** skim the phrasing labels, especially the rows with a `note`, in
      `products/kenn/tooling/data/natural_holdout_candidates.jsonl`; the gate counts owner-checked labels
- [x] C6 run 12 tried: **worse than run 11, so run 11 stays in shadow.** 2–13 wrong plans per fresh set against
      run 11's 2–7, some flipped ("pull back the bass" → unmute). It memorised its synthetic examples; the next
      planner needs real tester wording
- [ ] Stage 1 conversational KENN · [ ] Stage 2 deep Ableton knowledge · [ ] Stage 3 agentic co-producer ·
      [ ] Stage 4 memory · [ ] Stage 5 creation
