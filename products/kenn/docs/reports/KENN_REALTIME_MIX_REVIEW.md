# KENN realtime Mix Review

## What is supported now

KENN Mix Assistant already has a read-only plug-in handoff. The plug-in's
allocation-free realtime core publishes a bounded bus snapshot outside
`processBlock`; the companion validates it, keeps it for a short time, and
passes it to KENN's evidence layer. The snapshot now includes:

- peak and RMS dBFS;
- stereo correlation and width;
- crest, transient and recent clipping indicators; and
- broad low/mid/high relative energy estimates; and
- a bounded fixed-band spectral snapshot, including a band centred near 315 Hz,
  compared with a measured 1 kHz-anchored `-3 dB/octave` pink-noise-style
  baseline.

This is enough for advice such as “the latest bus peak is -1.0 dBFS; check
headroom” or “the latest correlation is negative; audition this section in
mono.” The spectral handoff can support language such as “the nearest realtime
band centred at 315 Hz is about 5 dB above the pink-noise-style baseline”, but
the values are still uncalibrated bus energy rather than LUFS or true-peak.
This is a broad listening reference, not a universal quality score or EQ
instruction.

The current plug-in snapshot is a bus observation. It does not identify which
track or device caused a bus problem, and it cannot inspect Live routing,
automation, clip content, or individual track audio. The richer read-only
AbletonOSC session snapshot can now carry instantaneous per-track output-meter
readings for a track-specific headroom check, but those readings are not
audio-rate peaks, spectrum, LUFS, true peak, or masking evidence. A full Mix
Review still uses the existing WAV/stem analysis path for audio attribution;
KENN must not solo, mute, or alter tracks automatically just to diagnose them.

The background Mixing Doctor may also flag a `low_end_overlap_candidate` when
two likely low-end tracks are both unmuted and high on their faders. This is a
name/fader-state prompt only, not a masking measurement; it deliberately
points back to Mix Review or a mono audition rather than proposing an EQ or
level change. Measured masking remains confined to the separate multi-stem
analysis path.

Live context also retains a bounded recent window: at most 12 snapshots over
two minutes. The response includes `freshness` (`observed_at_epoch`, age,
expiry, frame count, and an explicit current/stale diagnosis status) and
`live_window` (`insufficient`, `stable`, or `changing`). A snapshot is marked
`current_for_diagnosis` only while it is no more than 15 seconds old; the
30-minute retention TTL exists for bounded history and recovery, not as a
claim that the meters are still current. When at least three snapshots contain spectral data, KENN can
report the median deviation for a band and say that a bus trend is repeatable.
This remains a prioritisation signal; it does not turn bus evidence into
track attribution or authorise an EQ change.

The recommendation bridge promotes validated current bus warnings separately:
limited peak headroom, recent clipping, negative stereo correlation, wide side
energy, and meaningful pink-noise-style band deviation. These are listening
checks only; stale retained context is withheld from current recommendations,
and none can infer a responsible Live track or device.

For consumers that need to refresh a panel without requesting another capture,
`GET /api/plugin-live-review?session_id=<id>` returns the latest validated
review, live context, trend status, and freshness receipt. It is explicitly
read-only (`capture_requested: false`) and advisory-only; a missing or expired
session returns a clear 404 rather than stale data.

The same receipt is available to reasoning clients through the MCP
`live_plugin_review` tool. It preserves the endpoint's `plugin_bus` scope,
freshness, bounded trend, and advisory-only fields, so a planner can inspect
the current bus review without opening a second OSC connection or requesting
new audio capture.

For clients that need recommendations without an uploaded render, the
read-only `realtime_mix_recommendations` tool accepts only the explicit
plug-in session id and returns the current validated listening checks. It
returns no recommendations for stale context and cannot infer a responsible
Live track/device or authorize a mutation.

The colleague-owned UX can consume the same contract through
`GET /api/realtime-mix-recommendations?session_id=<id>`. A missing or expired
session returns 404 with an empty recommendation list; the route never asks
the plug-in to capture new data.

For a read-only side-by-side check, `compare_realtime_mix_review` accepts an
explicit uploaded/rendered `review_id` and plug-in `plugin_session_id`. The
matching HTTP route is
`GET /api/realtime-mix-comparison?review_id=<id>&session_id=<id>`. It compares
sample peak, RMS, and crest factor when both records contain them, while
labelling the live value as current/short-window and the uploaded value as
whole-file. It can also show the two pink-noise-style shape observations as a
directional comparison; fixed-band realtime and whole-file LTAS measurements
are not treated as interchangeable. Missing or stale evidence fails closed,
and the response remains advisory-only with no Live target inference.

The richer MCP `kenn_context` and `kenn_session_intelligence` reads can also
accept an explicit `plugin_session_id`. When supplied, the latest validated
bus frame, pink-noise-style comparison, trend summary, and freshness receipt
are carried into the bounded session context and compact intelligence brief.
This is opt-in so an ordinary context read does not add an unnecessary
round-trip or claim that a plug-in capture exists.

