# KENN private beta: plan from the current state

**Written:** 2026-09-24 · **Owner:** Jack · Tick items in the same commit as the work, with the date and the evidence.

This plan supersedes the beta parts of `KENN_BETA_SPRINT_PLAN_2026-09-06.md`, `KENN_BETA_PLUS_PLAN_2026-09-07.md`,
`KENN_BETA_ROADMAP.md` and `BETA_SCOPE.md` (whose 1 Sept scope, chat and Mix Review only with no Live control, no longer
describes KENN). The GLM tracker (`KENN_GLM_FULL_ASSISTANT_TRACKER.md`) stays the log for the wider programme.

## What the beta is

**Who:** 5–10 invited producers on macOS with Ableton Live 12 Suite, supervised (onboarding call, feedback channel).
Not public.

**The promise** (everything else is off or labelled experimental):

1. **Knows your session.** Tracks, selection, devices, returns and master, change history, with freshness shown.
2. **Controls Live safely.** Proposes a bounded change, waits for Apply, writes, reads it back, keeps an undoable
   receipt. Mixer (volume in real dB, pan, mute, solo, arm, sends), device focus, the measured device parameters,
   inserting the 10 allowlisted audio effects.
3. **Answers with sources.** Cited answers from KENN's approved notes (74 of Live's 78 devices), and it says when it does
   not know.
4. **Listens to a render.** Loudness, true peak, clipping and low-end findings from an exported mix or stem, clearly
   separated from Live state.
5. **Never surprises you.** No write without Apply; delete, master level and destructive requests refused; everything
   undoable.

**Out of the beta:** the AI planner writing to Live (stays in shadow, collecting evidence), AutoMix, audio generation,
voice, arbitrary plug-in control, silent saves.

## Where KENN is today (measured 2026-09-24)

