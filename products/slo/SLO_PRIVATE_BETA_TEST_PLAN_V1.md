# SLO Private Beta Test Plan V1

**Scope**: what needs testing before and during a controlled private beta. Distinguishes what this session already produced real evidence for vs. what needs a live human session.

## Pre-beta (owner + engineering, before any tester sees a build)

| Test | Status | Notes |
|---|---|---|
| Clean build (`ssm_qual_full`) | **Done, repeatedly** | Verified multiple times this session, zero duplicate-symbol errors |
| Read-only safety on fixture library | **Done** | Real SHA-256 checksums, before/after — see `SLO_READ_ONLY_SAFETY_QUALIFICATION_V1.md` |
| Cross-vendor classification accuracy | **Done** | 62.9%/30.2% full-evidence/audio-only, honestly reported |
| OOD/Unknown behavior | **Done** | 72.0% false-known / 17.7% false-unknown, cross-vendor, first time measured |
| Performance at scale (100/1k/10k files) | **Done** | See `SLO_PRIVATE_BETA_PLAN_V1.md` §7 |
| Soak / memory leak check | **Done** | 30-iteration soak, flat RSS after warm-up |
| RT deadline/allocation stress | **Done** | 0/2000 deadline misses, 0 allocations |
| **Live GUI click-through** (scan → results → search → filters → preview) | **NOT DONE — needs a human** | This session cannot drive the actual GUI |
| **Clean-machine install** | **NOT DONE — needs a human, physical/VM Mac** | Same class of gap as Submit's B-002 |
| **Real Ableton Live host test** | **NOT DONE — needs a human, live DAW** | Same class of gap as Submit's Ableton-specific work |
| App restart / crash recovery | **NOT DONE — needs a live app session** | Cache/index reload behavior on restart is untested in this pass |

## During beta (tester-facing)

- **Cohort**: owner-approved only, per the beta definition. Naming testers is an owner decision (same pattern as `NITE_DSP_SUBMIT_BETA_LAUNCH_CHECKLIST_V1.md`).
- **Feedback focus, in priority order**: (1) any file-safety concern at all — this should be impossible per §Read-Only Safety, but tester reports are the real-world check on that claim; (2) classification usefulness — does the taxonomy actually help find sounds, independent of raw accuracy percentages; (3) Unknown/uncertain handling — does "I don't know" read as honest or as broken; (4) performance on the tester's own (likely much larger and messier than this session's test corpus) real library; (5) crashes/hangs.
- **What NOT to collect**: no requirement to upload audio anywhere (local-first, see infrastructure doc) — feedback should be structured text/screenshots, not sample files, unless a tester explicitly opts to share a specific problem file for debugging.

## Fixture-only destructive-test discipline

Any test that could plausibly mutate, move, or delete files (Sort Library, cache quarantine/rebuild logic, etc.) must run against fixture data only — this was already the existing convention across every `Test*` target in this codebase before this session (verified: every engine-touching test calls `setCacheDbDirectoryOverrideForTesting()` or an equivalent isolation mechanism), and `TestReadOnlySafetyQualification` (this session's new addition) explicitly follows the same rule for its own fixture library. No test in this codebase runs against a real owner sample library, and none should.