The read-only `realtime_session_review` MCP tool and
`GET /api/realtime-session-review` route provide a single handoff for clients
that need the whole current-session picture. They compose the cached Ableton
session, Mixing Doctor alerts, structural project-health findings, and (when
an explicit `plugin_session_id` is supplied) the validated plug-in bus review.
The sources remain separate in the response: a bus recommendation cannot be
mistaken for a track diagnosis, and an unavailable Live cache returns a
structured fail-closed result rather than a clean bill of health.

When `kenn_session_intelligence` receives both `mix_review_id` and
`plugin_session_id`, its `kenn.session_intelligence.v1` response additionally
contains `realtime_mix_comparison`. This lets the planner and answer layer use
the same scope-labelled comparison without parsing prose or making a second
tool call. Supplying only one ID leaves that field null.

The existing `mix_review_recommendations` MCP response also carries this
comparison when its optional `plugin_session_id` is supplied, alongside the
ranked uploaded-review findings and bounded Mixdown Coach checks. This keeps
the uploaded and realtime evidence streams visibly separate while making the
combined review available through the established recommendation path.

## Natural-language session scan

The normal KENN chat route also recognises a request such as “scan the current
Ableton session for advice” and routes it to the same unified report. This is
an orchestration convenience only: it does not poll Live, request plug-in
capture, apply changes, or turn a cached meter into a claim about clipping,
masking, phase, LUFS, true peak, or full spectral balance. An explicit
`plugin_session_id` can still be supplied by an integration when a validated
plug-in bus snapshot should be included.

The HTTP and MCP unified-review surfaces also accept an optional bounded
`focus` value. For example,
`GET /api/realtime-session-review?focus=headroom%20and%20gain%20staging` adds
the structured `knowledge_guidance` list using the same source-diverse
retrieval path as chat. Omitting `focus` performs no knowledge retrieval.

When the scan is made through normal chat, KENN also adds a bounded
`knowledge_guidance` list to the structured report and renders a few
“Knowledge-grounded next checks.” These items are retrieved from the indexed
official Ableton manual, reviewed producer transcripts, or curated KENN notes,
with an evidence class and short excerpt. They are advisory references only;
they do not supply missing measurements or authorise a Live mutation.

The read-only `ask_audio_engineering_question` MCP tool and
`POST /api/knowledge/ask` route accept the same optional `mix_review_id` and
`plugin_session_id` pair. They add typed uploaded-review and plugin evidence to
the deterministic answer context and return `realtime_mix_comparison` when
both records are available. An unavailable optional review is ignored rather
than making a general knowledge answer fail.

The main conversational `POST /api/ask` route accepts the same explicit IDs.
It adds the validated evidence turns to both streaming and non-streaming
answers and attaches the comparison to returned metadata. This makes the
capability available to the normal chat surface without creating a second
mutation or capture path.

The comparison is also encoded as a separate freshness-aware evidence packet
for deterministic answer generation. Explicit realtime/reference questions
can therefore state the measured live-versus-uploaded peak, RMS, and
pink-shape deltas directly, while retaining the distinction between a
current/recent plugin-bus window and a whole-file review. This packet is
derived evidence, not a new measurement source; stale realtime context is
still excluded from current diagnosis, and no comparison can identify a
responsible track/device or authorise an EQ move.

## Evidence and advice policy

The Live 12 manual is indexed as `official_ableton_manual` after explicit local
opt-in. Questions asking what Ableton documents should prefer matching manual
chunks and abstain when no substantive manual match exists.

Reviewed producer notes that carry transcript metadata are indexed as
`youtube_transcript`. They are useful for musical suggestions—arrangement,
sound design, kick/bass separation, stereo placement and creative reverb—but
are labelled advisory and never presented as official Ableton behaviour.
The answer layer should combine them with current session measurements and
state the distinction when it matters.

## GPU index workflow

The laptop can build the manual/BM25 index with:

```bash
KENN_SKIP_EMBEDDINGS=1 ./ableton build --include-local-manuals
```

The semantic embedding pass can be run on a CUDA-enabled host using the
versioned `scripts/build_gpu_onnx_embeddings.py` helper and KENN's local
MiniLM ONNX model. The returned matrix must match the exact chunk file before
being promoted. No server restart is required for index promotion; already
running processes may retain their previously loaded cache until their normal
next reload.

## Next engineering slice

Complete real-session qualification after the current soak and a normal
companion reload. Exercise fresh handoffs while Live is playing and stopped,
verify the expiry/freshness receipt, and validate the new side-by-side
comparison against a real uploaded render or reference. A future selected-track scope still requires
a separate read-only per-track capture; it must not be simulated by soloing,
muting, or changing the arrangement.
