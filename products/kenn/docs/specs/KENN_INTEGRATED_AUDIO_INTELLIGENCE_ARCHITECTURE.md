# KENN integrated audio intelligence architecture

**Status:** architecture proposal grounded in the current KENN/SLO codebases

**Date:** 2026-09-05

**Scope:** Ableton Live control, KENN plug-in intelligence, SLO classification,
Mix Review, AudioGen audio/MIDI generation, AutoMix, LLM planning, memory,
receipts, and safe file/track operations.

## 1. Product goal

KENN should behave like an intelligent studio instrument: it observes the
session, understands the user's musical intent, measures what can be measured,
creates or renders material when requested, proposes an exact next action, and
remembers only verified outcomes.

The user should be able to ask things such as:

- “Add EQ on track 4 and reduce 250 Hz by 3 dB.”
- “Why is the vocal getting masked by the synth?”
- “Generate a dark 8-bar bass loop in the current key.”
- “Write a MIDI bassline for the generated loop and put it on the bass MIDI
  track.”
- “Render two AutoMix versions of these stems and tell me what changed.”
- “Rename the fourth track to Bass Synth.”
- “Make the vocal clearer, but show me the exact changes before applying them.”

The key product behavior is supervised intelligence:

```text
observe -> classify -> measure/generate -> reason -> propose -> confirm
-> execute/render -> verify -> explain -> remember
```

No model, generator, or offline renderer gets an implicit write path into Live.

## 2. Design laws

1. **Facts before interpretation.** Every useful context item has a source,
   timestamp, version, and confidence.
2. **Unknown is a valid result.** Missing, ambiguous, unsupported, stale, and
   out-of-distribution states are reported explicitly.
3. **The LLM is a planner, not a privileged executor.** It may select typed
   tools and compose recipes; it cannot emit raw OSC, arbitrary Python, or
   unreviewed filesystem operations.
4. **One mutation boundary.** All Live writes go through the existing
   proposal/confirmation/stale-state/readback/receipt/undo service.
5. **Creative output is not evidence.** AudioGen output is generated material;
   Mix Review output is measured material; neither should be mislabelled as the
   other.
6. **Offline renderers stay offline.** AutoMix may create candidates and
   reports, but does not silently alter the Live set.
7. **Classification is evidence-gated.** SLO's methodology is reused: measure
   separability on real held-out data before shipping a new label, and stay
   silent when confidence is not earned.
8. **Every meaningful change is reversible.** A user can see the exact target,
   before value, after value, and a receipt-backed inverse action.
9. **Real-time audio stays deterministic.** The C++ plug-in audio callback does
   meters and bounded feature extraction only. Python, the LLM, disk I/O, and
   network calls stay off the callback.

## 3. High-level architecture

```text
                         User
                           |
                UI / KENN plug-in / MCP client
                           |
                           v
              +-----------------------------+
              | KENN intent + recipe layer  |
              | deterministic parser first  |
              | optional LLM planner        |
              +-------------+---------------+
                            |
                            v
              +-----------------------------+
              | Versioned SessionContext    |
              | facts + evidence + jobs     |
              +--+-----------+-----------+--+
                 |           |           |
                 v           v           v
       Ableton/MCP      Mix Review    SLO classifier
       Live snapshot    measurements  roles/subtypes
                 |           |           |
                 +-----------+-----------+
                             |
                             v
                  typed tool/recipe planner
                             |
        +--------------------+--------------------+
        |                    |                    |
        v                    v                    v
   LiveActionService     AudioGen jobs        AutoMix jobs
   OSC + readback        WAV + MIDI           offline candidates
        |                    |                    |
        v                    v                    v
   Ableton Live        generated assets      render/report store
        |                    |                    |
        +--------------------+--------------------+
                             v
                 receipts, memory, evaluation
```

## 4. Current state versus target state

