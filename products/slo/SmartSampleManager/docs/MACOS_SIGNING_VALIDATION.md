# macOS Signing Validation

# HUMAN ACTION REQUIRED

```text
STATUS: BLOCKED -- no Apple Developer Program membership exists
OWNER:  You
BLOCKS: Sections 24-34 of the Phase 5 master prompt (Developer ID signing, notarization,
        stapling, Gatekeeper/AU/VST3/standalone validation of a signed build)
REASON: See docs/HUMAN_COMMERCIAL_REQUIREMENTS.md -- "Apple Developer Program membership",
        "Developer ID Application certificate", "Notarization credentials"
```

Nothing in Sections 24-34 can be genuinely performed without a Developer ID Application
certificate and notarization credentials, both of which are issued only from a real Apple
Developer account. This document does not simulate, mock, or approximate any of these steps --
per Section 29, "If rejected: retrieve the reason and fix the real problem. Do not bypass," and
per the Section 88 STOP RULE more generally.

## What is genuinely ready for the moment credentials exist

- `cmake/BundleAppleDeps.cmake` already bundles TagLib/ONNX Runtime/libsodium into each format's
  `Contents/Frameworks/` with `@rpath`-rewritten load commands (Phase 2) -- this is the
  dependency layer signing operates on.
- The release manifest (`scripts/verify_release_manifest.py`) and the identity regression guard
  (`scripts/verify_identity_manifest.py`, new this phase) both pass against the current Release
  build (confirmed this phase after rebuilding a stale `build-release` directory -- see
  `docs/PHASE_5_FINAL_SYNTHESIS.md`), so signing would be applied to a build that is already
  known-clean in composition and identity.
- `docs/MACOS_RELEASE_PROCESS.md` (Phase 2) already documents the intended signing/notarization
  pipeline steps in detail.

## What genuinely cannot be verified here

Binary inspection for Homebrew/developer-machine paths (Section 27) *was* proxy-verified in
Phase 2 (hiding this machine's own Homebrew paths and confirming the app still runs) -- see
`docs/CLEAN_MACHINE_VALIDATION.md` for why that remains a proxy, not the real test. Actual
signing, signature validation on signed artifacts (not just checking exit codes -- Section 28),
notarization submission and result retrieval, stapling, and Gatekeeper/AU/VST3/standalone
validation *of a signed, notarized build* all require the real credentials this environment does
not have.
