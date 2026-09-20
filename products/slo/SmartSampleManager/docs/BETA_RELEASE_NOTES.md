# Smart Sample Manager 1.0.0-beta.1 -- Release Notes

**Not yet cut.** This document is drafted ahead of the actual release candidate so its shape is
ready the moment the real blockers (below) clear -- it is not itself evidence that beta.1 exists
or has been distributed. See `docs/PRIVATE_BETA_RC.md` for the gate status.

## Supported systems (once signed)

macOS only for this beta. Windows is out of scope for the initial private beta (Section 77) --
not because it's inferior, but because all Phase 1-5 work has run exclusively on macOS/Apple
Silicon, and expanding to Windows before macOS beta ships would delay the thing that's actually
close to ready.

## Tested DAWs

**None yet, honestly.** Section 41's host-validation matrix (Ableton Live, Logic Pro as
priority; Reaper/Bitwig/Studio One/Cubase after) has not been run against a signed build, because
no signed build exists yet (`docs/MACOS_SIGNING_VALIDATION.md`). Only list a host here once it's
actually been tested -- per Section 42's "do not overclaim." This section will be filled in as
part of the clean-machine test flow (`docs/CLEAN_MACHINE_VALIDATION.md`'s Section 38 sequence),
not before.

## What's actually verified so far (Phase 1-5.5, local development builds)

- Realtime-safety audit passed (no audio-thread allocation/file I/O)
- Duplicate detection, embedding quality, find-similar, prune-missing, path-traversal
  containment, malformed-audio resilience, multi-instance concurrent cache access, async
  sort/cancel, taxonomy, XMP metadata read/write, TagLib integration -- 12/12 automated tests
  passing, zero memory leaks (`leaks --atExit`), reconfirmed this phase
- Dependency bundling (TagLib/ONNX Runtime/libsodium **and their full transitive Homebrew
  dependency graph** -- Phase 5.5 found and fixed a real gap where ONNX Runtime's own ~85
  abseil/protobuf/re2 dependencies were never bundled, only the top-level libs) --
  `scripts/check_homebrew_dependencies.py` now passes with zero forbidden paths across all
  three formats. Still not clean-machine verified (that requires real hardware, not just a
  dependency-path scan).
- Full commercial platform (auth, licensing, commerce sandbox, downloads, admin) -- 11/11
  automated E2E tests passing (9 original + 2 concurrency tests added Phase 5.5, which found and
  fixed two real race conditions: activation-limit over-allocation and duplicate webhook
  double-processing under concurrent load)
- NITE DSP identity applied (`docs/FINAL_PRODUCT_IDENTITY.md`) -- `COMPANY_NAME "NITE DSP"`,
  `BUNDLE_ID com.nitedsp.smartsamplemanager`, `PLUGIN_MANUFACTURER_CODE NDSP`

## Known issues (Section 63 -- transparency, not hiding limitations)

- No macOS code signing or notarization yet -- any build produced today would trigger Gatekeeper
  warnings on a machine that isn't this development machine.
- No real clean-machine validation performed -- dependency bundling is evidence, not proof, that
  the plugin runs without Homebrew installed. `docs/CLEAN_MACHINE_TEST_PROCEDURE.md` and
  `scripts/clean_machine_acceptance.py` (Phase 5.5) are ready for the moment a clean machine
  exists.
- No DAW compatibility testing performed against a signed build -- see
  `docs/DAW_VALIDATION_MATRIX.md`, currently all rows "NOT TESTED."
- Windows: not supported, not planned for this beta.
- No real domain or company email exists yet (Phase 5.5 confirmed via repo-wide search --
  `docs/DOMAIN_CONFIGURATION.md`, `docs/EMAIL_CONFIGURATION.md`).
- Real Paddle commerce, real hosted staging, real email delivery: all still local-only/simulated
  (`docs/PADDLE_SANDBOX_VALIDATION.md`, `docs/HOSTED_STAGING_DEPLOYMENT.md`,
  `docs/EMAIL_DOMAIN_CONFIGURATION.md`).

## Feedback

Once a real beta exists, feedback should route through a single dedicated support email
(`docs/HUMAN_COMMERCIAL_REQUIREMENTS.md`'s "Support email address" item) -- not yet available,
since no domain/email account is owned. No community platform is planned for this beta
(Section 64's "avoid an elaborate community platform").
