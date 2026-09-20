# NITE DSP Private Beta Plan — SmartSampleManager (Design Only)

Phase 3, Sections 74-78. **Plan document — no beta has been distributed.** Execution is blocked
on the same items throughout this phase: Apple Developer credentials (signed installer) and a
real clean-machine test (the mandatory gate, Section 78 — "no public beta until the installer
works on a clean system... this gate cannot be waived simply because the code compiles").

## What a tester receives (Section 74)

```text
1. Signed/notarized macOS installer (.pkg) -- NOT a raw dev build, NOT requiring Homebrew
   (satisfied by Phase 2's dependency-bundling work -- verified via the local
   hidden-Homebrew-paths proxy, docs/RUNTIME_DEPENDENCY_STRATEGY.md)
2. A beta license (entitlements.license_type = 'beta', see below)
3. Plain-language installation instructions (no terminal commands, no "run brew install")
4. A known-issues list (honest, current -- not "no known issues" unless genuinely true)
5. A feedback channel (structured report format -- see below)
6. A privacy notice covering what the beta build does/doesn't collect
```

## Beta license type (Section 75)

Already representable in `docs/NITE_DSP_DATABASE_SCHEMA.md`'s `entitlements.license_type` CHECK
constraint (`'beta'` is one of the allowed values) — no schema change needed. A beta entitlement:

```text
license_type = 'beta'
purchase_id  = NULL          -- no real payment record, satisfies Section 75's
                                 "without creating fake payment records"
expires_at   = <beta period end>
status       = 'active', can be flipped to 'revoked' at any time if the beta
                 needs to be pulled from a specific tester
```

Reuses the exact same `LicenseToken`/Ed25519 verification path as a real purchase — a beta
tester's client code path is identical to a paying customer's, which is itself useful beta
coverage (it exercises the real licensing flow, not a special-cased "beta mode").

## Beta feedback capture (Section 76)

Structured report fields:

```text
OS version
DAW + DAW version
Plugin format (VST3 / AU / Standalone)
Approximate library size (sample count, not the samples themselves)
Issue description
Steps to reproduce
Severity (tester's own assessment: blocking / major / minor / cosmetic)
Logs (AppLogger's existing output -- see Source/AppLogger.h -- already structured,
    already excludes sample audio/paths beyond what's needed for diagnosis)
```

**Never automatically request a tester's actual sample files** (Section 76's explicit
instruction) — this is already consistent with the existing local-first privacy boundary
(`docs/NITE_DSP_WEBSITE_ARCHITECTURE.md`'s privacy section): the commercial/beta-feedback
infrastructure has no legitimate reason to ever receive sample audio.

## Crash reporting (Section 77) — not yet implemented, scoped here for when it is

If added: version, OS, architecture, DAW, stack trace only. Explicitly excluded: sample names,
raw audio, project data, full private file paths (a stack trace referencing
`/Users/<realname>/Music/...` should be sanitized to a relative or redacted path before
transmission). Not implemented this pass — no crash-reporting SDK integration exists yet, and
adding one is a real, non-trivial scope item (SDK selection, privacy review of what it collects
by default, opt-in UX) that belongs in a dedicated pass once the beta program itself is closer to
running, not bundled speculatively into this planning document.

## Beta readiness gate (Section 78)

```text
[ ] Signed, notarized installer exists           -- BLOCKED on Apple Developer credentials
[ ] Clean-machine test passed (real, not proxy)   -- BLOCKED on clean-machine hardware
[ ] NITE DSP identity finalized                    -- BLOCKED on your sign-off
                                                        (docs/NITE_DSP_PRODUCT_IDENTITY.md)
[ ] Beta entitlement issuance path exists            -- BLOCKED on production licensing
                                                          deployment (docs/PRODUCTION_LICENSING_ARCHITECTURE.md)
[ ] Known-issues list is current                       -- can be prepared once the above are done
```

**None of these gates are met yet.** This document exists so that once they are, the beta program
itself doesn't need to be designed from scratch under time pressure.

## Recommended beta cohort size and duration

Not specified by the master prompt; reasonable default for a first private beta of a desktop
plugin: **10-20 testers, 2-4 weeks**, small enough for genuinely responsive one-to-one feedback
handling (no support infrastructure exists yet — Section 68's admin tooling is still design-only),
large enough to surface real-world DAW/OS/library-size variation the internal test suite can't
cover (real Ableton Live/Logic Pro project recall, real large libraries, real hardware variety).

## Status

**Plan only.** No beta invitations, licenses, or installers have been created or distributed.
