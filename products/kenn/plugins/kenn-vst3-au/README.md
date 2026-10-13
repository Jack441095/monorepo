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
`http://127.0.0.1:8090`) and a **Conversation ID** matching the KENN conversation you
want to ground. Conversation IDs persist in the set and may be shared by paired
inserts. Each processor also has a separate generated insert ID, scoped to its
lifetime, so two inserts in one conversation cannot overwrite each other's audio.
Reopened or duplicated processors require fresh bindings. The
plug-in intentionally accepts only `localhost` and `127.0.0.1` HTTP addresses.
Use **Test** to check `/api/health` before sending a review or stems. **Publish
live context** is opt-in and posts changed compact feature frames at most twice
per second, including with the editor closed. Stopped audio does not resend the
same publication. It never sends raw audio and runs outside the audio callback.

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

The **Ask KENN** panel sends the question, conversation ID and separate insert
ID to the local companion. KENN therefore receives the retained bus context alongside
its normal Audio Too knowledge base; it does not need raw audio or a generic
chat-only prompt to answer mix questions.

An explicit question such as **“Analyse the kick”** or **“What should I change
on this channel?”** now carries a fresh feature snapshot with the Ask request.
The companion matches a host-reported name to one track in a fresh AbletonOSC
snapshot; an ambiguous name, another track's insert, stopped audio, or disabled
analysis prompts a clarification. API callers use the conversation as `session_id` and the measured insert as
`plugin_session_id`. Native Ask supplies both. The embedded web URL carries both
IDs, but frontend selection of paired sources is not qualified by these native
checks. Parameter API callers may use the conversation for a single insert;
multiple inserts require an explicit insert ID. An ambiguous conversation
cannot queue or consume another instance's parameter updates. The response separates `measured`, `session`,
`interpretations`, `recommendations`, and `unavailable` fields under
`kenn.live_track_analysis.v1`. This focused analysis route uses deterministic
interpretation; general engineering questions retain the existing knowledge/model
path.

The audio callback passes audio through with zero declared latency. It copies
only its own input into a preallocated single-producer/single-consumer queue;
there is no callback-side allocation, mutex, worker wake-up, network request or
model call. One low-priority worker serves all inserts, independent of editors.
The queue holds up to 16,384 stereo frames in 145,976 bytes per insert (including
packet metadata). A full queue drops an entire measurement block without waiting
for playback. Oversized host blocks use the same drop path.

Peak, RMS, crest, correlation, width, near-full-scale frame count and 13 filter
bands are published together from contiguous **100 ms** windows under
`kenn.continuous_window.v1`. The payload includes a sequence, source generation,
local sample bounds, duration, validity and cumulative dropped/invalid sample
counts. Audio age refers to capture, including worker backlog; a gap, source
change or disabled analysis retires evidence until a full window recovers.
Continuous frames older than **1 second** cannot ground diagnosis. Legacy
handoffs retain their explicitly labelled per-block measurements and 15 second
age limit. HTTP deliveries retain at most 12 updates over 120 seconds; they
remain sparse history, not a continuous retained recording.

Opt-in **Publish live context** uses one shared low-priority HTTP publisher per
loaded plug-in binary. Every 500 ms it groups changed insert frames by companion
endpoint into `kenn.plugin_handoff_batch.v1` at `/api/plugin-handoff-batch`.
Each batch contains at most 64 distinct insert IDs and stays under the existing
1 MiB request cap; compact JSON preserves FFT precision and all six history
windows. The companion validates every frame before replacing any evidence,
anchors siblings to one receipt time, and returns compact freshness
acknowledgements. Malformed batches change no cached inserts; a stale frame
is refused independently of valid siblings. Feature uploads have a separate
120 requests/minute budget; Live controls retain their 60 requests/minute limit
and existing endpoint permissions. No model call or Live write happens here.
Stopped windows are not resent. Missing companions let evidence expire while
playback continues. The publisher joins after the last insert is destroyed;
HTTP waits never hold processor pointers. Responses are capped at 64 KiB and
local requests use a 1,200 ms timeout with no redirects. Continuous publication
requires the companion's batch endpoint; manual handoff retains the older
single-frame endpoint.
On macOS each publisher tick drains its own autorelease pool; temporary feature
and HTTP objects cannot accumulate until the shared thread shuts down.

Native batches and individual snapshots include `exported_at_epoch`, sampled in
epoch seconds before feature collection. This also covers explicit Ask, file
export and single uploads. The companion uses that shared local clock with each
window's measured age, so collection, serialization, HTTP stalls and validation
count toward the one-second diagnosis lifetime. Receipt time still controls
cache retention. Non-finite/negative clocks and clocks more than 50 ms ahead of
receipt reject the frame or whole batch; smaller future offsets clamp to receipt and
cannot extend freshness. Older clients without this field retain receipt-relative
ages and do not qualify transport-delay freshness. When both batch and frame clocks
are present the older anchor wins.