| Surface | Current verified state | Target integration |
|---|---|---|
| AbletonOSC | Working local transport and fresh Live snapshots | Remain the default backend behind KENN's safety service |
| KENN MCP facade | Read tools, confirmation-only proposals, guarded apply/undo | Expose the shared context and typed recipes |
| KENN VST3 | Hosted and reloaded in Live on `4-Audio` after `EQ Eight` | Publish compact meter/context frames and receive supervised proposals |
| Live control | Track/device/parameter operations, supervised MIDI clip insertion, and exact clip-slot audition qualified across a real disposable set | Bind generated-clip audition into one composite workflow, add replacement/rename recipes, and expand capability profiles |
| Mix Review | KENN-owned deterministic WAV boundary with seven qualified fault families | Feed measured findings into explanations and proposal generation |
| SLO classification | Separate C++ product with evidence-gated taxonomy, OOD, confidence, and safe rename principles | Reuse the data model and methodology for KENN track context, not its PANNs classifier wholesale |
| AudioGen WAV | Existing KENN bridge and render/job routes | Add provenance, audition, comparison, and explicit import proposals |
| AudioGen MIDI | Bounded artifact contract, optional live producer adapter, supervised proposal/apply/undo handoff, symbolic preview, and exact existing-clip audition are qualified | Bind generated-clip creation to supervised audition and add richer musical-context adaptation |
| AutoMix | Approval-gated adapter; delegates to external Audio_Too renderer and is beta-disabled | Produce offline variants, compare them, explain deltas, and never write directly to Live |
| LLM command planning | Optional shadow/active code exists; capability identity, unit, and range gates reject unsafe plans; deterministic parser remains authoritative | Activate only after complete shadow agreement, latency, and human-review gates |
| Track/file rename | KENN track rename is confirmation-gated and real-Live qualified; filesystem rename remains separate | Add human-reviewed naming suggestions, then a separate filesystem service |

## 5. The shared `SessionContext`

The central integration object is a bounded, versioned context—not a dump of
every file, waveform, or conversation.

```json
{
  "schema": "kenn.session_context.v1",
  "session_id": "user-session-id",
  "observed_at": "2026-09-05T00:00:00Z",
  "snapshot_fingerprint": "sha256:...",
  "versions": {
    "live_snapshot": "kenn.live_snapshot.v1",
    "device_capabilities": "kenn.device_capabilities.v1",
    "track_classifier": "kenn.track_context.v1",
    "mix_review": "kenn.mix_review.local_engine.v1",
    "planner": "kenn.planner.v1"
  },
  "transport": {
    "ableton_connected": true,
    "tempo_bpm": 120.0,
    "playing": false
  },
  "tracks": [],
  "devices": [],
  "measurements": [],
  "generated_jobs": [],
  "offline_jobs": [],
  "previous_receipts": [],
  "available_actions": [],
  "limitations": []
}
```

Every child fact should include:

```text
source, observed_at, source_version, confidence, evidence, expires_at
```

The context builder must:

- use a fresh Live snapshot for any mutation;
- keep uploaded/rendered audio measurements separate from current Live meters;
- mark AudioGen output as `generated`, not `measured_user_audio`;
- mark AutoMix output as `offline_candidate`, not `applied_live_state`;
- discard expired plug-in feature frames;
- include limitations when a conclusion cannot be supported.

## 6. SLO classification layer for KENN

SLO's most valuable contribution is its classification design, not a direct
source-code transplant.

### 6.1 Track context model

Extend the current KENN track-name classifier into a read-only result like:

```json
{
  "track_index": 3,
  "track_name": "4-Audio",
  "role": "unknown",
  "subrole": null,
  "confidence": 0.18,
  "confidence_band": "low",
  "evidence": [
    {"kind": "name", "value": "4-Audio", "strength": 0.0}
  ],
  "candidates": ["audio", "bass_synth", "vocal_lead"],
  "uncertainty_reason": "generic_track_name",
  "masking_partners": [],
  "advisory_only": true
}
```

Potential evidence sources, ordered from safer to richer:

1. exact user-provided track name;
2. deterministic aliases (`vox`, `bgv`, `808`, `gtr`, `drm`, `fx`);
3. track type and routing;
4. device chain and instrument/effect capabilities;
5. clip metadata and MIDI/audio presence;
6. measured audio features, only when actually available;
7. user correction.

A name alone must never be presented as proof of the sound.

### 6.2 Confidence and Unknown states

Use the SLO pattern of a continuous confidence value plus visible bands:

- `high`: strong exact evidence or independently qualified measurement;
- `medium`: useful hypothesis with more than one supporting signal;
- `low`: name-only, generic, conflicting, or stale evidence.

Keep these distinct:

```text
never_observed != observed_unknown != ambiguous != stale
```

