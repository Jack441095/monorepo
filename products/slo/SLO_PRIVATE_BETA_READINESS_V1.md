# SLO Private Beta Readiness V1

**Updated:** 2026-08-28, following `NITE_DSP_SLO_MASTER_PLAN_V1.md` Phases 0-4 (see that file for full evidence trail and commit history — this doc states the verdict, that one carries the receipts).

## Verdict

**Still not ready for external/private-beta distribution qualification** — three P0 blockers remain fully open, and all three need the owner, not more engineering (see below).

**Conditionally suitable for a controlled internal read-only classification pilot**, same as before, using tester-owned/synthetic libraries, with no automatic sorting, no accuracy promise beyond the documented benchmark scope, and visible Unknown/OOD states. This conditional path is now on firmer footing than the last version of this doc: the clean-build blocker is gone, and the accuracy/performance evidence behind it is real, cross-vendor, and no longer resting on a synthetic proxy.

## What changed since the last verdict

- **B-012 (P0, build) — CLOSED.** The 13,044-duplicate-JUCE-symbol build break is fixed and verified (`ssm_qual_full` green, zero duplicate-symbol occurrences). The product now has a build that actually completes.
- **B-006 (P1, accuracy reporting) — CLOSED.** The headline accuracy number this doc's predecessor implicitly leaned on (96.5%, blended) is retired. In its place: an honest **62.9% full-evidence / 30.2% audio-only** split, measured on 620 real, licensed, cross-vendor (14 vendors) commercial sample-pack files — not the synthetic sine/noise golden set the 5.9%-audio-only figure everyone was citing came from. Full report: `SmartSampleManager/docs/classification/REAL_CORPUS_CROSS_VENDOR_V1_REPORT.md`. No production classifier code changed — this closes the *reporting* honesty gap, not an accuracy-improvement gap. Don't read this as "accuracy improved"; read it as "the number was wrong before, and now it isn't."
- **B-009 (P1, performance) — CLOSED.** Real 100/1k/10k-file scale receipts plus a 30-iteration soak test, all against real commercial audio, not synthetic fixtures. Soak result is clean: RSS plateaus after cache warm-up with no growth trend across 29 repeated scans. Peak RSS grows sub-linearly with corpus size (2.7GB → 3.0GB → 4.2GB across 132 → 1,359 → 10,034 files) — a large fixed floor, not a per-file blowup.
- **B-011 (P2, Sort Library) — PARTIALLY CLOSED.** Sort Library now defaults to **copy**, not move, and the confirmation dialog was corrected to describe that accurately (it previously would have described a move it no longer performs). This directly strengthens the "explicit consent before any move/rename" pilot control below — a copy-by-default posture is safer than what this doc previously certified. Still missing: an explicit user-facing copy-vs-move choice, and rollback evidence beyond "copying leaves originals in place."
- **B-010 (P2, RT instrumentation) — CLOSED.** `NITE_DSP_SLO_MASTER_PLAN_V2.md` Phase 8. The V1 concern ("needs new JUCE plugin-client build plumbing, too risky to rush") turned out smaller than feared — an existing precedent (`TestPrecisionBrowserSorting`) already proved the pattern. Built `TestRtDeadlineStress`: 2000 real `processBlock()` calls, deadline/allocation-tracked, `playSample()` stress interleaved. **Result: 0/2000 deadline misses, 0 allocations.** `SLO_RT_THREADING_AUDIT_V1.md` updated with this instrumented evidence — verdict is still PASS WITH LIMITATIONS / NOT QUALIFIED as a hard RT gate, but the allocation/timing gap specifically is now closed with real numbers, not just source review. Real Ableton validation (B-004) is the only thing still missing for full RT qualification.
- **B-005 — reclassified BLOCKED, needs Jack.** `AL-002` is an explicitly protected/sealed evaluation set ("no protected labels or predictions are exposed... no completion receipt was available to authorize a pass claim"). This is not an engineering task — fabricating a substitute review would defeat the point of a protected holdout.
- **B-007 (P1, OOD gate) — CLOSED**, `NITE_DSP_SLO_MASTER_PLAN_V2.md` Phase 6. First-ever cross-vendor false-known measurement: **72.0%** (121/168 real, genuinely out-of-taxonomy files — worse than the single-vendor 41.6%/47.2% baseline). False-unknown cross-check on the known population: 17.7% (110/620). Also fixed a real UI gap: "Unknown" results were showing the identical text as never-scanned files.
- **B-008 (P1, Vocal Loop) — CLOSED (verification), claim still suppressed.** `NITE_DSP_SLO_MASTER_PLAN_V2.md` Phase 7 + V3 follow-up. The existing fix (`e85feec`) did not generalize: 0% Vocal Loop recall cross-vendor (0/22) on 3 non-KSHMR vendors, vs. 7.5% single-vendor. Two distinct root causes identified; the smaller one (a "BVs" abbreviation-recognition gap) was fixed, moving recall to **4.5% (1/22)**. The dominant cause (tempo-only-tagged vendors never satisfying the fix's tempo+key signal, 21/22 real misses) remains a genuine design-effort item, not fixed. Decision unchanged: treat Vocal Loop classification as unreliable in any user-facing claim until a dedicated remediation phase.

## Minimum pilot controls

- arm64 macOS only;
- AU-first; VST3/Ableton explicitly experimental;
- one plugin instance and bounded fixture-size guidance;
- no owner/customer audio in the audit corpus;
- read-only classification and review;
- explicit consent before any move/rename — **now actually true at the code level**, not just a UI promise: Sort Library's default action is a non-destructive copy (see B-011 above);
- crash/log collection that excludes audio contents and license secrets;
- rollback and cache backup instructions;
- feedback focused on false positives, Unknown behavior, memory, and host stability.

## Exit criteria (for full private/external beta, not the internal pilot above)

- ~~Close P0 build blocker~~ — **done** (B-012).
- **Close the three remaining P0 blockers — all need the owner, not more engineering**: signed/notarized distribution (B-001, needs Apple Developer ID access), production licensing endpoint with real credentials (B-003), clean-machine validation on a physical/VM Mac this session doesn't have (B-002).
- Complete AL-002 blind review (B-005) — **blocked on Jack**, not an engineering task (protected/sealed evidence set).
- Qualify Ableton (B-004) — needs a GUI DAW session, not started.
- ~~Regenerate the classification/performance gates on authorized cross-vendor data~~ — **done** (B-006, B-009), using Jack's own licensed sample-pack corpus.
- ~~Close B-007 (OOD cross-vendor gate) and B-008 (Vocal Loop)~~ — **done, verified**: false-known 72.0% cross-vendor (B-007), Vocal Loop 0% cross-vendor recall / claim suppressed (B-008). Both numbers, not both green — closing the blocker means the honest measurement now exists, not that either one passed.
