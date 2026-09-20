# Clean Machine Validation

# HUMAN ACTION REQUIRED

```text
STATUS: BLOCKED -- no genuinely clean macOS machine or VM available
OWNER:  You
BLOCKS: The mandatory clean-machine release gate; cannot be waived
REASON: See docs/HUMAN_COMMERCIAL_REQUIREMENTS.md
```

This gate cannot be passed or faked from this development environment, and per the Phase 4
STOP RULE this document does not pretend otherwise.

## What exists instead (a real proxy, explicitly not a substitute)

Phase 2 verified the dependency-bundling implementation (TagLib/ONNX Runtime/libsodium bundled
into each plugin format's `Contents/Frameworks/`) by temporarily renaming this machine's own
Homebrew install paths (`/usr/local/opt/{taglib,onnxruntime,libsodium}`) and confirming the built
app still launched and used ONNX Runtime/CoreML correctly. This is evidence that the bundling
mechanism works, not proof the plugin runs on a machine that never had these dependencies
installed via any other means (system frameworks, a different package manager, prior manual
installs, etc.) -- see the original note in `docs/HUMAN_COMMERCIAL_REQUIREMENTS.md`.

## What would actually close this out

A spare Mac, a fresh VM provisioned specifically for this test, or a cloud macOS CI runner
(GitHub Actions macOS runners are close but come with Homebrew and various dev tools
preinstalled, which is itself a confound worth being aware of if that path is chosen) -- none of
which this environment can provision on your behalf.

## Phase 5 note

Re-reviewed against the master prompt's Section 37-40 (clean-machine flow) and Section 39
(failure policy: "If anything only works after installing Homebrew/a dylib/developer
tool/SDK, the release fails"). Still BLOCKED for the same reason -- no genuinely clean machine
exists. Nothing new was fabricated to work around this. See `docs/MACOS_SIGNING_VALIDATION.md`
for the related signing blocker (a clean-machine test of an *unsigned* build wouldn't be
representative of what a real beta tester receives anyway, so the two blockers are sequenced:
signing first, then clean-machine validation of the signed artifact).