This directly improves the LLM: it can say “I need to inspect the track”
instead of treating a weak role guess as a command target.

### 6.3 What not to import from SLO

Do not copy the SLO PANNs classifier, taxonomy weights, or sample-library
labels into KENN without a KENN-specific dataset and evaluation. SLO's
cross-vendor OOD findings are a warning that apparently confident classifiers
can fail badly outside their training distribution.

## 7. Plug-in capability intelligence

KENN should learn what a plug-in can safely expose through inspection, not by
guessing from a screenshot or training on every plug-in name.

### Capability record

```json
{
  "schema": "kenn.device_capability.v1",
  "identity": {
    "track_name": "4-Audio",
    "track_index": 3,
    "device_index": 0,
    "device_name": "EQ Eight",
    "vendor": "Ableton"
  },
  "role": "eq",
  "parameters": [
    {
      "name": "1 Gain A",
      "raw_min": -15.0,
      "raw_max": 15.0,
      "unit": "dB",
      "readable": true,
      "writable": true,
      "mapping_evidence": "real_live_readback",
      "qualification": "qualified"
    }
  ],
  "safe_operations": ["inspect", "propose_parameter_change"],
  "unsupported_operations": ["arbitrary_script", "unverified_unit_conversion"],
  "observed_at": "...",
  "live_version": "..."
}
```

For third-party plug-ins, KENN should default to inspect-only until a parameter
profile has verified its raw range, display unit, quantization, readback, and
undo behavior. This is where MCP is genuinely valuable: it exposes structured
capabilities to an LLM without giving it a raw mutation socket.

## 8. Ableton Live and MCP control plane

### Read path

```text
MCP live_snapshot
  -> exact track/device topology
MCP live_devices
  -> exact identity
MCP live_parameters / live_parameter_profile
  -> raw value, range, quantization, display string
TrackContext classifier
  -> role hypothesis with evidence and confidence
```

### Write path

```text
user request
  -> deterministic parse and/or shadow LLM plan
  -> exact target resolution
  -> ActionProposal with before/after and evidence
  -> user confirmation
  -> LiveActionService
  -> AbletonOSC
  -> authoritative readback
  -> receipt + inverse/undo proposal
```

The LLM may produce a typed `recipe`, but every step is individually validated
and confirmation-bound. A recipe stops if the context becomes stale or any
step returns `clarification_required`, `unsupported`, or
`transport_uncertain`.

## 9. Mix Review integration

Mix Review is the measurement layer. It currently qualifies bounded families
such as clipping, headroom, silence/truncation, channel imbalance,
phase/mono-compatibility, DC offset, and loudness estimate.

The local companion now uses KENN's repository-owned deterministic WAV engine
as its fallback review service when the historical external Audio_Too package
is unavailable. Reviews are persisted as metadata outside the repository;
source audio is not retained. The external engine remains opt-in only.

The integrated flow is:

```text
WAV or verified plug-in feature frame
  -> Mix Review receipt
  -> evidence-ranked finding
  -> candidate hypotheses
  -> exact Live proposal, only if the target and parameter are known
```

Example:

```text
Measured: recent bus peak -0.1 dBFS, 18 clipped samples.
Hypothesis: inspect limiter/clipper and upstream gain.
Proposal: none yet — current plug-in chain has not identified the responsible stage.
```

This avoids the common failure where a meter observation is incorrectly turned
into an automatic EQ or compressor command.

Future Mix Review upgrades should add masking, tonal balance, dynamics, and
reference comparison only after each family has its own measurements, fixtures,
limits, and abstention behavior.

## 10. AudioGen integration: WAV and MIDI

AudioGen is a creative generator. It should become a first-class asynchronous
job system with two output types.

### 10.1 WAV output

```text
creative brief
  -> typed AudioGen request
  -> render queue
  -> WAV + metadata + hash
  -> audition/measure/classify
  -> optional Live import proposal
```

Required metadata:

- prompt/brief and normalized musical intent;
- emotion/style, bars, BPM, key if known;
- model/provider/version and seed where available;
- output hash and local path constrained to the approved runtime area;
- rights/provenance status;
- whether the file is generated, user supplied, or derived.

### 10.2 MIDI output

The adjacent AudioGen implementation already has MIDI event generation and
MIDI export. KENN should integrate that as a typed artifact rather than treating
it as a WAV side effect.

