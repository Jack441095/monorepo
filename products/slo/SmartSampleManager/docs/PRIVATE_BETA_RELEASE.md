# Private Beta Release

Phase 4's closing milestone. Updates `docs/PRIVATE_BETA_PLAN.md` (Phase 3, design-only) against
what Phase 4 actually built.

## What's ready

- A real commercial backend (auth, licensing, commerce webhook, downloads, admin) running
  against a real Postgres schema, all verified this phase (`docs/STAGING_E2E_RESULTS.md`).
- A real website with account/sign-in, product/pricing pages, and legal placeholders.
- Admin tooling (`docs/NITE_DSP_BACKEND_IMPLEMENTATION.md`'s `admin.py`) sufficient to manually
  issue a beta tester a comp license without needing real commerce -- `POST
  /admin/entitlements/issue {license_type: "beta"}` -- exercised successfully this session.
- Phase 2's hardened plugin: 12/12 regression tests passing, dependency bundling implemented and
  proxy-verified, use-after-free bugs fixed, release-manifest enforcement in CI.

## What blocks an actual private beta tester from receiving anything today

Every item is already tracked in `docs/HUMAN_COMMERCIAL_REQUIREMENTS.md` and unchanged by this
phase's implementation work -- implementation doesn't remove a human-credential blocker, it just
means the blocker is now the *only* thing standing between "code exists" and "a beta tester has
it":

1. **Identity** -- `docs/NITE_DSP_PRODUCT_IDENTITY.md` still AWAITING USER approval. Nothing
   ships under the NITE DSP name until this is confirmed.
2. **Apple Developer Program membership** -- blocks signing, notarization, and therefore any
   distributable macOS build at all.
3. **A clean macOS test machine** -- `docs/CLEAN_MACHINE_VALIDATION.md`, BLOCKED, cannot be
   waived.
4. **A domain + support email** -- needed before the website or installer can display real
   contact information.

None of these can be resolved by further code changes. This document does not propose additional
implementation work to work around them -- per the STOP RULE, that would be inventing speculative
work rather than reporting a genuine blocker.

## Recommended next action (yours, not a code task)

Of the four blockers above, (2) Apple Developer Program membership is the one with the longest
external lead time (account review) and the widest downstream blast radius (it also blocks (3)
indirectly, since the clean-machine test is only useful once there's a signed build to test) --
starting that enrollment is likely the highest-leverage next step, but it's your call given cost
(~$99/yr) and whether NITE DSP as a real business entity should exist first.
