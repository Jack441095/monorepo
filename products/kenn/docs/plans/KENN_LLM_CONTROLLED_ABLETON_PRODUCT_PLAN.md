# KENN: LLM-Controlled Ableton Product Plan

Status: active implementation plan — 2 September 2026

## Product outcome

KENN becomes an Ableton Live plug-in product controlled by natural-language
commands. A user can type a request such as “mute the vocal”, “set the bass
volume to -8 dB”, or “show devices on track 4”. KENN must show the exact Live
target and proposed change before anything is written. The user confirms; KENN
executes through `KENN_Bridge`, reads the value back, and reports a receipt or a
clear failure.

The LLM is the language and planning layer. It is never the authority that
writes to Live. KENN’s typed boundary, current Live snapshot, confirmation
token, stale-state check, idempotency key, readback, and undo receipt are the
authority.

## Architecture decision

```text
User text
   ↓
C++ plug-in UI and local HTTP client
   ↓
Optional LLM planner → typed JSON plan
   ↓
Deterministic KENN command gateway
   ↓
Fresh KENN_Bridge snapshot and exact target resolution
   ↓
Typed proposal → user confirmation
   ↓
LiveActionService: validate → write → read back → receipt
   ↓
Ableton Live
```

### Use C++ where it has a measurable advantage

- Audio analysis, meters, feature snapshots, serialization, and all audio
  thread work remain in `common/AudioTooRealtimeCore.h` and the JUCE plug-in.
- The plug-in owns the responsive command UI, local HTTP client, proposal
  display, confirmation dialog, and non-blocking result handling.
- No network, LLM call, file I/O, allocation-heavy analysis, or Live mutation
  runs from `processBlock()`.
- Python remains the local companion boundary for the knowledge index, LLM
  provider adapters, session persistence, and Ableton orchestration. Porting
  those pieces to C++ would add model/runtime complexity without reducing
  audio latency; the command request is already off the audio thread.
- If a future benchmark proves the companion process is the bottleneck, move
  only the measured hot path into a small C++ service or embed a local model;
  do not rewrite by assumption.

## Current implementation slice

Implemented in this pass:

- `apps/backend/src/kenn/core/live_intent.py` recognises user-facing numbered tracks,
  safe track controls, device-parameter requests, EQ insertion intent, and
  compound EQ-cut intent without performing writes.
- `apps/backend/src/kenn/core/live_command.py` provides the
  `kenn.ableton_command.v1` gateway, bounded LLM-plan validation, exact
  snapshot resolution, read-only inspection, clarification/refusal, and
  proposal/confirmation routing.
- The optional `KENN_LIVE_LLM_ENABLED=1` planner path can ask the configured
  local/OpenAI-compatible model for `kenn.ableton_llm_plan.v1`; malformed,
  unsupported, or snapshot-mismatched plans are rejected before they become
  intents. Provider-backed quality is implemented as a path, not yet a
  qualification claim.
- `POST /api/ableton/command` is a stable companion endpoint for the plug-in
  and future LLM planner.
- The C++ plug-in has a dedicated `Control Live` action. It sends the command
  off the audio thread, displays the exact proposal, asks for confirmation,
  and reports verified application or failure.
- Offline `Local Mix Check` remains usable when the companion is unavailable.

## Capability ladder

### Phase 1 — supervised command core (current)

Support and qualify:

- inspect tracks and devices;
- set volume, pan, mute, solo, and arm;
- play and stop transport;
- change one explicitly inspected device parameter;
- confirmation, stale rejection, replay rejection, readback, receipt, and
  undo.

The deterministic parser is the fail-safe fallback. The optional LLM may
produce a plan, but it must pass the same schema and snapshot validator.

### Phase 2 — native EQ workflow

Add a typed, reversible `insert_device` operation only after confirming the
Ableton API for the supported Live version. The operation must:

