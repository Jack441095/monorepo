# KENN + SLO + AudioGen Integration Truth Report

Date: 2026-09-21

## Executive result

The KENN-side AudioGen MIDI boundary is implemented and regression-tested. The shared collaboration checkout contains the real AudioGen producer and SLO C++ source, and both were exercised from this pass. The producer serializer was tightened to enforce the declared half-open clip window; five seeded one-bar outputs now all convert to valid KENN artifacts. Ableton Live/OSC was not available, so proposal confirmation, insertion, readback, and undo remain unqualified on this host.

## Verified now

### KENN → AudioGen MIDI boundary

- `/api/audiogen/midi-proposal` exists and is confirmation-gated.
- AudioGen events are converted to bounded, digest-backed MIDI artifacts.
- Live context records exact track identity, tempo, time signature, key, and timing limitations.
- `MidiClipActionService` supports proposal, confirmation, readback verification, retry safety, and identity-bound undo.
- Local KENN symbolic generation plus artifact conversion produced 32 notes with p50 `0.118834 ms` and p95 `0.138667 ms` over 200 repeats.
- MIDI import validation measured p50 `0.026500 ms` and p95 `0.028417 ms`.
- Relevant KENN/Ableton/AudioGen boundary tests: **163 passed**.

The actual producer bridge was loaded from the collaboration checkout with
`KENN_AUDIOGEN_ROOT` plus the shared `nite_core` path. Five seeded one-bar runs
all returned producer JSON in a p50 `870.520 ms` / p95 `922.287 ms` envelope,
and all five converted to valid KENN artifacts. The producer boundary now drops
events at or beyond the declared clip end and clips a final duration to the
remaining window. Duplicate notes are coalesced with explicit warnings by KENN.

The local symbolic stages are not the bottleneck. Actual AudioGen model latency and OSC round-trip latency remain unmeasured.

### KENN DSP

Existing receipts establish large native wins:

- Real 24-bit assets: native p50 `63.651 ms` versus reference `2418.996 ms` on one file, and `25.574 ms` versus `2479.984 ms` on another.
- Peak RSS: native `177 MB` versus reference `2.56 GB` on the same workload.
- Masking: native p50 `55.405 ms` versus reference `187.234 ms` with identical findings digest.

No new DSP rewrite is justified until remaining boundary and serialization stages are profiled.

### KENN ↔ SLO boundary

- KENN SLO adapter and route tests pass.
- KENN intentionally consumes SLO through a read-only, typed boundary.
- Unknown/OOD and confidence handling are represented in the adapter contract.

## Blocked or not freshly verified

### AudioGen producer / Ableton

- The main monorepo does not vendor the producer, but the shared collaboration
  checkout provides it at `monorepo-collab/Audio_Too/server/app` and
  `monorepo-collab/Audio_Too/studio/audiogen/audiogen`.
- The producer serializer now enforces the strict half-open clip window before
  KENN intake; the five-seed qualification passed after this fix.
- Ableton Live was unavailable, so no OSC round-trip, confirmed insertion,
  readback, or undo receipt was produced.

### SLO production handoff

- `products/slo/SmartSampleManager/Source/` is absent from the main checkout;
  the collaboration checkout contains the source and was used for source-level
  review and the existing qualification binaries.
- No `kenn.slo_artifact_manifest.v1` handoff artifact is present.
- The classifier is not enabled in KENN production.
- Existing SLO evidence is still the authoritative runtime baseline: Release
  16/32 inference batching is ~25.5–26.25 ms/file with ~1.4–1.47 GB RSS,
  versus ~28.63 ms/file and ~1.98 GB for 32/64; the RT stress test reports
  0/2000 deadline misses and 0 allocations. These are SLO-local receipts, not
  a KENN handoff benchmark.

## Current bottleneck map

| Area | Evidence | Decision |
| --- | --- | --- |
| KENN DSP kernels | Native/reference receipts show 70–99% wins | Keep native path; profile boundaries next |
| KENN chat | Recent profile shows BM25/rerank around 10 ms/request; chat cache/batched-write pass already landed | Keep Python unless a complete-request C++ candidate wins materially |
| AudioGen symbolic MIDI | Sub-millisecond local stages | Not a bottleneck |
| AudioGen model/bridge | Producer p50 ~871 ms / p95 ~922 ms; 5/5 artifacts valid after boundary fix | Qualify OSC and Live round-trip |
| SLO inference/scan | Release batch sweep and RT stress receipts are available; 150 ms flush and lock-held UMAP remain documented follow-ups | Keep 16/32 default; profile deferred lock/flush work before changing it |
| SLO → KENN artifact intake | Required handoff manifest missing | Block classifier enablement; build intake verifier first |

## Next executable phase

1. Correct the producer's exact-end-of-clip event (or change its declared
   section length) and add a seeded regression test.
2. Run the proposal path against Ableton Live and capture confirmation,
   readback, and identity-bound undo receipts.
3. Add a versioned `kenn.slo_artifact_manifest.v1` producer handoff, then
   measure the remaining SLO lock/flush paths before changing C++.
4. Optimize cross-module serialization, queueing, OSC, and model boundaries in
   C++ only where complete-request measurements prove a win.

No commit was created; the existing dirty worktree was preserved.
