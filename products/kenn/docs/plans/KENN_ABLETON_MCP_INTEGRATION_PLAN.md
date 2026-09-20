# KENN Ableton MCP integration plan

Status: **adapter decision recorded — 2026-09-05**

## Decision

Use Ableton MCP as an optional tool/protocol adapter for KENN, not as a direct
replacement for KENN's proposal and verification boundary.

KENN already has a working AbletonOSC route with exact target selection,
confirmation tokens, stale-state checks, readback verification, replay
rejection, receipts, and identity-bound undo. An MCP server that exposes raw
Live mutations directly to an LLM would bypass the most important part of the
current design.

The intended control path is:

```text
LLM or MCP client
        |
        v
KENN MCP facade: typed tools, snapshots, proposals, confirmation
        |
        v
LiveActionService: stale checks, exact identity, readback, receipts, undo
        |
        v
Ableton backend: AbletonOSC today; Extensions SDK/MCP adapter later
        |
        v
Ableton Live
```

## Candidate routes

### AbletonOSC-based MCP servers

Several open-source projects expose AbletonOSC as MCP tools. The
[Simon-Kansara Ableton Live MCP server](https://github.com/Simon-Kansara/ableton-live-mcp-server)
uses the same AbletonOSC transport and the standard `11000`/`11001` ports that
KENN currently owns. It is useful as a reference for tool naming and MCP
schemas, but it must not run as a second OSC client beside KENN: both processes
would compete for the fixed AbletonOSC reply port and could misassociate
responses.

### Ableton Extensions SDK

Ableton's official [Extensions SDK](https://www.ableton.com/en/live/extensions/)
is the longer-term native option. It can interact with tracks, clips, MIDI,
devices, tempo, and other Live-set data. The SDK is currently documented as a
Live 12.4.5 public-beta feature and is available to Live Suite users in that
beta, so it should be evaluated in an isolated beta installation rather than
becoming KENN's production dependency immediately.

The open-source
[Ableton MCP Extension](https://github.com/idx3d/ableton-mcp-extension) is a
useful reference implementation for this route. Its reported in-Live testing
is promising, but KENN still needs independent capability, stale-state,
readback, and recovery tests before trusting its write surface.

## KENN boundary rules

The first KENN MCP surface should expose only these operations:

1. `live_snapshot` — read-only topology and transport context.
2. `live_devices` — exact track/device identities.
3. `live_parameters` — exact parameter names, raw values, ranges, and optional
   Ableton display strings.
4. `live_parameter_profile` — one exact parameter's raw value, range,
   quantization, and targeted Ableton display string; never a write.
5. `create_live_proposal` — deterministic KENN proposal; never a write.
6. `apply_live_proposal` — requires the exact proposal, confirmation token, and
   idempotency key; delegates only to `LiveActionService`.
7. `undo_live_receipt` — creates and applies a fresh identity-bound inverse
   proposal through the same confirmation boundary.
8. `live_receipts` — bounded, redacted recovery evidence after an uncertain
   transport exchange; never exposes confirmation secrets.

The MCP layer must not expose raw `set_parameter`, raw OSC addresses, arbitrary
Python execution, filesystem paths, or a tool that accepts free-form model JSON
and writes directly to Live.

## Implementation stages

### Stage 1 — provider-neutral read path

- Define a small backend protocol around the methods KENN already consumes:
  session snapshot, topology, device parameters, display strings, and bounded
  writes.
- Keep `AbletonOSCClient` as the default backend.
- Add a read-only MCP/provider adapter test double; do not install a third-party
  MCP server into the active Live set yet.
- Make capability reports identify the backend and its read/write contract.

**Progress:** `apps/backend/src/kenn/core/live_backend.py` now defines the
provider-neutral contract and a dependency-free `ReadOnlyMCPBackend`. It maps
snapshot, parameter, and display-string tools into KENN's inspection path,
advertises no write tools, and raises on every mutation method. Three tests
cover direct reads, capability reporting, proposal creation, and failed-safe
application. The adapter is intentionally not selected by the running server.

### Stage 2 — KENN-owned MCP facade

- Expose KENN's typed read/proposal/apply/undo operations as MCP tools.
- Keep deterministic parsing authoritative when a request comes from an LLM.
- Require exact Live identity in every proposal and reject stale snapshots.
- Return compact deltas and receipts rather than dumping the whole Live set to
  the model.

### Stage 3 — disposable write qualification

For each backend, repeat the existing qualification sequence:

1. proposal-only inspection;
2. explicit confirmation;
3. one reversible write;
4. fresh readback;
5. exact replay rejection;
6. inverse receipt and restored readback;
7. transport loss or timeout recovery without retrying an ambiguous write.

No backend becomes selectable for writes until it passes the same evidence
requirements as AbletonOSC.

### Stage 4 — optional native backend

Only after Stage 3 should KENN evaluate an Extensions SDK backend against
AbletonOSC on a disposable set. Compare:

- device and parameter identity stability;
- display-unit mapping;
- insertion and deletion semantics;
- stale-state behavior;
- readback latency;
- Live restart and extension-host recovery;
- undo and transaction behavior;
- third-party AU/VST parameter coverage.

The selected backend should be a runtime configuration choice, never an
LLM-controlled choice.

## Acceptance gates

- Existing AbletonOSC tests remain green.
- MCP read-only calls cannot mutate Live.
- No MCP call can bypass `LiveActionService`.
- Every write has a visible exact proposal before mutation.
- Every successful write has numeric and, when available, display-value
  readback.
- A lost response never triggers an automatic repeat.
- The MCP client and KENN do not bind competing AbletonOSC reply sockets.
- The active plugin continues to work if the MCP provider is offline.
- A full Live restart is required and explicitly acknowledged before changing
  the installed Remote Script or plugin binary.

## Immediate next action

Stage 2 is now implemented and exercised as a dependency-free stdio MCP
facade: `PYTHONPATH=source python3 scripts/kenn_mcp_server.py`. Against the
running KENN companion it returned a connected Live topology and created a
confirmation-only Glue Compressor proposal with `changed=false`; no Live
mutation occurred. The facade exposes typed snapshot, device, parameter,
display-string/profile, capability, proposal, exact confirmed-apply, and
identity-bound undo tools. Apply and undo delegate only to KENN's existing
HTTP safety boundary; there is still no raw OSC or arbitrary execution tool.
The disposable-set qualification is now complete for Glue `Attack`, track pan,
EQ gain, compound EQ, and device insertion/removal: each MCP apply verified
readback, exact replay was rejected, and receipt undo restored the original
state. The final Live snapshot confirmed `4-Audio` pan `0.0` and an empty
`2-MIDI` device chain. The facade now also exposes a redacted `live_receipts`
recovery tool and marks an incomplete apply/undo transport exchange as
`transport_uncertain` with `retry_allowed=false`. Simulated transport coverage
passes; a deliberate real ambiguous-write qualification remains before
evaluating the official Extensions SDK path in a separate Live beta set.
AbletonOSC remains the fallback.

The rebuilt KENN VST3 has now also been hosted and verified in the reopened
disposable Live set: `4-Audio` reports `EQ Eight` followed by `KENN Mix
Assistant`, and the same MCP facade can read the KENN plug-in's exposed
parameters and create a confirmation-only proposal against them. This proves
the MCP-to-hosted-plugin inspection path; it does not enable autonomous model
writes or qualify every plug-in parameter's user-facing unit mapping.

Client connection and confirmation sequencing are documented in
[`docs/KENN_MCP_CLIENT_SETUP.md`](docs/KENN_MCP_CLIENT_SETUP.md).

The hosted disposable copy has also passed a reload persistence check: after
reopening `KENN_MCP_hosted_20260905.als`, Live reported the same
`EQ Eight -> KENN Mix Assistant` chain on `4-Audio`, and the KENN companion
health endpoint plus AbletonOSC snapshot remained connected. The original
safety copy was not modified.

The first integrated-context slice is now implemented: `kenn.session_context.v1`
is a bounded read model for Live topology, exact devices, track-role evidence,
plug-in frames, Mix Review receipts, AudioGen job metadata, and AutoMix receipts.
The MCP facade exposes it as read-only `kenn_context`, alongside exact
read-only `live_midi_clip` inspection for one clip slot. When the current OSC
connection is offline, the tool returns an empty Live context and an explicit
limitation instead of creating a proposal.

`kenn_context` requests the full Live snapshot so an LLM receives the current
tempo, time signature, root note, scale, mixer observations, and selected track
alongside topology. It now also attaches the read-only device capability matrix
by default, without expanding every parameter profile. Set
`include_device_parameters` to true when the planning turn needs bounded
current parameter ranges as well. The lightweight `live_snapshot` topology
default remains available for fast liveness and identity reads.

The facade also exposes read-only `mix_review_recommendations`. It returns
measured findings and action-plan guidance with the review id and an explicit
`uploaded_or_rendered_audio` scope. The result forbids Live target inference:
an LLM must identify an exact current Live track/device/parameter separately
before creating the normal confirmation-only proposal.

For multi-operation control, `create_live_recipe_proposal` accepts one to
three typed steps and returns a single confirmation-only recipe. It is still
proposal-only at the MCP boundary; application uses the normal confirmation,
fresh-state, per-step readback, rollback, receipt, and identity-bound undo
path.

AudioGen metadata is now bounded by `kenn.audiogen_artifact.v1`. MIDI artifacts
are checked for digest, note-range, note-count, bar, tempo, and key metadata;
unsupported kinds and invalid values fail closed, while producer filesystem
paths are excluded from the context sent to an LLM. A completed artifact can
now feed a proposal-only MIDI handoff; it cannot change Live without explicit
confirmation and the existing readback boundary.

When the optional local AudioGen bridge is configured,
`generate_audiogen_midi_proposal` can also generate symbolic events,
validate/hash them, and return the same typed proposal without applying it.

The facade also exposes read-only `audiogen_artifact` for one job ID. It
returns a bounded artifact summary and `ready_for_review`; missing jobs and
incomplete metadata remain explicit limitations. The bundled AbletonOSC
surface has documented `create_clip` and `add/notes` endpoints, now enabled
only through the typed proposal service below.

The facade now also exposes `live_device_matrix` as a read-only discovery
tool. It returns exact current track/device identities, readable parameter
profiles, and qualification labels before an LLM chooses a command or recipe.
Those labels describe evidence status only; every write still requires the
shared proposal, confirmation, stale-state, readback, receipt, and undo gates.

`kenn_context` composes this discovery result with the same fresh full Live
snapshot in one planning packet. The matrix is included without parameter
profiles by default; `include_device_parameters=true` expands bounded ranges
when the planner needs them. This keeps the normal context call useful and
complete without forcing the slowest inspection path on every conversational
turn.

For the opt-in Live LLM path, KENN now performs the same targeted expansion
automatically after deterministic parsing identifies the requested track. The
model sees bounded parameter names, sparse Live indices, current values, and
ranges for that track's devices; if it returns a device-parameter action, the
name/index pair must match the live-read profile exactly. Failure remains
fail-closed before a proposal is created. The plan validator also rejects
unknown fields, unrelated action fields, and nested steps outside an explicit
recipe action, so a model cannot smuggle a second operation inside a simple
command plan.

The first supervised MIDI clip boundary is now implemented and real-Live
qualified in `kenn.core.midi_clip_service`: `create_midi_clip_proposal`
accepts a bounded note list for one exact empty slot, and confirmed
application verifies clip length, MIDI identity, and every note. A verified
receipt carries a deletion inverse. Replacement of an existing clip,
arbitrary file-path import, and autonomous LLM application remain disabled.
The 2026-09-05 qualification created and removed a two-note clip on `1-MIDI`
slot 1 with both forward and inverse receipts verified by Live readback.
An additional `2-MIDI` clip was applied, rejected on an exact replay, and
removed through the same verified inverse path. The full repository suite is
green at **349/349**. The actual AudioGen symbolic-event producer has also
been qualified through this boundary: a one-bar phrase was normalized from 12
producer events to 10 Live-representable notes, applied through the stdio MCP
facade with verified readback, and removed through verified identity-bound undo.

Generated MIDI proposals now also capture `kenn.audiogen_live_context.v1` from
a fresh full Live snapshot before producer invocation. The context records the
exact target, tempo, meter, key/scale, producer metadata when present, and an
explicit no-retiming decision. A real proposal-only run returned 4/4 and C
Major from Live with `changed=false`; no clip or note was written.

Validated MIDI artifacts now also carry a bounded symbolic preview with note
density, pitch-class distribution, velocity/duration ranges, onset count, and
up to 64 ordered events. This is an inspectable preview only; the contract
reports `audition.status=not_rendered`. A separate exact clip-slot audition
path is now implemented for existing MIDI clips; it reports Live playback
readback and does not claim that symbolic preview rendered audio.

The MCP facade now exposes `create_clip_audition_proposal` using
`kenn.ableton_clip_audition_proposal.v1`. It requires an exact existing MIDI
clip, verifies its identity before firing through AbletonOSC's clip-slot
endpoint, and returns an identity-bound stop inverse. A real disposable
qualification started and stopped a two-note clip with verified playback
readback, recovered the identity from the bounded journal inverse, and removed
the temporary clip. The next step is to compose this with generated-clip
creation and add a separate rendered-audio audition path.

That generated-clip composition has now passed as a real local qualification:
the configured AudioGen producer generated a one-bar 10-note artifact, KENN
created it on an empty exact MIDI slot, returned the bounded audition next
action, verified playback start and stop through clip-slot readback, and
removed the clip through identity-bound undo. A client timeout during cleanup
was reconciled from the receipt journal without retrying the ambiguous request.
The remaining creative workflow work is rendered-audio audition, feedback
capture, and deterministic revision—not another direct OSC path.
