# Release Candidate Validation

Phase 6, Sections 89-90. Template for the exact evidence a real Release Candidate must produce
-- **no RC has been cut.** Per Section 89, the exact artifact tested must be the exact artifact
published; nothing here claims that's happened.

## Full RC test matrix (Section 90) -- status against each item today

```text
[x] native tests                    12/12, zero leaks -- current, reconfirmed this phase
[x] commercial E2E                  11/11 -- current, reconfirmed this phase
[x] identity guard                  PASS -- reconfirmed this phase
[x] release manifest                PASS, all 3 formats -- reconfirmed this phase
[x] dependency graph                PASS, all 3 formats, zero forbidden paths -- reconfirmed
[x] Homebrew scan                   PASS -- same check as "dependency graph" above
[x] secret scan                     PASS -- reconfirmed this phase (all bundled Mach-O binaries)
[ ] signing                         BLOCKED EXTERNAL -- no Developer ID certificate
[ ] notarisation                    BLOCKED EXTERNAL -- chained on signing
[ ] Gatekeeper                      BLOCKED, needs a signed artifact
[~] AU validation                   PARTIAL -- real `auval` PASS on this dev machine (Phase 7,
                                     docs/CRITICAL_FINDING_LAUNCH_BLOCKING_BUG.md); signed +
                                     clean-machine version still BLOCKED
[ ] VST3 validation                 BLOCKED, same
[ ] Standalone                      BLOCKED, same
[ ] clean Mac                       BLOCKED EXTERNAL -- no clean machine available
[ ] Ableton                         BLOCKED, needs a signed build + clean/real machine
[ ] Logic                           BLOCKED, same
[x] account                         PASS -- magic-link auth verified live, this and prior phases
[ ] trial                           BLOCKED -- not implemented, docs/PUBLIC_TRIAL_VALIDATION.md
[x] activation                      PASS -- Ed25519, concurrency-safe, verified live
[x] offline use                     PASS at logic level -- 14-day grace period verified
[x] download                        PASS -- entitlement-gated signed URLs verified live
[ ] update                          BLOCKED -- update-channel checking exists in design only
                                     (docs/PHASE_5_PLAN.md's Section 60 scope), no client-side
                                     update-check implementation has been built or verified
[ ] project recall                  BLOCKED, needs a real DAW + signed build
[ ] hosted backend                  BLOCKED EXTERNAL -- no Railway deployment exists
[x] backup/restore                  PASS -- real pg_dump/restore rehearsal, Phase 5, evidence
                                     stands (no schema changes since to invalidate it)
[ ] Paddle sandbox                  BLOCKED EXTERNAL -- no Paddle account
[ ] refund sandbox                  BLOCKED, chained on Paddle sandbox
```

## Score: 10 ready / 14 blocked or not-applicable-yet

Consistent with `docs/PRIVATE_BETA_RC.md`'s 12/15 gate score -- some items above (trial, update
system) are additional launch-specific checks beyond the beta gate list, both correctly
unbuilt/unblocked-yet rather than fabricated.

## What "cutting an RC" will actually require

Once the BLOCKED EXTERNAL items above clear (signing credentials, clean machine, hosted
backend), cutting a real RC means: tag an exact commit, build once, run every check in this
matrix against that exact artifact, and never substitute a different build for what gets
published -- per Section 85's "release immutability."
