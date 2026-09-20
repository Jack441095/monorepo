# Public Trial Validation

Phase 6, Section 75. **Not validated -- the trial system is not implemented.**
`docs/TRIAL_ARCHITECTURE.md` (Phase 3) is explicit: "Design document — no trial system is
implemented." Nothing has changed that since; no trial-issuance endpoint exists in
`nitedsp/backend/app/`.

## What the design specifies (for when it's built)

14-day full-featured trial, client requests a trial token on first launch, server issues a
trial-type `LicenseToken` (reusing the existing struct, `tier = "trial"`), the `trials` table
(already in the schema, unused) records `machine_id` + `product_id` to prevent trivial re-trial
abuse via the `UNIQUE (product_id, machine_id)` constraint. Trial expiry must not delete
customer library/creative data (Section 39) -- the trial only gates the *plugin's* license
check, never touches a user's sample files. Purchasing must unlock the *same* installation, not
require a reinstall (Section 39/75).

## Why this wasn't built this phase

Phase 4 explicitly deferred trial issuance as out of scope for the initial commercial backend
build ("no trial-issuing endpoint was built this phase -- trial issuance wasn't part of
Milestones B-H's scope"), and every phase since has correctly not built it speculatively ahead
of an actual need. Section 39 of this master prompt describes trial *requirements* for whenever
it exists; it is not, on its own, an instruction to build it now, and building a customer-facing
trial system as an incidental part of a broad launch-readiness pass risks exactly the kind of
under-scoped, under-tested feature Section 3's "hard release philosophy" warns against.

## What would need to happen before this document could report real evidence

1. Build the trial-issuance endpoint and `LicenseToken` trial-tier handling (a real, scoped
   implementation task -- not attempted this phase).
2. Validate the full journey: landing page → "Try Free" → account → download → install →
   activate trial → use → offline → trial expiry → purchase → same install becomes licensed.
3. Confirm no library data loss at any point in that sequence.

## Current website behavior (deliberately honest, not overclaiming)

`/pricing` notes a 14-day trial "is planned but not yet available" -- no "Try Free" CTA exists
anywhere on the site, since clicking one would currently do nothing real.