```json
{
  "schema": "kenn.audiogen_midi_job.v1",
  "job_id": "...",
  "status": "completed",
  "artifact": {
    "kind": "midi",
    "path": "approved-runtime/bassline.mid",
    "sha256": "...",
    "tracks": [
      {
        "name": "Bass",
        "channel": 1,
        "note_count": 48,
        "lowest_note": 36,
        "highest_note": 55,
        "bars": 8
      }
    ],
    "bpm": 120,
    "key": "C minor"
  },
  "provenance": {"generated": true, "model": "..."},
  "validation": {
    "parseable": true,
    "notes_in_range": true,
    "channels_valid": true,
    "no_unbounded_events": true
  }
}
```

Validated MIDI artifacts also expose a bounded symbolic preview: note density,
pitch-class distribution, velocity/duration ranges, onset count, and up to 64
ordered events. The preview is not audio playback; it reports
`audition.status=not_rendered`. A separate supervised Live clip-slot audition
path is now implemented for already-existing MIDI clips; it reports actual
playback readback and remains distinct from artifact preview and clip creation.

### 10.3 MIDI-to-Live stages

MIDI insertion is a separate capability from MIDI generation:

1. **Stage 1 — export and audition:** KENN generates or receives a validated
   `.mid` artifact; the user can review it without Live mutation.
2. **Stage 2 — supervised import:** the typed Ableton backend now creates a
   MIDI clip on an exact empty MIDI track/slot and verifies the result.
3. **Stage 3 — MCP recipe:** `create_midi_clip_proposal` and
   `create_midi_clip_from_artifact` expose exact track, scene/slot, clip
   length, note events, and artifact hash; confirmation, readback, replay
   rejection, and undo/delete-reversal are required.
4. **Stage 4 — musical context:** use current tempo, time signature, key, and
   selected track/device context to adapt the generated part before proposal.
5. **Stage 5 — supervised audition:** after a clip exists, propose one exact
   track/slot audition, verify clip identity before firing, verify
   `is_playing`/`is_triggered` after firing, and expose an explicit stop inverse.

The typed proposal and MCP boundary for supervised MIDI clip insertion are now
implemented and qualified against a disposable local Live session. The actual
AudioGen producer is also connected through an opt-in root configuration:
`generate_audiogen_midi_proposal` returns a digest-bound proposal, and the
stdio MCP route has completed a real generate -> confirm -> apply -> readback
-> undo cycle. AudioGen duplicate events at the same pitch/start position are
coalesced deterministically because that is the representation Ableton's clip
API can verify. Replacement, arbitrary file-path import, and autonomous LLM
application are still disabled. The first context slice now captures the exact
Live target and observed tempo before generation, records the producer tempo
when available, and explicitly preserves symbolic beat positions without
silent retiming. Exact replay rejection and verified deletion
recovery remain required.

The companion/MCP read surface now includes exact clip-slot inspection, so a
planner can observe whether a slot is empty, confirm MIDI identity, and inspect
bounded notes before it creates a proposal. This keeps musical state discovery
separate from mutation.

The exact clip-slot audition boundary is now implemented in
`kenn.core.clip_audition_service` and exposed through the MCP facade. It only
accepts an existing MIDI clip, binds its length and note fingerprint to the
proposal, uses AbletonOSC's clip-slot fire/stop methods, and verifies both
playback transitions. Verified MIDI-clip creation now returns a bounded next
action for audition, while `create_clip_audition_from_receipt` derives the
target from the recorded receipt so an LLM cannot accidentally retarget the
wrong slot. A real disposable qualification passed start readback, stop
readback, receipt recovery, handoff, and cleanup; automatic “create then
audition” mutation and rendered audio audition remain later stages.

## 11. AutoMix integration

AutoMix should act as an offline candidate and comparison service:

```text
stems + mix goal
  -> source validation and hashes
  -> baseline measurements
  -> approved AutoMix render(s)
  -> candidate measurements
  -> before/after delta report
  -> user chooses candidate or asks for a supervised Live recipe
```

AutoMix output should include:

- input stem names and hashes;
- renderer/version and settings;
- target loudness and delivery constraints;
- baseline and candidate metrics;
- applied operation list;
- output hashes and paths;
- approval state;
- no claim that a candidate is musically better without a user/listening gate.

KENN should never translate an AutoMix output into a collection of Live writes
automatically. Instead it can say:

