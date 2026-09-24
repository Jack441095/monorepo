# KENN progress: where we are

**Updated:** 2026-09-24 evening · Ticked as each step finishes. Full detail lives in the two plans:
[beta plan](products/kenn/docs/plans/KENN_BETA_PLAN_2026-09-24.md) (Stage 0) and the
north-star plan (`products/kenn/docs/plans/KENN_NORTH_STAR_2026-09-24.md`, on branch `kenn-north-star-and-app`
until the merge after the soak).

## Right now

- **Running:** 12-hour companion soak on this Mac, ends ~03:00 Fri 25 Sep. Nothing is committed on this checkout
  until it ends (the receipt is bound to commit `ef27425`). New work goes on branch `kenn-north-star-and-app`.
- **Done since last update:** C6 run 8 evaluated (regressed, not promoted); a new retrieval test exposed a real
  knowledge gap (below). Box Ollama stopped, GPU 0 back to baseline.
- **Next:** the after-soak steps below.
- **Needs you (when convenient):** quit and reopen Live once before ~03:00 (the soak must see one reconnect); rotate
  the GPU box password.
- **Question for you:** advice → fix. Each audio finding should offer one change you can Apply, but the obvious
  fixes need your call: true peak over −1 dBTP → a Limiter on the master (KENN's boundary blocks master changes
  today); low-end excess → which track gets the cut? And re-measuring needs a fresh export, which KENN can't make yet.
  My suggestion: offer the change only when a finding names one track, and ask for a re-export to re-measure.
- **Question for you:** a stronger embedding model for knowledge search (e.g. bge-small-en-v1.5, MIT licence,
  ~130 MB) — only if you're happy with another pinned download. See the Stage 2 note below.
- **Parked until the end (your call):** testers, reviewers, Apple Developer ID signing, feedback channel.

## Qualified beta gate: 8 / 14

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
- [x] C6 planner run 7 trained, kept in shadow (not promoted: "bass" solos Drum Bus)
- [x] C6 run 8 trained and evaluated — **not promoted**: 60.5% vs run 7's 78.2%. It picks the right track but
      leaves out the track name, so KENN's safety check rejects the plan. Run 7 got every value right (16/16) on the
      new value probe. Run 4 stays in shadow. Next run needs a demo-style validation set and less training
- [ ] Rack notes indexed — 3 approved, index rebuild after the soak (77/78 devices; Drum Synth not in the manual)
- [ ] D1 device measurements on real Live — tool ready (`measure_device_parameters.py`); run after the soak
- [ ] Advice → fix → re-measure
- [ ] Exit: every tester-guide command works on the demo set and one real project

### Phase 4 — human evidence (parked, needs people)
- [ ] Rehearsals 4–10 · [ ] two reviewers · [ ] real-mix listening · [ ] supervised pilot

### Phase 5 — launch (parked)
- [x] Save diagnostics for support (redacted counts + timings; toolbar **Setup & Support**) — click-test after the soak
- [ ] Known limitations + support runbook · [ ] feedback channel · [ ] rollback · [ ] first 3 testers

## After the soak (~03:00 Fri)
- [ ] Check the soak receipt passes; commit the 12-hour gate change + receipt on `main`
- [ ] Merge `kenn-north-star-and-app` into `main` (push only with your OK)
- [ ] Rebuild the index with the rack notes; rebuild the review packet
- [ ] Measure Compressor, EQ Eight, Reverb, Delay parameters on real Live
- [ ] Rebuild the app (new Support button); double-click install test of the DMG on a clean account
- [ ] Restart the companion on the new code

## North star (Stages 1–5)
- [x] Plan written (hybrid brain: local planner + hosted brain for conversation; stages with measured gates)
- [ ] Your sign-off on the direction, brain provider and budget — parked
- [x] Stage 2 baseline measured: when you describe what you want without naming the device ("line up two mics a
      few ms out"), KENN finds the right note in its top 4 only **62%** of the time (named topics: 97%). A tested fix
      (merge keyword and embedding results) lifts it to **74%** with no loss elsewhere; not shipped yet (it changes
      how KENN decides "I don't know", and the gate evidence). Gate target 95% on 300 questions (now 253)
- [ ] Stage 1 conversational KENN · [ ] Stage 2 deep Ableton knowledge · [ ] Stage 3 agentic co-producer ·
      [ ] Stage 4 memory · [ ] Stage 5 creation
