# KENN Mix Assistant

`KENN Mix Assistant` is a transparent mono/stereo audio-effect plug-in, built
from one JUCE target for VST3 and Audio Unit. It performs no automatic
processing in `processBlock`.

It publishes a conservative Mix Review snapshot: peak dBFS, recent RMS dBFS, stereo correlation and width, plus fixed frequency-band energy estimates for a broad pink-noise-style listening reference. **These are bus metrics, not LUFS, true-peak, track attribution, or a full mix diagnosis.** The UI's handoff button POSTs `kenn.plugin_handoff.v1` to the optional local KENN Companion. If KENN is unavailable, it saves the JSON under the operating system's user application-data folder.

## Offline mode

The plug-in's native meters and **Local Mix Check** work without the KENN
Companion. They report the current bus's peak, RMS, correlation, stereo width,
crest, transient ratio, and clipping/headroom/polarity/silence threshold
findings directly from the C++ real-time state. Audio is not sent anywhere.

The optional local companion provides chat, retrieved knowledge, Mix Review
handoff, confirmation-gated Live commands, guarded proposals, and AutoMix.
Those features are clearly reported as unavailable when the companion is
stopped; offline mode does not claim to replace calibrated LUFS/true-peak or
full-file spectral analysis.

## Using the companion safely

Start KENN from the repository root:

```sh
./tooling/scripts/start_server.sh
```

In the plug-in, set the local companion address (the default is
`http://127.0.0.1:8090`) and a Session ID matching the KENN conversation you
want to ground. Each new plug-in instance starts with its own generated,
project-persisted session ID, preventing accidental cross-bus context. The
plug-in intentionally accepts only `localhost` and `127.0.0.1` HTTP addresses.
Use **Test** to check `/api/health` before sending a review or stems. **Publish
live context** is opt-in and, while the editor is open, posts a compact feature
frame every eight seconds. It never sends raw audio and it runs outside the
audio callback.

Modes are persisted in the DAW project and included in every handoff:

- **Ask** returns measured observations only; it never returns actions.
- **Suggest** can return a scoped, explainable proposal but cannot apply it.
- **Assist** permits a KENN proposal to be applied only after an explicit
  confirmation, with a one-click undo for the KENN target setting.
- **Auto** is reserved for opt-in workflows; the current target change still
  requires confirmation, and AutoMix always requires manually selected stems.

Confirmed target changes and their undos are retained as a bounded, timestamped
action history in the plug-in's DAW state (up to 50 entries). This makes the
current safe action both reversible through the host gesture and auditable when
the project is reopened.

The **Ask KENN** panel sends the question and this instance's Session ID to the
local companion. KENN therefore receives the retained bus context alongside
its normal Audio Too knowledge base; it does not need raw audio or a generic
chat-only prompt to answer mix questions.

The **Control Live** button sends the text in the same command box to the
confirmation-gated Ableton command endpoint. It can inspect tracks/devices and
prepare changes to supported track controls or an explicitly inspected device
parameter. KENN also supports a single, explicitly identified existing EQ
Eight band, for example “reduce amplitude by 3 dB at 200 Hz on track 4 band
1B”. KENN shows the exact track/device, band, frequency, before value, and
after value in the **Live proposal** panel; nothing changes until **Confirm
Live Proposal** is pressed. **Cancel Proposal** discards the pending plan. A
confirmed change is re-read from Live before the plug-in reports success, and
**Undo Last Live Change** creates a fresh, separately confirmed reverse
proposal using the verified receipt.
Device insertion is now limited to an append-only, allow-listed `EQ Eight`
proposal on a track without an existing EQ Eight. It shows the before/after
device order and remains confirmation-gated; duplicate, stale, or unqualified
targets are refused. The command path also supports an explicit compound EQ
edit such as “retune EQ Eight band 1A to 300 Hz and reduce gain by 3 dB on
track 4”; the proposal shows both parameter changes and confirmation is
required before either write. Ambiguous frequency-only requests remain
clarification states.

AutoMix is intentionally a handoff rather than a live insert effect. Select up to 32 WAV, AIFF, or FLAC stems in the plug-in and it uploads them to KENN's existing quality-gated offline renderer. The plug-in accepts up to 490 MB of selected stems, leaving multipart overhead below the companion's 500 MB request limit. The editor shows the queued job identifier; do not close KENN while the render is running.
When a completed job is detected, **Copy AutoMix Download Link** puts its local
WAV delivery URL on the clipboard so it can be imported into any DAW.

Build the native plug-in from the repository root:

```sh
cmake --build build/plugins/kenn-vst3-au --config Release --parallel 2
```

For the repeatable local build-and-install flow, use:

```sh
./tooling/scripts/rebuild_vst3.sh
```

After every rebuild, fully quit and reopen Ableton Live before testing. Live
can retain the previously loaded plug-in binary for the lifetime of the
process; closing and reopening only the plug-in editor is not a reliable
reload. Reopen the disposable test set, select the KENN device, and verify the
editor shows the **Show Live Controls**, **Live proposal**, **Confirm Live
Proposal**, **Cancel Proposal**, and **Undo Last Live Change** controls before
recording a test result. **Show Live Controls** is read-only: it lists exact
track/device/parameter names and inspected ranges from the current Ableton
session, while **Control Live** remains the only route that can create a
mutation proposal.

On macOS, the default CMake configuration produces universal `arm64` and
`x86_64` VST3/AU bundles. Building AU requires full Xcode (not Command Line
Tools alone). Local development uses an ad-hoc signature; distributing outside
this machine still requires your Apple Developer ID signing and notarization
workflow.

The repository's release packager makes that workflow explicit and fail-closed:

```sh
KENN_CODESIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)" \
KENN_NOTARY_PROFILE="kenn-notary" \
./tooling/scripts/package_macos_plugins.sh --preflight

KENN_CODESIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)" \
KENN_NOTARY_PROFILE="kenn-notary" \
./tooling/scripts/package_macos_plugins.sh
```

The script refuses to create an ad-hoc or unnotarized beta archive. It signs,
validates, notarizes, staples, Gatekeeper-checks, and checksums both formats.
Notary credentials must already be stored in a `notarytool` keychain profile;
they are never passed directly on the command line. See
`docs/KENN_PLUGIN_HOST_VALIDATION_2026-09-07.md` for the latest host evidence.