```text
Candidate B is 1.8 dB quieter, has improved mono correlation, and reduced
low-end overlap. These are the three reproducible operations that produced it.
Create a Live proposal for operation 1?
```

## 12. LLM intelligence layer

### What the LLM should do

- understand natural language and musical goals;
- classify the request into inspect, diagnose, generate, render, compare,
  propose, clarify, or refuse;
- select a typed tool;
- explain measured evidence in plain language;
- compose a bounded multi-step recipe;
- learn from explicitly reviewed user corrections in evaluation data.

### What the LLM must not do

- invent track/device/parameter indices;
- infer raw plug-in units from memory;
- claim to have heard audio that was not supplied;
- treat filenames or generated audio as ground truth;
- call raw OSC or arbitrary Python;
- write a MIDI clip or audio file into Live without a proposal;
- apply an AutoMix candidate to the set without a separate confirmation;
- retry an uncertain transport exchange.

The current Qwen shadow evidence supports this boundary: the small model made
a schema-valid but incorrect track-target selection, while the larger model
timed out on a simple case. Better prompts and a future reviewed adapter may
help, but deterministic target validation remains mandatory.

## 13. Memory and provenance

Persist structured events, not unrestricted conversation or raw audio:

```text
request -> normalized intent -> context fingerprint -> tool/job result
-> proposal -> confirmation -> readback -> receipt -> user feedback
```

Useful memory includes:

- preferred track names and roles, when user-confirmed;
- accepted/rejected mix suggestions;
- generated asset IDs and MIDI/WAV hashes;
- AutoMix candidates the user selected;
- verified Live changes and inverse receipts;
- corrections that become reviewed evaluation cases.

Every memory item needs provenance and a confidence/status field. A user
correction should not silently rewrite a global classifier or training set.

## 14. Safety and failure states

All clients should share this status vocabulary:

| Status | Meaning | Next action |
|---|---|---|
| `offline` | No fresh Ableton/engine context | Retry observation only |
| `unknown_target` | Identity cannot be resolved | Ask for exact target |
| `ambiguous` | Multiple interpretations | Ask one clarification |
| `unsupported` | Capability is not qualified | Explain limitation |
| `proposal_ready` | Exact before/after is known | Show and request confirmation |
| `awaiting_approval` | AudioGen/AutoMix job needs approval | Show artifact/settings |
| `applied_verified` | Readback confirms Live mutation | Return receipt |
| `rendered_verified` | Offline artifact validates and hashes | Offer audition/import |
| `transport_uncertain` | Outcome cannot be inferred safely | Inspect receipts/snapshot; never retry blindly |
| `failed` | Operation did not complete | Preserve source and explain |

Destructive or difficult-to-reverse actions—file moves, track renames, clip
replacement, and MIDI clip replacement—must show source/destination mappings,
require explicit confirmation, and produce an undo or recovery journal.

## 15. Performance architecture

### C++

Use C++ for:

- plug-in audio processing and metering;
- bounded feature extraction;
- bounded deterministic parsing of common hosted-plug-in Live commands;
- bounded read-only AbletonOSC topology and exact-device parameter snapshots;
- MIDI event validation/serialization if it enters the plug-in;
- low-latency host-facing code;
- lock-free or bounded queues between audio and UI threads.

### Python

Use Python for:

- HTTP/MCP orchestration;
- deterministic intent parsing and proposal services;
- batched read-only AbletonOSC snapshot collection with echoed identity matching;
- Mix Review analysis and evaluation;
- AudioGen/AutoMix job management;
- provenance, receipts, memory, and reports;
- LLM calls and asynchronous recipes.

The LLM and offline renderers must never run in the C++ audio callback. The
fast path is a C++ feature frame plus a local Python context update; a command
can then be planned asynchronously without adding audio latency.

The hosted plug-in's local parser is intentionally a language front-end, not a
second Live controller. It extracts a bounded action, track number, value/unit,
device name, and recipe marker without network, OSC, model, disk, or audio
callback work. Its metadata is advisory for observability; the companion
re-resolves every target against a fresh snapshot before creating a proposal.
Independent snapshot reads are batched to reduce round trips, while mutations
remain ordered, confirmation-gated, stale-checked, read back, and receipt-bound.

