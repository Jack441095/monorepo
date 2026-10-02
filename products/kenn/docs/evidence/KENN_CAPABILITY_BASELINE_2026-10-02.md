# KENN capability baseline — 2 October 2026

KENN is a functioning local development build with useful assistant features. It
still needs reliability work and qualification before it can be considered a
complete Ableton coproducer.

This saves the current-status discussion as dated evidence. Committed source at
capture: `ba4011b301b786f0eb7d1268d1bc33d2fa60669b`. Concurrent uncommitted
changes are not included in the verified capability claims. This is a source and
recorded-evidence snapshot, not a fresh model benchmark or real-Live qualification.
[KENN_PLAN.md](../../KENN_PLAN.md) remains the sole roadmap and work queue.

## Local model plan

The current plan uses **Qwen3 8B for chat** (`kenn-brain-qwen3-8b`) and **Qwen3 4B
for planning**, with local inference. The target machine is Apple M3 with 16 GB
unified memory, running alongside Ableton Live. This model choice does not prove
that both models fit resident together or meet the response-time targets; memory,
model switching and delivery timing still need measurement.

## Implemented capabilities and limits

Implemented means a capability exists in the inspected software, with the evidence
boundaries stated below. It does not mean every interface or current build has
passed supervised real-Live qualification.

| Area | What it can do now | Current limits |
| --- | --- | --- |
| Conversation | Answer audio-engineering and Ableton questions using retrieved knowledge; retain scoped context and handle some follow-ups, corrections and ambiguous track choices. | Broad conversational quality, five-turn reliability and response times on M3/16 GB still need qualification. |
| Live inspection | Read tracks, devices, exposed parameters and selected session/mixer information. | It cannot inspect every aspect of a set or infer musical intent from session metadata alone. |
| Live commands | Prepare supported changes to volume, pan, mute, solo, arm, track names, track creation, playback, tempo, time signature, sends and selected clip/scene operations. Established paths support confirmation, readback and Undo. | Some newer extension paths lack complete transport support or incorrectly report verification. Their reliability is not established. |
| Devices | Attempt raw-value changes on exposed parameters of existing top-level devices on regular tracks; insert 10 allowlisted effects; use display-unit mappings across nine devices. | It cannot control the entire Live 12 library. Nested rack devices and general return/master device writes are incomplete. Many human-unit conversions remain unsupported. |
| Mix analysis | Analyse uploaded WAVs/stems, compare references and use fresh plug-in bus measurements for headroom, clipping, stereo and spectral observations. | A bus measurement cannot identify the responsible track. Musical usefulness and loudness/true-peak accuracy still need qualification. |
| Memory | Explicitly save, inspect, update, forget and restore scoped preferences, including preference history. | Human usability and complete isolation across every route/project transition remain open. |
| MIDI ideas | Generate basic chord progressions, basslines and drum patterns, then prepare confirmable MIDI clip proposals. | Musical quality and the complete preview → insertion → Undo workflow need qualification. Autonomous song composition and arrangement are not established. |
| Interfaces | Has frontend, desktop, native plug-in and MCP implementations connected to the companion. | Several MCP proposals have routing gaps; native Apply can mislabel a refusal as verified. Current release packaging and clean-host validation remain open. |

Return mixer volume, pan and mute already have a dedicated guarded path. The
return/master limitation above concerns general device-parameter targeting.
Generic raw control is not restricted to the ten insertable effects or nine
devices with display-unit mappings; those are separate capabilities.

The insertion allowlist contains EQ Eight, Glue Compressor, Saturator, Auto Filter,
Drum Buss, Compressor, Hybrid Reverb, Echo, Roar and Multiband Dynamics. No
instrument or MIDI effect is currently in that allowlist.

## Capabilities not established

- Complete control of every stock device, nested rack, parameter, Pack, preset,
  Max for Live device or third-party plug-in control.
- Reliable execution and honest verification across every newer automation,
  arrangement, rack, routing, freeze and safety-limiter extension. Some are latent
  methods rather than available public workflows.
- Automatic attribution of a bus-level audio problem to a particular track or
  device, or a qualified claim that a suggested change improves musical quality.
- Dependable autonomous song composition, arrangement or an autonomous AutoMix
  workflow.
- Audio generation and audio-to-MIDI as dependable default capabilities. They
  remain optional integrations with separate availability and qualification.
- Proven model quality, latency and resource use alongside Live on the target Mac.
- A fully qualified current release, including supervised sessions, extended soak,
  signing/notarization and clean-host validation.

## Recorded verification

The [Live 12 implementation audit](KENN_LIVE12_IMPLEMENTATION_AUDIT_2026-10-02.md)
passed **1,028 Python tests**, **20 frontend API/composable tests** and **three pure
C++ test executables**. Its inventory contains 78 stock/catalog entries, 77 matching
knowledge notes, ten insertion devices and 20 unit-profile entries across nine
devices plus the separate EQ Eight band-gain path. The recipe-card component test
was blocked by the existing missing `happy-dom` dependency. No running Live session
was accessed, and the full native plug-in was not built in that audit.

Since the status discussion, the recorded combined backend baseline reports
**3,171 passed, 12 optional-dependency skips and no failures**. It covers the
request-local knowledge and rewrite-readiness fixes and predates subsequent
reference/status/cancellation changes. See the exact scope, warnings and commands
in [the backend test baseline](KENN_TEST_BASELINE_2026-10-02.md). These counts have
overlapping tests and must not be added together.

Passing automated checks does not establish real-model answer quality, human
usability, musical usefulness or current-build real-Live qualification. Historical
real-Live receipts qualify their recorded targets and builds only.

## Next qualification priorities

The plan tracks request/context consistency, honest Apply/readback receipts,
transport and device coverage, and measured conversation quality and speed.
Implementation repairs remain open under A2/A3/A4, C1–C5 and L1/L3/L5. Completing
L1a means the source audit is complete; it does not mean full Live control is
complete. Listening, memory, creation and release gates remain separately tracked
under B1–B4 and R1–R4.

Relevant evidence:

- [Live 12 audit report](KENN_LIVE12_IMPLEMENTATION_AUDIT_2026-10-02.md)
- [Live 12 machine-readable audit](KENN_LIVE12_IMPLEMENTATION_AUDIT_2026-10-02.json)
- [Backend test baseline](KENN_TEST_BASELINE_2026-10-02.md)
- [Realtime Mix Review scope](../reports/KENN_REALTIME_MIX_REVIEW.md)
