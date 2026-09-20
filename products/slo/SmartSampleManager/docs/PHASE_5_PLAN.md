# Phase 5 Plan — External Enablement + Private Beta Release Candidate

## What this phase is and isn't

Not another architecture phase. Phase 4 built and verified real, running commercial
infrastructure locally. Phase 5's job is to connect that infrastructure to the real external
prerequisites a genuine private beta requires: a real domain, real email, real Apple signing,
a real (sandbox) Paddle account, a real hosted environment, and a real clean-machine test.

## What this environment can and cannot do

**Can do without new credentials** (executed this phase): rerun and verify both test suites,
find and fix a real migration-reversibility bug via a backup/restore + migration rehearsal, add
an identity-drift regression guard, add rate limiting to auth/licensing/download/admin
endpoints, scan built artifacts for leaked secrets and localhost references, harden the beta
entitlement workflow (email invite, sensible default expiry). All of this genuinely moves the
codebase closer to release-ready without touching anything that requires an external account.

**Cannot do without you** (Section 88's STOP RULE, not a limitation to work around): Apple
Developer Program membership and signing/notarization, a real domain and DNS (SPF/DKIM/DMARC),
a real transactional email account, a real Paddle sandbox account and its API/webhook
credentials, real hosted staging (a VPS/PaaS + managed Postgres), and a genuinely clean macOS
test machine. None of these can be fabricated, approximated, or worked around with more code --
doing so would produce false confidence, which is worse than an honest blocker. See
`docs/HUMAN_COMMERCIAL_REQUIREMENTS.md` for the current status of each.

## Identity

Not applied this phase either. Section 6 of the master prompt describes what happens *if* you
explicitly approve the NITE DSP identity -- the master prompt text itself is not that approval.
`docs/NITE_DSP_PRODUCT_IDENTITY.md` remains AWAITING USER. The identity regression guard built
this phase (`scripts/verify_identity_manifest.py`, `docs/APPROVED_IDENTITY_MANIFEST.json`)
protects the *current* shipped identity ("Audio Engineering Company" / `AECO` /
`com.audioengineeringcompany.smartsamplemanager`) from accidental drift either way -- it is not
itself an identity decision.

## Order of work this phase

1. Rerun both test suites (Section 1) -- found and fixed a stale `build-release` directory
   failing the release manifest check (missing bundled dependencies from a build predating
   Phase 2's bundling work).
2. Identity regression guard (Sections 7-8).
3. Rate limiting (Section 56).
4. Database backup/restore + migration rehearsal (Sections 57-58) -- found and fixed a real
   migration-reversibility bug.
5. Config-leak / no-localhost scan (Sections 46-47).
6. Beta entitlement workflow hardening (Sections 21-23).
7. Documentation pass reflecting genuine state, including explicit BLOCKED status for every
   credential-gated workstream.
8. Final Phase 5 report (Section 86) and rescore (Section 85).