The transient ratio is fast-envelope excess over sustain: fast attack/release
1/15 ms and slow attack/release 50/100 ms. It is not compressor gain reduction.
The spectrum averages separate channel power so opposite-phase stereo retains
energy. The 13 legacy bands remain uncalibrated filter-bank estimates. Separate
**2,048- and 8,192-sample FFTs** use cached radix-2 plans and periodic Hann
windows, entirely on the worker. The short FFT updates at 10 Hz, the long FFT
at 5 Hz. `kenn.fft_spectra.v1` carries 32 logarithmic group powers from 20 Hz
to 20 kHz, total mean-square power including DC/Nyquist, strongest non-DC bin,
bin spacing and each transform's own sample bounds. Power uses separate stereo
channels and Hann-power normalization; it is not LUFS, true peak or a resonance
diagnosis. At 48 kHz, bin spacing is 23.4375 Hz / 5.859375 Hz, with durations
42.67 ms / 170.67 ms. Partial rings and gaps supply no completed spectrum.

For an explicit association, say **“bind this insert to track 1”** in native Ask
or the matching web conversation; **“unbind this insert”** clears it. Binding
requires fresh continuous audio and Live topology, lasts five minutes, and
rechecks names/order, source generation and sample-counter resets. Conflicting
host names are refused. A declaration alone cannot unlock fader control where
the host name is missing or duplicated. AbletonOSC supplies no durable project
ID: re-bind after switching sets, including two sets with identical topology.

For **“Is the bass masking the kick?”**, use the same Conversation ID in both
native inserts, play both, enable **Publish live context**, and bind each to its
actual track number. Each publisher includes at most six feature windows
(600 ms) to bridge different publishing phases. The companion requires one
current explicit binding per source, the same sample rate and host measurement
interval, identical long-FFT capture intervals, capture times within 50 ms and
FFT capture ages no greater than 1 second. It reports measured band-power shape
similarity across whole groups spanning 20–267 Hz and a manual listening
comparison; this does not prove audible masking. Missing clocks, warm-up,
seeks/loops, stale audio, duplicate bindings or other owners abstain. No paired
comparison creates a control card.

Host timing is read only inside the callback from JUCE's optional playing
transport sample clock. `kenn.host_timeline.v1` carries signed host sample
bounds and a per-insert transport epoch; missing or stopped clocks remain
unknown. Windows align to a 100 ms host-sample grid. Seeks, loops and clock loss
retire evidence and clear FFT/history without expiring the track association.
Epoch counters belong to each insert and are not compared as shared project IDs.
Host-provided timing aligns captured buffers; delay compensation and durable
project identity remain producer-supervised host qualification work.

For less than 3 dB of measured sample headroom, Suggest/Assist can offer one
fader-reduction audition through the existing LiveActionService. It shows the
before/after dB, mix-balance trade-off, and explicit confirmation card; Apply
rechecks identity/value, verifies readback, and supports guarded Undo. A
downstream fader cannot repair upstream distortion or guarantee master headroom.
Ask mode remains read-only. Native Ask displays the advice and a specific command
to enter in **Control Live**, where the existing confirmation panel applies it.
Master/unknown inserts and unavailable controls receive manual advice only.

Each KENN insert receives only its own input. Paired spectral measurements
require two explicitly associated inserts; they cannot establish sidechain
routing or compressor operation. Sidechain questions retain unknown confidence
and ask for the trigger source or a controlled, matched bypass comparison. Third-party EQ/compression and upstream gain changes remain
manual in this analysis slice. No raw audio upload or new writer is added.

