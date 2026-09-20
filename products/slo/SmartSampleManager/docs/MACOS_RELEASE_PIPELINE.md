# macOS Release Pipeline

Phase 6, Section 59. Consolidates the release pipeline as it actually exists today across
Phase 2's design (`docs/MACOS_RELEASE_PROCESS.md`, `docs/INSTALLER_ARCHITECTURE.md`) and Phase
5-5.6's tooling. This is the authoritative step list; the two docs above remain the deeper design
rationale for signing/notarization and installer packaging respectively.

```text
FRESH RELEASE BUILD          cmake --build build-release (clean, current source)
       ↓
NATIVE TESTS                 12 Test* executables, run individually -- 12/12 required, zero leaks
       ↓
IDENTITY GUARD                scripts/verify_identity_manifest.py
       ↓
RELEASE MANIFEST              scripts/verify_release_manifest.py (VST3, AU, Standalone)
       ↓
RECURSIVE DEPENDENCY BUNDLE   scripts/bundle_apple_deps.py (runs as a POST_BUILD step already --
                               not a separate manual invocation)
       ↓
DEPENDENCY GRAPH VALIDATION   scripts/check_homebrew_dependencies.py (VST3, AU, Standalone)
       ↓
SECRET SCAN                   strings + grep against every bundled Mach-O binary for key
                               material/secret-shaped strings -- manual this phase, see
                               docs/PHASE_6_FINAL_SYNTHESIS.md for the exact commands used
       ↓
CODE SIGN                     BLOCKED EXTERNAL -- no Developer ID Application certificate
       ↓
PACKAGE                       BLOCKED, chained on signing -- docs/INSTALLER_ARCHITECTURE.md
       ↓
SIGN INSTALLER                BLOCKED, chained on signing
       ↓
NOTARISE                      BLOCKED EXTERNAL -- no Apple Developer Program membership
       ↓
STAPLE                        BLOCKED, chained on notarization
       ↓
GATEKEEPER VALIDATE           BLOCKED, needs a signed+notarized artifact
       ↓
AU VALIDATE                   PARTIAL -- `auval -v aufx AtSm NDSP` genuinely run against the real
                               built component this dev machine, Phase 7:
                               "AU VALIDATION SUCCEEDED." Real evidence the component itself is
                               structurally valid, not fabricated -- but still not equivalent to
                               what a customer experiences (unsigned, this machine already has
                               every dependency this exact build needs). Full BLOCKED status
                               remains for the signed+notarized+clean-machine version of this
                               check.
       ↓
VST3 VALIDATE                 same as above
       ↓
STANDALONE VALIDATE           same as above
       ↓
CHECKSUM                      Ready -- sha256sum against the final signed artifact once it exists
       ↓
UPLOAD                        BLOCKED EXTERNAL -- no hosted release storage exists yet
                               (docs/RAILWAY_DEPLOYMENT.md's known object-storage gap)
       ↓
RELEASE RECORD                Ready -- releases table + admin release-management endpoints
                               already exist (docs/NITE_DSP_BACKEND_IMPLEMENTATION.md)
```

## What's genuinely READY today (verified this phase)

Everything up to and including "DEPENDENCY GRAPH VALIDATION" -- confirmed via
`scripts/signing_preflight.py`, which mechanically re-runs the manifest + identity + Homebrew
checks and reports "Build/manifest/identity preflight: READY" for all three formats.

## What's BLOCKED EXTERNAL, and why nothing after it can be faked

Every step from CODE SIGN onward chains on the missing Developer ID Application certificate
(itself chained on Apple Developer Program membership). AU/VST3/Standalone validation is listed
as blocked *at this stage* specifically because validating an *unsigned* build proves less than
validating what a customer actually receives -- the meaningful validation happens after signing,
ideally on a genuinely clean machine (`docs/CLEAN_MACHINE_TEST_PROCEDURE.md`), not before.