| Area | State |
|---|---|
| Tests | Backend 1,592 passed, 5 skipped |
| Demo gate | 2 owner runs passed (run 1; today's run pending its 8–12 min timing), plus one agent run; need 10 |
| Live control | Verified apply → readback → undo on real Live; fader law measured; device focus fixed today |
| Language | Rule parser 80/124 (64.5%) with 0 wrong plans; typos can slip past refusals ("et the master volume…") |
| Knowledge | 74/78 devices with an approved note; BM25 index, retrieval fixture recall@4 0.966 |
| AI planner | Run 4 fine-tune in background shadow; promotion gate (500 comparisons / 14 days) not met |
| Qualified beta gate | **3/14** (`qualify_internal_beta.py --profile qualified`): see Phase 2 |
| Install | **Not ready.** The tester guide's `.pkg` does not exist; setup needs this Mac's paths, a terminal and env vars |
| Known defect | `KENN_Bridge` Remote Script in the User Library fails to load (IndentationError, line 888) at every Live start |
| Idle wake | First Live read after hours idle returned "offline", then recovered |

## Decisions needed from you (before Phase 1 ends)

- [ ] **Confirm the promise above** as the beta scope (it replaces `BETA_SCOPE.md`).
- [ ] **Distribution.** Signed and notarized app/installer needs an Apple Developer ID (£79/year, your account). Without it,
      testers must bypass Gatekeeper by hand. Recommendation: buy it.
- [ ] **Testers.** Names or a shortlist of 5–10; at least 3 bring their own real projects (needed for the pilot gate).
- [ ] **Two independent reviewers** for the human-review packet (people who did not write KENN's answers).
- [ ] **Feedback channel** (BB-3): e.g. a private Discord channel or a form. Recommendation: one channel plus an
      in-app "send diagnostics" button.
- [ ] **Diagnostics consent.** What testers' KENN may send back (recommend: receipts and timings only, never audio).
- [ ] **`Audio_Too` dependency** (BB-1): Mix Review still reads a Thursday-owned branch. Vendor the three qualified
      detectors into KENN, or drop Mix Review from the beta and keep the new loudness/true-peak path.

## Phase 1: Make it installable (week 1) — biggest gap

The beta cannot start while KENN only runs from this Mac's checkout.

- [x] Fix or remove the broken `KENN_Bridge` Remote Script so Live starts clean
  > 2026-09-24: a duplicated, mis-indented line (repo line 1045; installed copy line 888) fixed in the repo; new test compiles all 46 Remote Script files. The installed copy was moved to `User Library/Remote Scripts/.backups_2026-09-24/`: KENN does not use it and it listens on port 11000 like AbletonOSC, so the beta installer must not ship it.
- [x] One companion bundle: KENN backend + UI as a macOS app (`apps/desktop/macos/build_macos_app.sh`) with its own
      Python runtime, no repo paths, no env vars (DAW control, capture paths and model settings become app settings)
  > 2026-09-24 progress: `tooling/scripts/build_kenn_app.py` builds `KENN.app` (arm64) in ~40 s: Swift launcher with a
  > bundled mode, standalone CPython 3.13.15 (python-build-standalone, SHA-256 pinned), runtime packages, KENN in its repo
  > layout, and the active index, notes, embedding model, UI and native DSP module from the main checkout. Settings and
  > data: `kenn/app_entry.py` (`~/Library/Application Support/KENN`, `settings.json`). Checked from an empty environment:
  > healthy, hybrid retrieval, cited answers, UI served. 540 MB uncompressed (scipy, onnxruntime, sklearn, numpy, model);
  > trim later. Still to do: launch-by-double-click test with Live, Remote Script install, first-run check, DMG.
  > Later the same day: unused packages and test suites pruned (91 MB), DMG 207 MB; every build now runs a smoke test
  > on the bundle (health, hybrid retrieval, setup status, cited answer, Mix Review) and fails if any check fails.
- [x] Installer puts AbletonOSC (KENN build, version-stamped) in the user's Live User Library and tells them to select it
      in Live's Control Surface settings
  > 2026-09-24: `kenn/core/live_setup.py` + the app's **Set up KENN** page: finds the User Library from the newest
  > Live's `Library.cfg`, installs the deploy tool's exact file list with a stamp, hides the previous copy in
  > `.kenn-backups`, explicit confirm. Checked from the built bundle on this Mac.
- [x] First-run check inside the app: the read-only preflight (Live connected, script version, knowledge index, audio
      analysis) with plain-English fixes
  > 2026-09-24: three checks (Live installed, AbletonOSC current, Live connected) with fixes; the app opens on
  > `/setup` and goes straight in when all pass. Index and audio are verified by the build and the bundle smoke test.
- [x] Uninstall and update path (update keeps receipts and settings)
  > 2026-09-24: all user data lives in `~/Library/Application Support/KENN`, so replacing the app keeps it; steps in
  > the tester guide. Setup offers an AbletonOSC update when the stamp differs.
- [x] Rewrite `docs/BETA_TESTER_GUIDE.md` to match what actually ships (remove the nonexistent `.pkg`, "autonomous"
      wording and unshipped workflows)
  > 2026-09-24: rewritten. The old guide also told testers to enable `KENN_Bridge` in a second slot, which shares port
  > 11000 with AbletonOSC and would break the connection.
- [ ] Sign and notarize (after the Developer ID decision); `package_macos_plugins.sh` pattern already exists
- [ ] **Exit:** a clean macOS user account (or second Mac) goes from download to "Live connected, 8 tracks" on the demo set
      in under 15 minutes following only the guide
  > Ready to try once the soak ends (the running dev companion holds ports 8090/11001): `build_kenn_app.py --dmg` →
  > `workspace/builds/kenn-app/KENN-beta-<commit>.dmg`. Owner test on a second macOS user account.

## Phase 2: Reliability and the qualification gate (weeks 1–2, overlaps Phase 1)

- [ ] Idle-wake: retry the first read after long idle before reporting "offline"; test with Live idle 2+ hours
  > 2026-09-24: code done — a Live that answered earlier in the process gets one retry (0.4 s) before "offline"; a never-reached Live still reports offline at once (latency budget kept). Real 2-hour idle test still to do (fold into the soak).
  > Later the same day the first soak found the real cause: the AbletonOSC client's circuit breaker opened after one
  > missed reply and skipped every later read with no retry, so KENN showed Live "offline" for 4 hours while it was
  > fine, until a probe. Now half-open: one real read every 5 s while "disconnected" (`a7bf41a`, regression test).
- [x] Refusals survive typos: destructive and master-level requests are refused even with a missing letter or odd wording
      (fuzzy intent check before falling to knowledge answers)
  > 2026-09-24: safety words allow one missing letter or swapped pair ("delte", "mastr"; real words like "remote" stay
  > safe); master level refused without the word volume ("master to max", "crank the master"); the chat route forwards a
  > slipped first verb ("et the master…") and put/bring/push/crank/take/kill. Checked through `/kenn/api/ask` on the
  > real companion; 22 new tests; 124 cases unchanged (80, 0 wrong).
- [x] Companion restart keeps the audio-analysis cache warm (persist it) so a restart cannot break an answer
  > 2026-09-24: measured results (never audio) persist by content hash in `kenn/data/analysis_cache/` (16 files max; `KENN_ANALYSIS_CACHE_DIR` overrides; tests isolated). After a companion restart with no preflight, demo steps 12–13 answered in 0.2–0.4 s (cold: 3.2 s) and the gate passed.
- [ ] ~~24-hour~~ 12-hour soak with Live restarts, companion restarts and sleep/wake (`companion_soak` gate)
  > Gate needs 24 h on one companion process and ≥ 1 Live disconnect/reconnect: run overnight when no code is being deployed; owner quits and reopens Live once.
  > 2026-09-24: owner cut it to **12 hours** so the Mac stays usable. First run (from ~15:00) invalid: the breaker bug
  > above froze the reported Live status from 15:49. Fixed, branch merged into `main`, companion restarted, real-Live
  > assistant task re-passed; **second run started 20:16, ends ~08:16 Fri 25 Sep**, bound to `c40532b` (no commits on
  > `main` until it ends). Still needs one Live quit/reopen.
  > 25 Sept: run 2 ran clean for ~11 h, then the Mac slept on low battery at 07:06 and shut down (67 samples short, and
  > no Live reconnect yet), so it doesn't count. **Run 3 started 12:42, ends ~00:42 Sat**, on the final code
  > (`98581b2`: last night's fixes, index `v-4fd17ceb264f` with the rack notes, rebuilt review packet). Before it
  > started: tester-guide walkthrough 13/13 and the real-Live assistant test passed on real Live.
- [x] Regenerate stale evidence: `automated_suite`, `intelligence` (`--run-suite --run-intelligence`),
      `planner_bakeoff` (missing input `chat/evals/ableton_deliberative_adversarial.json`), `real_live_assistant`
      (lifecycle/replay check failing), `artifacts` (five named docs missing)
  > 2026-09-24 progress — gate 4/14 → with suite: **artifacts** pass (gate now looks in docs/reports|plans|runbooks);
  > **planner_bakeoff** pass (re-run on the box, GPU 0: 3 repeats × both sealed suites all passed, mean 2.6 s);
  > **automated_suite** fixed (Mix Review imports Audio_Too's `server/app` and `shared/nite_core` again; each suite target
  > runs in its own process because Audio_Too packages shadowed KENN modules) — passes on re-run.
  > Blocked on owner: **intelligence** needs hybrid retrieval (MiniLM embedding model, ~90 MB pinned download, not yet
  > approved); **real_live_assistant** needs the box's planner server (running since 9 Sept) restarted with the repo
  > version of `serve_transformers_ollama_compat.py` (only a `--cuda-devices` flag differs) — box rule: no restarts.
  > Done later on 24 Sept after owner approval: MiniLM pinned and hybrid index `v-7a5d8c12e5bb` (recall@4 0.966) →
  > **intelligence** pass; planner server restarted once → **real_live_assistant** pass on real Live. Gate **8/14**.
- [x] Refresh the human-review packet against the current index (`human_review` is stale after today's rebuild)
  > Packet builder works (100 cases, 3 s). Build the final packet after the embedding decision, since it binds the active index.
  > 2026-09-24: rebuilt on the hybrid index at a clean HEAD (`ABLETON_ASSISTANT_HUMAN_REVIEW_PACKET_2026-09-24.json`).
  > Rebuild again if the index changes (the 3 rack notes are approved but not yet indexed).
- [ ] **Exit:** gate shows every engineering gate passing; only human, pilot and distribution gates left
  > 2026-09-24: 8/14; every engineering gate passes except the soak (running). Tests also run on the GPU box's CPUs
  > (`tooling/scripts/run_tests_on_box.py`) so results don't depend on this Mac.

## Phase 3: Fill the capability gaps testers will hit first (weeks 2–3)

- [ ] D1 wave 1 on real Live, same method as the fader law: Compressor (threshold, ratio, attack, release, makeup),
      EQ Eight (every band's frequency, gain, Q), Utility (gain, width), Limiter, Reverb/Hybrid Reverb, Delay/Echo;
      commands generated per parameter and run end to end (`e2e_demo_commands.py`)
- [x] Rule parser to ≥ 80% of the 124 cases with 0 wrong plans; the owner's review-page test commands all pass
  > 2026-09-24: **105/124 (84.7%)**, 0 wrong plans (was 80). General rules, tested on self-written phrasings rather than
  > the evaluation set: insert verbs (stick/drop/throw a …), "new midi track", "return channel", "start the song",
  > locators (drop/place), corrections ("no wait, … not the hats"), "call track N …", ordinals ("the fourth channel"),
  > mute/solo slang (kill, nuke, out of the mix, on its own, just the …), terse pan and volume, focus verbs. Owner test
  > commands 1/1; e2e 21/22 unchanged. Then device focus by name ("show me the bass eq") and sends to a named return
  > without the word send ("synth to the delay at 20 percent"): 109/124. Then two-part requests joined by a plain "and"
  > when both halves are clear ("mute the hats and the snare", "solo the bass and turn it up 2 dB"; e2e apply → verify →
  > exact undo 3/3): **112/124 (90.3%)**, 0 wrong plans. Still asks: device parameters by name, pan without an amount,
  > terse dB without a direction ("kick -3 dB": absolute or relative?).
- [x] Advice → fix: each audio finding offers one confirmable change and re-measures after Apply
  > 2026-09-24, owner's call: keep it simple for the beta. Each audio review ends with **one next step to say**
  > (`core/advice_next_step.py`): "turn the Bass down 1 dB" for heavy low end when exactly one bass/sub track exists,
  > "turn the Lead Vocal down 3 dB" for vocal clipping (with the export-vs-recording caveat), otherwise a question that
  > gets a cited answer ("how do I keep my master under -1 dBTP?"). Commands are offered only if they parse to a clean
  > proposal, so they still go proposal → Apply → readback → Undo; KENN never changes the master. Re-measuring = export
  > again and ask again. In chat audio advice now; Mix Review's own panel (Vue frontend) not yet.
- [ ] Notes for the last 4 devices (Instrument/MIDI/Audio Effect Rack, Drum Synth) and a small review of the 21 notes
      approved today
  > 2026-09-24: 3 of 4 — Instrument, MIDI and Audio Effect Rack notes approved (77/78 devices). Drum Synth has no
  > entry in the Live 12 manual, so it waits for a measured note. Review of the 21 notes not yet done.
- [x] Planner: rebuild the C6 corpus with dB volume labels, train run 7, keep in shadow; revisit promotion when the
      gate's 500 comparisons / 14 days are met (likely during the beta itself)
  > 2026-09-24: run 7 trained on the box (GPU 0) with dB labels: volume values fixed, but "bass" solos Drum Bus, so it
  > stays in shadow (not promoted). Run 8 corpus ready (confusable track names + exact-track contrast rows); training next.
- [ ] **Exit:** every command in the tester guide works on a fresh demo set and on one real project
  > 2026-09-24, real Live (demo set) through the chat route: 10/11. "Bring the bass down 2 dB" answered "not sure": the
  > gateway took a topology-only snapshot (no fader values) for wording without "volume"/"turn up/down", so the relative
  > change had nothing to start from. Fixed (`d902c4f`: any dB or up/down wording reads the mixer, plus a re-read when the
  > parser reports a missing current volume). The demo backend now drops mixer values from topology reads as real Live
  > does, and `test_tester_guide_commands.py` runs the guide's commands end to end. Re-check on real Live after the soak.

## Phase 4: Human evidence (weeks 3–4, needs people)

- [ ] Finish demo rehearsals 3–10 (at least one with the recovery drill, one on the projector)
  > 2026-09-24: rehearsal 3 (owner) passed 20/20; 7 to go.
- [ ] Two reviewers score the refreshed 100-case packet; adjudicate (`human_review` gate)
- [ ] Real-mix listening set with consent, two reviewers (`real_mix` gate)
- [ ] Supervised pilot: 10 sessions across 3 real projects with you watching; zero unauthorised writes, false receipts,
      lost undos or crashes (`supervised_pilot` gate)
- [ ] **Exit:** `qualify_internal_beta.py --profile qualified --check-live` returns 14/14

## Phase 5: Launch the beta (end of week 4)

- [x] Known-limitations page and support runbook shipped with the app
  > 2026-09-25: the tester guide, known limitations included, opens inside the app (`/guide`, linked from Setup &
  > Support; the build pre-renders it). `docs/runbooks/KENN_BETA_SUPPORT_RUNBOOK.md` rewritten for the app beta:
  > first reply, common reports, the "must never happen" list, fixing and shipping, rollback.
- [ ] Feedback channel live; diagnostics button sends receipts and timings only
  > 2026-09-24: diagnostics half done — **Setup & Support** (app toolbar) → **Save diagnostics for support** writes one
  > redacted file (receipt counts by action and outcome, answer timings p50/p95, versions; no track names, values,
  > questions, audio or paths) to `~/Library/Application Support/KENN/diagnostics`. It saves rather than sends until the
  > feedback channel is chosen. Click-test in the rebuilt app after the soak.
- [x] Rollback: previous app version and previous knowledge index one click away
  > 2026-09-25: the app bundles its knowledge index, so the previous DMG is the previous app *and* index. Every build
  > writes `KENN-beta-<commit>.dmg` next to the older ones in `workspace/builds/kenn-app/`; rolling back is installing
  > the previous DMG (settings and history in `~/Library/Application Support/KENN` are kept). Steps in the support
  > runbook. For the dev index, `index_store.rollback_index()` switches to `PREVIOUS`.
- [ ] Invite the first 3 testers; onboarding call each; widen to 10 after a clean first week
- [ ] Weekly: triage feedback, re-run the gate, publish a short changelog

## Order of work while you are away or busy

Claude can do without you: Phase 1 (except signing), Phase 2 in full, Phase 3 engineering, evidence regeneration.
Needs you: the decisions list, signing credentials, rehearsals, reviewers, testers, pilot sessions.
