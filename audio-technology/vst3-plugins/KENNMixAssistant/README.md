# KENN Mix Assistant

`KENN Mix Assistant` is a transparent mono/stereo audio-effect plug-in, built
from one JUCE target for VST3 and Audio Unit. It performs no automatic
processing in `processBlock`.

It publishes a conservative Mix Review snapshot: peak dBFS, recent RMS dBFS, stereo correlation and width. **These are bus metrics, not LUFS or a full mix diagnosis.** The UI's handoff button POSTs `kenn.plugin_handoff.v1` to the local KENN server. If KENN is unavailable, it saves the JSON under the operating system's user application-data folder.

## Using the companion safely

Start KENN with the project virtual environment:

```sh
.venv/bin/python studio/kenn/kenn/server.py
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

AutoMix is intentionally a handoff rather than a live insert effect. Select up to 32 WAV, AIFF, or FLAC stems in the plug-in and it uploads them to KENN's existing quality-gated offline renderer. The plug-in accepts up to 490 MB of selected stems, leaving multipart overhead below the companion's 500 MB request limit. The editor shows the queued job identifier; do not close KENN while the render is running.
When a completed job is detected, **Copy AutoMix Download Link** puts its local
WAV delivery URL on the clipboard so it can be imported into any DAW.

Build VST3 on macOS/Linux:

```sh
cmake -S studio/vst3_plugins/KENNMixAssistant -B build/kenn-mix-assistant
cmake --build build/kenn-mix-assistant --config Release
```

On macOS, the default CMake configuration produces universal `arm64` and
`x86_64` VST3/AU bundles. Building AU requires full Xcode (not Command Line
Tools alone). Local development uses an ad-hoc signature; distributing outside
this machine still requires your Apple Developer ID signing and notarization
workflow.