For the hosted Ableton plug-in, Live commands use a deterministic-only route
by default. The C++ UI sends an explicit no-LLM flag; the gateway performs
bounded language parsing and exact target resolution, then delegates the
guarded proposal/readback boundary to the one AbletonOSC companion. This
keeps the in-Live control path fast while preserving one owner for Live
transport. A fully serverless plug-in remains a separate migration: it would
need a C++ OSC client, snapshot cache, and the same confirmation, stale-state,
readback, receipt, and undo logic, while Ableton still needs a Remote Script
or Max for Live endpoint. The first serverless slice is now present as a
read-only C++ OSC codec and liveness probe used only when the companion HTTP
path is unavailable; the plug-in's Live-controls inspection also uses the
topology reader for track/device visibility. It does not create proposals or
perform mutations, and parameter qualification remains in the companion. This
keeps the migration incremental and prevents a second writer from bypassing
the Python safety service.

## 16. Implementation roadmap

### Phase 0 — preserve the working boundary

- Keep AbletonOSC as the single Live transport owner.
- Keep MCP as a typed facade over KENN, not a second OSC client.
- Keep deterministic parsing authoritative.
- Keep the hosted KENN VST3 and saved disposable Live set as the qualification
  fixture.

### Phase 1 — shared context and capability registry

- Add `kenn.session_context.v1` builders and validators.
- Add SLO-style `TrackContext` evidence/confidence output.
- Normalize `live_snapshot`, `live_devices`, `live_parameters`, plug-in frames,
  and Mix Review handoffs into the context.
- Add exact device capability profiles and qualification state.

### Phase 2 — cross-tool read-only intelligence

- Expose the context through MCP read tools.
- Let KENN explain track roles, device capabilities, current measurements, and
  job states together.
- Expose `mix_review_recommendations` as a provenance-scoped read tool so an
  LLM can carry measured findings into a supervised Live conversation without
  treating an uploaded bounce as current Live state or guessing a responsible
  track/device.
- Add context-age and source provenance to UI answers.
- Add benchmark cases for conflicting evidence and Unknown states.

### Phase 3 — supervised Live recipes

- Expand the qualified typed `rename_track` path to human-reviewed naming
  recipes and project-wide naming conventions.
- Add Mix Review finding -> Live proposal recipes only when an exact Live
  target/parameter is supplied separately and the review remains attached as
  evidence; never infer the target from the uploaded audio alone.
- The generic typed MCP recipe path is now implemented and real-Live
  qualified for a reversible two-step mixer change; Mix Review-specific recipe
  synthesis remains a later layer because audio evidence alone cannot identify
  the responsible Live track or device.
- Add parameter change recipes for qualified device families.
- Verify every step with readback and identity-bound undo.

### Phase 4 — AudioGen MIDI and asset workflow

- Add `kenn.audiogen_midi_job.v1`.
- Validate `.mid` artifacts and expose note/key/tempo summaries.
- Keep export/audition as the provenance-first path; the first verified MIDI
  clip import backend is now available through the supervised proposal path.
- The first Live-context handoff is qualified: `kenn.audiogen_live_context.v1`
  records exact target identity, Live/source tempo relationship, timing basis,
  and limitations in the artifact, confirmation token, proposal, and receipt.
- Time signature and key/scale context are now read from the full Live snapshot
  and carried into AudioGen provenance; deterministic adaptation and selected
  device context remain before exposing replacement or autonomous application.
- Add explicit generated-asset provenance and user approval.

### Phase 5 — AutoMix comparison workflow

- Keep AutoMix offline and approval-gated.
- Normalize baseline/candidate reports into `SessionContext`.
- Add a comparison explainer and candidate selection receipt.
- Offer reproducible supervised Live recipes, never opaque auto-application.

### Phase 6 — LLM shadow and eventual activation

- Evaluate route selection, exact identity, values, clarification, refusals,
  latency, and recipe stopping on a sealed holdout.
- Review representative cases manually.
- Run shadow mode against real snapshots without writes.
- Activate only if every proposal still passes the deterministic boundary and
  the model adds measurable value over deterministic parsing.

## 17. Acceptance gates

The integrated product is not ready until these are evidenced:

- context construction is deterministic, versioned, bounded, and provenance
  complete;
- conflicting Live, plug-in, uploaded-audio, generated-audio, and AutoMix
  evidence remains visibly separated;
