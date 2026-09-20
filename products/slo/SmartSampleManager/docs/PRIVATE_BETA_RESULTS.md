# Private Beta Results

Phase 6, Sections 69-73. Template for recording real beta evidence -- **no private beta has
run yet.** `docs/PRIVATE_BETA_RC.md`'s gate is NOT READY (12 PASS / 3 BLOCKED EXTERNAL as of
Phase 5.6), and per Section 69's own instruction, real-user beta testing must not be skipped
just because engineering readiness is high. This document has nothing to report until testers
actually use the product.

## Why nothing is here yet

Inviting real testers before a signed, notarized build exists would mean either (a) asking
testers to bypass Gatekeeper themselves -- not representative of the real customer experience
this beta is supposed to validate, or (b) using unsigned dev builds -- which is exactly the
"test real user paths" violation Phase 5.5's `docs/CLEAN_MACHINE_TEST_PROCEDURE.md` warns
against (Section 40). Beta testing is sequenced after signing/notarization/clean-machine
validation, not before.

## Structure ready for when testing begins

**Tester roster** (Section 70): prefer coverage across Ableton Live, Logic Pro, different macOS
versions, Apple Silicon (and Intel only if Intel support is actually shipped -- not claimed
here, since `docs/RUNTIME_DEPENDENCY_STRATEGY.md`'s bundling has only ever been built/tested on
Apple Silicon).

**Feedback structure** (Section 71) -- fields to collect: product version, macOS version,
architecture, DAW + version, plugin format, sample library size, issue description, reproduction
steps, severity, safe logs. Explicitly not requested by default: proprietary sample files.

**Triage classification** (Section 72):
```text
P0 -- data loss / security / unusable      -> fix before continuing
P1 -- crash / major workflow failure       -> fix before public launch
P2 -- meaningful defect                    -> fix based on launch impact
P3 -- polish / minor                       -> backlog
```

**Evidence to track** (Section 73): installation success rate, activation success rate, plugin
scan success, crash reports, library indexing reliability, Find Similar reliability, DAW recall
success, support-request volume/friction. None of these have any data yet.

## Status

**BLOCKED** -- sequenced behind Apple signing/notarization and the real clean-machine test, both
themselves BLOCKED EXTERNAL. Update this document with real entries once a beta actually runs.
