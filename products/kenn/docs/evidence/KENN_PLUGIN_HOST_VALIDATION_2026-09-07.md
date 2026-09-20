# KENN plug-in host validation — 2026-09-07

## Decision

The installed KENN Mix Assistant 0.1.0 Audio Unit and VST3 pass independent
host/API validation and a real Ableton Live 12.4.5 discovery/load/remove check
on this machine. Both devices appeared active in Live's Device Detail and
Live's own log recorded successful creation. They are **not yet distributable
builds**: both bundles are ad-hoc signed, Gatekeeper rejects them, and no
Developer ID code-signing identity is installed on this Mac.

## Environment and artifact identity

- Host: Apple M3 MacBook Air, arm64.
- Current OS: macOS 26.6.2 (25G83).
- Installed bundle version: 0.1.0.
- Both installed bundles are universal `arm64 + x86_64` binaries.
- AU executable SHA-256:
  `99efcd36c67021be5a1da5af873b86f1328658b358fcaca150a84ad753b2b68a`.
- VST3 executable SHA-256:
  `7fd5ea79ce6d7f6a3a8c8109b17fd97daa83a862694fb7177abdbb41e625f7a3`.
- Signatures: ad-hoc; no Team ID.

The current OS is newer than the only real-Live-qualified support-matrix entry
(macOS 26.5.2). Host-format validation on 26.6.2 is evidence for the binaries,
not an expansion of the real-Live support matrix.

## Ableton Live host-load validation

At 15:52–15:54 BST, Ableton Live 12 Suite 12.4.5 discovered two `KENN Mix
Assistant` results under its AUv2 and VST3 formats. The test used empty tracks
in an unsaved `Untitled` set with transport stopped at 44.1 kHz.

- The first result was inserted on `3-Audio`. Live displayed an active KENN
  device and logged `VST3: plugin processor successfully loaded: Shenrendao AI
  'KENN Mix Assistant' v0.1.0`, followed by a five-parameter count and
  `VST3: Created: KENN Mix Assistant`.
- The device was removed through Live's device menu. The second result was then
  inserted on `4-Audio`; Live displayed an active KENN device and logged
  `Audio Unit v2: Created: KENN Mix Assistant`.
- The AU device was removed. A fresh read-only AbletonOSC snapshot then showed
  all four tracks with empty device lists, 120 BPM, stopped transport, and the
  selected `4-Audio` track. The set was not saved.

The current host-load check establishes discovery and clean instantiation in
Live on macOS 26.6.2. It does not establish signal-processing correctness,
long-session stability, downloaded-distribution acceptance, or expand the
qualified support matrix by itself.

The preflight also found an orphaned earlier KENN process holding UDP reply
port 11001. The newly started companion correctly reported AbletonOSC offline
instead of a false connection. After the exact stale process was terminated,
the running companion acquired the port and the same read-only probe passed.
Only one KENN companion may own AbletonOSC's reply port at a time.

## Audio Unit validation

Command:

```bash
auval -v aufx KnMa AECO
```

Result: `AU VALIDATION SUCCEEDED`.

The validator passed component discovery, cold/warm opening, required and
recommended properties, Cocoa UI creation, class state, host callbacks,
parameter persistence, mono/stereo layouts, connection semantics, parameter
scheduling, MIDI handling, and render tests from 11.025 kHz through 192 kHz.

## VST3 validation

The installed VST3 passed pluginval at normal strictness with UI tests enabled,
then again at strictness 10 with deterministic seed `120907` and headless GUI
tests disabled. The strictness-10 command tested 44.1, 48, 96, and 192 kHz at
block sizes 16, 64, 128, 512, 1024, and 4096.

Result: `SUCCESS` at both strictness levels.

Covered checks included discovery, cold/warm opening, audio processing,
non-releasing processing, state restoration, automation, parameter accessors,
parameter thread safety, bus layouts, and parameter fuzzing. pluginval's
optional Steinberg VST3 validator subtest was not run because no validator path
was configured; pluginval's own VST3 tests did run and pass.

## Distribution gate

Commands:

```bash
spctl -a -vv -t install "$HOME/Library/Audio/Plug-Ins/VST3/KENN Mix Assistant.vst3"
spctl -a -vv -t install "$HOME/Library/Audio/Plug-Ins/Components/KENN Mix Assistant.component"
security find-identity -v -p codesigning
```

Both Gatekeeper assessments returned exit code 3 (`rejected`), and the keychain
reported zero valid code-signing identities. This is expected for the current
local ad-hoc builds but blocks a normal downloaded beta distribution.

`scripts/package_macos_plugins.sh` now provides the release path. It fails
closed unless given an installed Developer ID Application identity and a valid
`notarytool` keychain profile. A successful run signs both bundles with the
hardened runtime, validates them, notarizes the archive, staples both bundles,
rechecks Gatekeeper acceptance, and emits a SHA-256 checksum. It never accepts
notary credentials directly on the command line.

Safe preflight:

```bash
KENN_CODESIGN_IDENTITY="Developer ID Application: ..." \
KENN_NOTARY_PROFILE="kenn-notary" \
./scripts/package_macos_plugins.sh --preflight
```

## Remaining release gates

- Produce a Developer ID-signed, notarized, stapled, Gatekeeper-accepted
  archive and checksum.
- Complete the two independent human reviews and bound adjudication.
- Repeat host and stability checks on any additional Live/OS combination
  before adding that configuration to the support matrix.