- SLO-style Unknown/OOD behavior prevents forced track-role claims;
- every Live mutation shows exact identity and before/after values;
- every successful Live mutation has readback and undo evidence;
- AudioGen WAV and MIDI outputs are parseable, hashed, and provenance-labelled;
- MIDI import is independently qualified before MCP exposure;
- AutoMix candidates never mutate Live without a separate explicit proposal;
- file/track renames show mappings and have recovery evidence;
- no LLM call can access raw OSC, arbitrary execution, or an untyped write;
- real-time plug-in processing has no LLM/network/disk work in the callback;
- full regression, real disposable Live, and job-recovery tests pass;
- the system remains useful when the LLM, AudioGen, AutoMix, or MCP provider is
  offline.

## 18. Immediate next engineering slice

The first shared-context slice is now implemented without adding a new unsafe
mutation path:

1. `kenn.session_context.v1` composes bounded Live topology, exact devices,
   plug-in frames, Mix Review receipts, AudioGen jobs, and AutoMix receipts;
2. SLO-style track evidence and confidence are attached to each Live track;
3. `kenn_context` exposes that read model through the dependency-free MCP
   facade;
4. offline Live state is explicit and produces no trusted actions;
5. `kenn.audiogen_artifact.v1` validates MIDI artifact metadata and strips
   arbitrary producer paths from the LLM-facing context.

The MCP facade also exposes `live_device_matrix`, a read-only capability
inventory that resolves exact track/device identities and current parameter
profiles from Live. Qualification labels describe evidence status only; they
are not permission to write. This gives an LLM a reliable discovery step before
it chooses a typed command or recipe and reduces repeated guessed parameter
lookups. `kenn_context` now assembles that inventory with the fresh full Live
snapshot in one bounded planning packet; parameter profiles remain opt-in so
the default context stays responsive on larger sessions.

The dependency-free MCP facade now also exposes `audiogen_artifact`, a
read-only job lookup that returns the validated artifact summary and an
explicit `ready_for_review` flag. It is intentionally not an import command.

Natural-language recipes now include exact existing-device parameter steps
alongside bounded track or transport controls. The recipe resolver performs a
fresh Live parameter inspection to bind sparse parameter indices and
evidence-backed units before presenting one confirmation card. Device
insertion and EQ band retuning remain separate proposals until their
multi-step identity semantics are independently qualified.

The next slice is supervised creative handoff refinement: the existing
clip-audition receipt is now bound to a persisted listener feedback loop, so
`keep`, `revise`, and `reject` evidence can be supplied to the next planner
turn without granting it a write. Rendered-audio audition and deterministic
A/B comparison are now available as read-only candidate services. Live tempo,
meter, and key/scale are captured before generated MIDI proposal creation, but
no retiming or key transformation is performed implicitly. MIDI generation and
MIDI insertion remain separate capabilities; no clip import is claimed without
exact target identity, confirmation, readback, replay rejection, and
undo/recovery evidence.

For a `revise` verdict, `create_audition_revision_brief` now resolves the
persisted feedback by session and id and returns
`kenn.audition_revision_brief.v1`. This makes the listener's intent available
to an LLM without allowing free-form feedback to become a raw Live command.
The brief preserves the baseline audition receipt and exact target, and the
next candidate must still be independently inspected, proposed, confirmed,
read back, and undoable.

`generate_audiogen_midi_revision_proposal` now composes that brief with the
existing AudioGen symbolic-MIDI producer. It requires a new explicit seed and
passes the bounded brief into the artifact's provenance context; it does not
claim that the current producer understands arbitrary listener prose. The LLM
or future specialist producer must select the musical variation, while KENN
enforces exact-target matching and the normal Live proposal boundary.

The rendered candidate path is now available as the read-only MCP tool
`generate_audiogen_audio_candidate`. It returns a local listen URL backed by
KENN's allowlisted portfolio-audio handler and safe artifact metadata. The
handler may serve the configured adjacent AudioGen portfolio directory but
never returns its filesystem path; no rendered candidate is inserted into or
played by Live automatically.

Two rendered candidates can now be passed to
`compare_audiogen_audio_candidates`. KENN analyzes only its opaque local WAV
references and returns `kenn.audiogen_audio_comparison.v1`, including hashes and
bounded deltas for technical metrics such as RMS, peak, correlation, and
band-energy values. The comparison can be attached to an audition revision
brief, where it remains provenance and advisory evidence: a numerical delta is
not treated as proof that candidate B is musically better. This gives the LLM
both listener intent and measurable before/after context without granting the
comparison route any Live write capability.