The name callback is the implemented JUCE 8.0.2
[`updateTrackProperties` API](https://github.com/juce-framework/JUCE/blob/8.0.2/modules/juce_audio_processors/processors/juce_AudioProcessor.h):
hosts decide whether and when to supply a name, on the message thread. It is a
matching hint, not a stable track ID, routing graph, or cross-track audio API.
[`AbletonOSC's documented API`](https://github.com/ideoforms/AbletonOSC)
exposes session/mixer information and selected device parameters; this slice
uses only fresh track names/mixer values and the existing supported fader path.

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

For offline verification against a configured build, run:

```sh
KENN_TEST_OFFLINE_ONLY=1 ctest --test-dir build/plugins/kenn-vst3-au \
  -E 'KENN.ServerIntegration' --output-on-failure
```

`TestContinuousAnalysis` checks exact windows, overflow/invalid input recovery,
phase energy, FFT power against independent time-domain energy, different insert
start times, signed preroll, seek/loop/clock loss, callback C++ allocations,
pass-through and editor-closed operation.
`TestRealtimePerformance` emits mean/p99/max callback timings, capture age, drops,
worker elapsed work and fixed queue storage for 60 wall-paced rate/buffer/insert
combinations. Its publishers are disabled; actual host CPU/RSS and companion contention
remain supervised soak work. The excluded server check expects an external
companion; backend `test_live_track_analysis.py` instead starts an isolated
FakeLive HTTP server. Set `KENN_NATIVE_COMMAND_TEST_BINARY` to the built
`TestCommandIntegration` executable when running that test to exercise the
native Ask/bind/unbind client and a two-insert, host-timed FFT comparison.
For the isolated active-publisher profile, set `KENN_NATIVE_PUBLISH_TEST_BINARY`
to `TestRealtimePerformance` and run only
`test_live_track_analysis.py::test_native_feature_publishers_remain_fresh_with_64_inserts`
from `apps/backend` with `KENN_LIVE_BACKEND=fake KENN_LLM_ENABLED=0`.
That fixture supplies its own loopback server. Its `short` case tests 1/8/32/64
inserts at 48 kHz / 128 samples for three seconds each. Its `delayed` case holds
the first 64-insert request for 1.05 seconds and requires stale evidence followed
by fresh recovery, without callback drops. The `memory` case profiles 64 inserts
for 15 seconds. Set `KENN_NATIVE_PUBLISH_SUSTAINED=1`
to enable the `sustained` case: 64 inserts for 65 seconds, crossing a full
60-second rate bucket with fresh acknowledgements and no delivery gap of one
second or longer. Request/serialization time adds to each 500 ms polling wait;
two batches/second is an upper bound, not a guaranteed delivery frequency.
All cases record HTTP sizes, freshness, handler latency, child process CPU/RSS
and companion CPU. Select one case with `-k short`, `-k delayed`, `-k memory` or `-k sustained`
and run it in a separate pytest process so earlier child RSS peaks do not distort
the measurement. Native output also records current macOS private footprint and
live allocator bytes after a five-second warm-up. The retained-memory gate allows
the timing vector's newly touched pages plus 8 MiB for a bounded request's
temporary copies. Peak RSS is reported separately; it includes OS/allocator
high-water marks and the test's timing vector. Other platforms need their own
current-footprint profiler to qualify this memory gate.
Synthetic input and FakeLive do not qualify Ableton timing or delay compensation.

Optional loudness/true-peak reuse can be profiled entirely offline from the
`products/kenn` directory with the already-built optional native DSP module:

```sh
KENN_LIVE_BACKEND=fake KENN_LLM_ENABLED=0 apps/backend/.venv/bin/python \
  tooling/scripts/profile_live_loudness.py --repeats 20 \
  --json-out /tmp/kenn-live-loudness-reuse.json
```

The tool measures serial 1/8/32/64-insert batches at 44.1/48/96 kHz with
400 ms/3-second synthetic clips. It records process CPU, wall time, binary and
fixture hashes, and numerical agreement with the existing Python clip algorithms.
Its 10 Hz CPU demand is an extrapolation; it excludes capture, FFT, publication
and model contention. The native call also performs LRA work, whereas the Python
timing covers only integrated LUFS and peak; these timings are not an equal-work
speed comparison. The clip API resets weighting/FIR state and returns gated
integrated LUFS, so its results cannot be relabelled as live momentary/short-term
loudness. Regression probes demonstrate the gating and restart differences.
The tool leaves runtime flags unchanged and makes no EBU/ITU conformance claim.

The streaming candidate has a separate offline target, `TestStreamingMeter`.
It keeps K-weighting/FIR history and bounded 100 ms energy bins for ungated
400 ms/3-second readings. Normal plug-in calls leave it disabled, and it adds
no published LUFS/dBTP fields. Its native checks cover warm-up, silence, phase,
source/seek/overflow retirement and allocation-free processing. To reproduce
the generated-signal reference comparisons and 36-cell cost profile:

```sh
KENN_LIVE_BACKEND=fake KENN_LLM_ENABLED=0 apps/backend/.venv/bin/python \
  tooling/scripts/profile_streaming_meter.py \
  --binary /tmp/kenn-live-analysis-arm64/TestStreamingMeter --repeats 20 \
  --json-out /tmp/kenn-streaming-meter.json
```

Use the path to your configured Release executable. The profile compares each
rolling window with full continuous SciPy filtering and the Annex 2 FIR; it uses
generated descriptions of Tech 3341 cases 1/2 and 15–19. It does not download EBU
audio or run the complete conformance suite. The 100 ms peak intervals describe
FIR output delayed by 5.875 input frames. Fixed 4x interpolation at 44.1 kHz
produces 176.4 kHz, below Annex 2's 192 kHz guideline, and has frequency-dependent
under-read. These limits must be addressed before promoting live dBTP claims.
Timing includes capture and the existing FFT/filterbank worker drained
synchronously; thread scheduling, HTTP, the model and Ableton remain outside
the measurement. Set `KENN_STREAMING_METER_TEST_BINARY` to the executable for
the optional Python native-reference regressions.
Current results and remaining gates live in
[KENN_PLAN.md](../../KENN_PLAN.md).

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

On macOS, pass `-DKENN_BUILD_UNIVERSAL=ON` to produce universal `arm64` and
`x86_64` VST3/AU bundles; the default developer build targets the host
architecture. On Windows, the same CMake project configures the VST3 target
only because Audio Unit is a macOS format. Building AU requires full Xcode
(not Command Line Tools alone).
Local development uses an ad-hoc or unsigned bundle depending on the JUCE/Xcode
toolchain; distributing outside this machine still requires your Apple
Developer ID signing and notarization workflow.

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
