# Phase 5.5 Plan — Close All Codex-Resolvable Private-Beta Blockers

## What this phase is

Implement/integrate/verify/harden/close-gates only -- no redesign of working Phase 4/5 systems.
Apply the now-approved NITE DSP identity. Search for (not fabricate) the domain/email the master
prompt claimed were "sorted." Close every remaining engineering gap that doesn't require a
credential this environment doesn't have.

## First finding: domain/email were not actually supplied

A repo-wide search (Section 7's explicit instruction: search first, never infer from the company
name, report "VALUE REQUIRED" if genuinely absent) found no real domain or email address
anywhere in the repository or available context. `docs/DOMAIN_CONFIGURATION.md` and
`docs/EMAIL_CONFIGURATION.md` report this per the master prompt's own specified format, rather
than fabricating `nitedsp.com`/`support@nitedsp.com` or similar.

## Second finding: baseline regression caught a real regression

Section 2's mandatory pre-change rerun found `build-release/` stale (same issue Phase 5 already
found and fixed once -- it had drifted again since). Rebuilt fresh before any Phase 5.5 changes;
confirmed 12/12 native, 9/9 commercial E2E, and a clean release-manifest pass before proceeding.

## What was applied this phase

1. NITE DSP identity, per `docs/NITE_DSP_PRODUCT_IDENTITY.md`'s Phase 3 proposal exactly -- see
   `docs/FINAL_PRODUCT_IDENTITY.md`.
2. Production config fail-closed validation (backend `config.py`, website
   `check-production-config.mjs`) -- Section 23.
3. `/health` and `/ready` endpoints, verified against a real Postgres outage-and-recovery --
   Section 48-49.
4. Production email templates (`email_templates.py`), wired into every live trigger that exists
   (magic link, beta invite, license ready, purchase confirmation) -- Section 19.
5. Website copy audit -- found already accurate (no semantic-search/Ableton-partnership
   overclaims existed) -- Sections 15-18.
6. Concurrency tests -- found and fixed two real race conditions (activation-limit
   over-allocation, duplicate webhook double-processing) -- Sections 50-51.
7. **A major dependency-bundling gap** -- ONNX Runtime's ~85 transitive Homebrew dependencies
   were never bundled by Phase 2's original `cmake/BundleAppleDeps.cmake`, only the three
   top-level libraries. Replaced with `scripts/bundle_apple_deps.py`, which walks the full
   transitive dependency graph. This is the single most consequential finding of this phase --
   see `docs/PHASE_5_5_FINAL_SYNTHESIS.md`.
8. `scripts/check_homebrew_dependencies.py`, `scripts/signing_preflight.py`,
   `scripts/clean_machine_acceptance.py` -- new automated guards/preflight tooling, Sections
   58-61, 64.
9. `docs/CLEAN_MACHINE_TEST_PROCEDURE.md`, `docs/DAW_VALIDATION_MATRIX.md`,
   `docs/BETA_TESTER_GUIDE.md`, `docs/BETA_TROUBLESHOOTING.md` -- Sections 40-42, 60-62.

## What remains genuinely blocked (unchanged in kind from Phase 5, narrower in scope)

Apple Developer credentials, a real clean machine, real hosted staging, a real Paddle sandbox
account, and now also confirmed: a real domain and company email. See
`docs/PRIVATE_BETA_RC.md`'s re-evaluated gate and `docs/PHASE_5_5_FINAL_SYNTHESIS.md`'s full
report.