The typed MIDI clip boundary is now implemented for the first safe case:
`create_midi_clip_proposal` accepts bounded notes and an optional source
artifact digest, rejects occupied slots, and routes confirmed creation through
AbletonOSC `create_clip` plus `add/notes`. The resulting receipt records the
exact notes and supplies a deletion inverse. The real disposable Live
qualification is now complete for this bounded case; broader replacement,
arbitrary import, and autonomous application remain separate gates.

This is how KENN becomes one intelligent studio system rather than a collection
of unrelated buttons, while preserving the safety boundary that is already
working.

## 19. Next engineering slice — self-contained local operation

The practical migration path toward a plug-in that does not require a
manually started Python process is now explicit:

1. **Read-only parity:** extend the C++ OSC layer from song liveness to a
   bounded topology/device snapshot and compare its decoded output with the
   Python bridge on sealed fixtures. No writes are enabled in this stage.
2. **Proposal parity:** translate the existing typed proposal schemas into a
   C++ read/plan model, including snapshot fingerprints, exact identity, and
   stale-state checks. The Python service remains the reference implementation
   until parity tests pass.
3. **Single-writer arbitration:** add an explicit ownership handshake for the
   fixed AbletonOSC response port. A C++ path may proceed only when the KENN
   companion is absent and ownership is acquired; it must fail closed if the
   port is already owned or the Remote Script contract is unknown.
4. **Controlled activation:** initially expose only read-only inspection and
   proposal display from the self-contained path. Enable writes behind a
   developer feature flag only after real disposable-set confirmation,
   readback, replay rejection, undo, timeout recovery, and Live-loss tests
   match the Python evidence.
5. **Packaging:** ship the local companion as an optional auto-start helper,
   so normal users get one-click operation immediately while the deeper C++
   migration is being qualified. No LLM, AudioGen, AutoMix, or filesystem
   operation is allowed to bypass the shared mutation contract during this
   migration.

The current implementation has completed the first foothold of step 1 and
started step 2: a standard-OSC codec, direct count/name probe, batched topology
reader with echoed-index matching, loopback qualification, and companion
fallback in the plug-in's Test and read-only Live-controls actions. A pure C++
plan model now resolves allow-listed append-device requests against exact track
and device identity, records the append index and before/after lists, and emits
the same canonical snapshot fingerprint used by the Python boundary. Duplicate
and unsupported actions fail closed. The plug-in command path now displays this
plan when the HTTP companion is absent but direct AbletonOSC topology is
available; the UI explicitly keeps the local-only plan non-confirmable. It
also has a bounded exact-device parameter reader and planner for current value,
range, sparse index, absolute dB, and relative dB checks. A separately tested
guarded OSC writer now has product-level confirmation, receipt, and identity-
bound undo scaffolding behind `KENN_ENABLE_DIRECT_LIVE_WRITES`; the default
build keeps that flag off. It performs fresh preflight, stale-before rejection,
one parameter write, and post-write readback in loopback tests, but real direct
Live mutation still awaits disposable-set qualification. Until that gate is
passed, the companion remains the write authority and the self-contained path
is read/plan-only.

A 2026-09-05 hardening pass found that the native CTest suite's assertions had
been silently disabled by `-DNDEBUG` in Release builds (the same configuration
used to build the installed plug-in), so several real defects in this
self-contained path had never actually been checked. Once fixed to always
evaluate, testing uncovered and fixed: a local-parser bug where the numbered
track reference could be mistaken for the requested volume value; a missing
verb sign for relative device-parameter changes (`reduce ... by` moved the
value the wrong way); and a genuine, previously invisible reliability gap in
the batched read-only OSC exchange (`exchangeQueries`) where a lost or
delayed reply could leave a topology/parameter snapshot incomplete roughly
10-15% of the time under repeated use. The exchange now resends exactly the
still-missing read-only queries once before reporting failure, which is safe
(idempotent, no side effects) and eliminated the failure in stress testing
(0/40 CTest runs failed afterward, versus frequent failures before the fix).
See `docs/ABLETON_ASSISTANT_CURRENT_STATE.md` for the full account.