1. identify the exact track by index and name;
2. identify the exact device definition (`EQ Eight`) from an allow-list;
3. wrap insertion in a proposal and explicit confirmation;
4. read back the device list and exact new device identity;
5. return a receipt with a safe rollback path;
6. refuse if the device already exists ambiguously or Live changes during the
   proposal.

Compound EQ commands such as “reduce amplitude by 3 dB at 250 Hz” must become
an atomic multi-parameter proposal before they can write both band frequency
and gain. Until that transaction exists, KENN asks for the exact band and does
not guess.

### Phase 3 — LLM planner qualification

The optional local or hosted OpenAI-compatible planner is now behind an
explicit configuration flag. It receives only the command and a bounded Live
snapshot and returns JSON matching `kenn.ableton_llm_plan.v1`.
KENN rejects prose, unknown actions, invented targets, missing values,
destructive operations, and unsupported compound changes. If the LLM is
unavailable or times out, the deterministic parser remains the fallback.

The remaining gate is provider-backed evaluation: measure parse accuracy,
latency, refusal/clarification accuracy, prompt-injection resistance, and
whether the model adds value over the deterministic fallback. Do not enable it
by default in a release build until those measurements exist.

### Phase 4 — product hardening

- Keep the plug-in transparent: no silent DSP or automatic Live writes.
- Add session history, receipts, undo, and a visible “nothing changed yet”
  state.
- Add command latency telemetry separately from audio latency.
- Package the local companion for one-click startup only after the current
  loopback architecture is stable; bundling is a deployment improvement, not
  a reason to weaken the boundary.
- Add native C++ benchmarks for command JSON parsing and UI response only if
  measurements show a need. The audio thread is already the latency-critical
  path.

## Acceptance tests

Every release candidate must prove:

- “show my tracks” returns a fresh snapshot and changes nothing;
- “mute track 2” produces an exact proposal and does not write before
  confirmation;
- confirmation changes only the named track, readback verifies it, and the
  receipt is undoable;
- a changed value, changed name, expired token, forged token, replay, timeout,
  and missing Live session all fail closed;
- “add EQ on track 4” never hangs or silently inserts a device while insertion
  is disabled;
- “reduce amplitude by 3 dB at 250 Hz” asks for the missing track/band context
  and never pretends to have applied an EQ move;
- all C++ audio-thread tests, numerical parity, ThreadSanitizer, Python
  regression tests, and the real Live read-only qualification pass;
- the C++ plug-in works with the companion stopped for local meters and Mix
  Check, and reports command unavailability honestly.

## Working commands

```bash
python3 -m pytest -q apps/backend/src/kenn/tests
cmake --build build/plugins/kenn-vst3-au --config Release --parallel 2
./scripts/start_server.sh
curl http://127.0.0.1:8090/api/health
```

## Verification snapshot — 2026-09-02

Completed in the current worktree:

- Python command, intent, action-service, safe-pipeline, and server smoke
  tests pass, including `6 passed` for `test_server_smoke.py` with the LLM
  disabled.
- The native VST3/AU build passes. Numerical parity, real-time thread-safety,
  and performance checks pass; the measured audio-processing CPU cost remains
  below the test budget.
- The compiled plug-in command client reaches `/api/ableton/command` and
  receives a bounded response from the running local companion.
- `KENN_Bridge` is installed in the active external User Library Remote
  Scripts path, selected in Live's Control Surface slot, and responding on
  UDP port 11000.
- The real-Live read-only qualification passes with `connected: true`, fresh
  track identity fields, and four visible tracks.
- The running command endpoint returns `inspected` for “show my tracks” with
  `changed: false` and `confirmation_required: false`.
- The previous `AudioToo_Bridge` folder was moved to the recoverable
  `AudioToo_Bridge.backup-20260902` directory.

Do not mark this product as fully autonomous. The correct early release claim
is “LLM-assisted, confirmation-gated Ableton control”.
