# KENN: LLM-Controlled GLM-Style Ableton Product

Status: implementation blueprint
Date: 2026-09-02
Decision: build toward an internal Ableton assistant beta first; do not call it a finished autonomous mixing engineer until real-Live evidence, evaluation results, and rollback behaviour support that claim.

## 1. Product definition

KENN should become a product that combines the conversational usefulness of an LLM with the deterministic behaviour of a hardware-style GLM: it observes the current Ableton session, understands a user's production request, explains what it sees, proposes a bounded action, waits for permission, changes only the exact target, verifies the result, and makes the action reversible.

The important distinction is:

```text
LLM = interprets language, explains evidence, proposes intent
KENN = owns state, safety, schemas, permissions, execution, verification, undo
AbletonOSC = transport and Live object access
C++ plug-in = low-latency local meters, UI, and optional real-time DSP
Python companion = orchestration, analysis, retrieval, policy, and HTTP/OSC gateway
```

KENN must never allow the language model to write directly to Ableton, call arbitrary OSC addresses, invent track/device indices, or claim success without a fresh readback.

The target user experience is:

> “Make the vocal less harsh.”

KENN should answer:

1. What evidence is available?
2. What does that evidence suggest?
3. What should the user listen for?
4. Which exact track/device/parameter would be changed?
5. What is the current value and proposed value?
6. May KENN apply this one reversible change?
7. Did Ableton confirm the new value?
8. How can the user undo it?

That is the GLM-like loop: observe → reason → propose → confirm → act → verify → learn.

## 2. Current position and immediate truth

The current repository already contains substantial foundations:

- an AbletonOSC route and vendored upstream Remote Script;
- a KENN companion server;
- a C++ VST3 plug-in with local meter/UI work;
- deterministic Ableton snapshot and action services;
- confirmation tokens, stale-state checks, idempotency, readback, receipts, and undo concepts;
- natural-language intent parsing for a small supported action set;
- audio analysis, Mix Review, retrieval, chat, evaluation, and beta documentation;
- test doubles and real-Live qualification scripts.

The current real-Live milestone has also demonstrated an important fact: the KENN path can reach Ableton through AbletonOSC and can write an EQ Eight device parameter with readback verification. The remaining work is to make this reliable, understandable, easy to operate, well-tested, and broad enough to feel like a product rather than a successful one-off command.

The current qualification also exposed and closed an undo-route dispatch bug:
device-parameter undo now reaches the schema-specific executor and is covered
by regression and real-Live qualification. Also improve clarification for
vague requests such as “change band 2 to the EQ Eight setting of .99”: “band
2” does not identify A or B, and “setting” does not identify gain, frequency,
Q, or another parameter.

Do not lose sight of these facts:

- the local companion is currently part of the control path;
- the C++ plug-in cannot independently control Ableton’s track/device graph without a host integration path;
- AbletonOSC is the current practical control transport;
- real-time audio processing must never wait on an LLM, HTTP request, disk operation, or OSC round trip;
- “GLM-like” is a product behaviour and safety model, not a claim that KENN is a literal hardware GLM implementation.

## 3. North-star architecture

### 3.1 Five planes

Build KENN as five explicit planes with narrow contracts.

#### Plane A: real-time audio plane

Owned by the C++ plug-in.

- sample-accurate metering where practical;
- peak, RMS, crest, clipping, correlation, width, and short-window spectral features;
- lock-free or bounded messaging from audio thread to UI;
- no network calls;
- no allocations or blocking locks in `processBlock`;
- no LLM calls;
- no mutation of the Live session;
- clear offline behaviour when the companion is absent.

#### Plane B: Live state plane

Owned by the Python companion plus AbletonOSC.

- connection health;
- current Live snapshot;
- track/device/parameter inventory;
- fresh state timestamp and session fingerprint;
- OSC request/reply correlation;
- bounded timeouts;
- transport and readback diagnostics.

#### Plane C: intelligence plane

Owned by Python orchestration with optional local or hosted LLM support.

- intent extraction;
- retrieval from approved audio knowledge;
- evidence interpretation;
- Ableton-specific explanation;
- constrained plan generation;
- clarification and refusal;
- conversation memory that never becomes authority over Live state.

#### Plane D: safety and action plane

Owned by typed KENN services.

- action allowlist;
- exact target binding;
- explicit confirmation;
- range and unit validation;
- stale-state rejection;
- idempotency;
- one-write policy;
- readback verification;
- receipt creation;
- undo proposal and execution;
- audit log.

#### Plane E: product/UI plane

Owned by the VST3 editor and companion UI.

- clear connection status;
- evidence display;
- command entry;
- proposal cards;
- confirmation controls;
- execution status;
- readback value;
- undo;
- failure explanation;
- no fake controls for disabled features.

### 3.2 Message flow

```text
User speech/text
      ↓
Command gateway
      ↓
Snapshot + retrieval + analysis evidence
      ↓
LLM or deterministic planner
      ↓
Typed KENN plan
      ↓
Validator / policy / exact target resolver
      ↓
Human-readable proposal
      ↓ explicit confirmation
LiveActionService
      ↓
AbletonOSC request
      ↓
Fresh readback
      ↓
Receipt + undo + UI history
```

The LLM may produce only a plan-shaped JSON object. The host must validate the plan against a fresh snapshot before a proposal exists. A proposal must be generated by KENN, not copied untrusted from model output. Execution must accept only a proposal whose confirmation token is bound to its exact contents.

## 4. Product modes

Implement the modes as visible state, not just prompt language.

### Ask

Grounded audio-engineering answers. No Live mutation.

### Inspect

Read-only current Live or audio state. Every answer states its source and freshness.

### Analyse

Deterministic analysis of an attached audio file or plug-in meter stream.

### Suggest

Evidence-backed recommendations with a listening test and Ableton workflow.

### Assist

One exact, reversible proposal. No mutation yet.

### Execute

Confirmed proposal only. Always read back and receipt.

### Auto

Disabled by default. A future Auto mode may automate only a pre-authorised bounded recipe, with a maximum change count, maximum parameter delta, stop conditions, and a complete action log. It must not be general “make it better” autonomy.

## 5. Command language and LLM contract

### 5.1 Human command grammar

Support a small reliable grammar first:

- `list tracks`;
- `what devices are on track 4`;
- `mute track 4`;
- `solo track 4`;
- `set track 4 volume to -6 dB`;
- `pan track 4 20% left`;
- `lower Compressor threshold by 2 dB on track 4`;
- `set EQ Eight 2 Gain A to -3 dB on track 4`;
- `reduce EQ Eight band 2A gain by 3 dB on track 4`;
- `play` and `stop`;
- `undo the last KENN change`.

Clarify these instead of guessing:

- `band 2` without A/B;
- `the EQ setting` without a parameter;
- `make it better`;
- duplicate track names;
- missing track numbers;
- device names not present in the snapshot;
- values without units where the parameter has multiple meaningful units;
- compound commands such as “make the vocal brighter, compress it, and widen it.”

### 5.2 LLM plan schema

Keep one versioned schema:

```json
{
  "schema": "kenn.ableton_llm_plan.v1",
  "action": "set_device_parameter",
  "track_index": 3,
  "track_name": "4-Audio",
  "device_index": 1,
  "device_name": "EQ Eight",
  "parameter_index": 17,
  "parameter_name": "2 Gain A",
  "value": -3.0,
  "relative": false,
  "unit": "dB",
  "frequency_hz": 200.0,
  "eq_band": "2A",
  "clarification": null
}
```

The model must use only names and indices present in the supplied snapshot. It must use `clarify` when any exact field is absent or ambiguous. The model must never claim that a write happened. The host owns all validation, proposal generation, confirmation, execution, and truth claims.

### 5.3 Response contract

Every command response should expose:

- `status`: inspected, clarification_required, proposed, applied, failed, offline, refused;
- `changed`: boolean;
- `answer`: concise user-facing explanation;
- `intent`: parsed intent;
- `proposal`: only when an exact proposal exists;
- `execution`: only after an attempted write;
- `receipt`: only after a write attempt;
- `sources` and `evidence` where relevant;
- `freshness`: snapshot timestamp and session version;
- `undo_available`: boolean;
- `limitations` when the system abstains.

## 6. Safe Live action model

### 6.1 Initial action allowlist

Release in this order:

1. inspect tracks;
2. inspect devices;
3. inspect parameters;
4. mute, solo, arm;
5. volume and pan;
6. play and stop;
7. one explicitly validated device parameter;
8. EQ Eight gain with exact band identity;
9. EQ Eight frequency and Q only after dedicated calibration;
10. device insertion only when append-only and allow-listed;
11. multi-parameter or batch recipes only after atomicity and rollback tests.

Keep disabled until qualified:

- delete/remove/overwrite;
- arbitrary device insertion;
- clip or scene launch;
- tempo mutation;
- routing changes;
- sidechain creation;
- track creation/deletion;
- project save/overwrite;
- unattended Auto mode;
- actions that cannot be read back accurately.

### 6.2 Proposal requirements

Every proposal must include:

- exact track index and name;
- exact device index and name;
- exact parameter index and name;
- before value;
- after value;
- unit and valid range;
- relative/absolute semantics;
- reason;
- evidence;
- confidence;
- risk;
- session fingerprint/version;
- timestamp and expiry;
- confirmation token metadata;
- idempotency key;
- undo source information.

### 6.3 Execution requirements

Execution must:

1. check the feature policy flag;
2. verify the proposal schema;
3. verify the exact confirmation token;
4. reject expired or replayed tokens;
5. reject duplicate idempotency keys;
6. request a fresh snapshot;
7. verify track/device/parameter identity;
8. verify the before value still matches;
9. validate the requested value and range;
10. send exactly one mutation;
11. read the parameter back;
12. compare readback to the requested value using a documented tolerance;
13. create a receipt regardless of success or failure;
14. expose undo only for verified applied receipts.

The undo route must dispatch by proposal schema. Track/transport proposals use the generic executor; device proposals use the device executor; insertion/removal proposals use their typed executors. Add a regression test for this exact bug.

### 6.4 Receipts

Receipts are the product’s trust mechanism. Include:

- action and proposal IDs;
- exact target;
- before/requested/readback values;
- OSC request/reply metadata;
- verification result;
- error, if any;
- timestamp;
- source session fingerprint;
- undo proposal reference.

Persist receipts in a bounded local journal so a companion restart does not erase the user’s visible action history. Never persist confirmation secrets in plain text. A restart should invalidate pending proposals unless they can be safely revalidated from a fresh snapshot. **Implemented locally:** a bounded non-secret receipt projection and read-only receipt-history endpoint; pending tokens remain process-bound.

## 7. LLM intelligence strategy

Use a hybrid architecture rather than asking one model to do everything.

### Deterministic code should own

- WAV parsing;
- FFT and meter calculations;
- unit conversion;
- Live snapshots;
- target resolution;
- parameter ranges;
- safety policy;
- confirmations;
- OSC calls;
- readback;
- receipts;
- undo;
- evaluation accounting.

### Retrieval should own

- approved audio-engineering facts;
- Ableton workflow notes;
- device parameter documentation;
- KENN-specific limitations;
- citations and provenance.

### The LLM should own

- language variation;
- intent interpretation;
- explanation;
- evidence-to-hypothesis translation;
- concise clarification questions;
- plan generation constrained to the supplied schema.

Do not fine-tune first. First build a held-out evaluation set and measure whether the LLM improves intent classification, clarification quality, and explanations over deterministic parsing and retrieval. Add a local model only after the contracts are stable. The model can be swapped without changing Live safety code.

### 7.1 Local model qualification before KENN fine-tuning

The repository now has a shadow-only command-planning mode. Use it to qualify
an open-weight local model before creating a KENN-specific adapter:

```text
AUDIO_TOO_LLM_ENABLED=1
AUDIO_TOO_LLM_PROVIDER=ollama
AUDIO_TOO_LLM_MODEL=<installed-model>
KENN_LIVE_LLM_ENABLED=1
KENN_LIVE_LLM_MODE=shadow
```

Each shadow result must record model name, latency, JSON/schema validity, exact
track/device/parameter identity, typed-value accuracy, clarification accuracy,
and agreement with the deterministic parser. A valid JSON response is not
enough: a missing track name, wrong index convention, wrong value type, or
invented target is a failed command-plan result. The model remains unable to
create or execute a Live write in this mode.

The first local probes on 2026-09-02 established a useful baseline: the
installed 0.5B Qwen model was fast but semantically unsafe for the command
contract, producing 0/10 accepted plans on the initial fixed corpus at a warm
mean of 1.262 seconds. The installed 7B instruct model selected the right
action in one probe but took about 50 seconds and omitted required identity
fields. The next qualification should use a larger held-out command set and
warm-model latency, then compare a compact fine-tuned KENN command adapter
against these baselines.

Do not train a full language model from scratch. If a specialised KENN model
earns its place in evaluation, start with a parameter-efficient adapter for
intent/slot extraction and clarification. Keep audio neural networks as a
separate evidence-producing subsystem; neither model may bypass the typed
snapshot, confirmation, readback, receipt, or undo boundary.

The first local one-epoch LoRA pilot was intentionally stopped after it failed
to produce an artifact on the development machine in roughly seven minutes.
That result changes the deployment boundary, not the product direction:
training belongs in an offline, reproducible job on dedicated compute, while
the KENN bridge remains a small inference-and-control service. The bridge must
load only a reviewed, versioned adapter and must never train, download model
weights, or compete with Ableton's control path at runtime. The next training
attempt should use a batched/collated loop or a supported accelerator trainer,
then run the complete held-out shadow evaluator before any adapter is exposed
to live proposals.

### 7.2 AudioCraft: optional, license-gated audio research

AudioCraft is not currently integrated into KENN. It may be useful as a
research reference for EnCodec-style tokenisation and audio-generation
experiments, or as a separately isolated sound-design feature. It is not a
replacement for the KENN command model or the evidence-producing audio
analysis network.

The integration decision must distinguish repository code from pretrained
weights: Meta releases the AudioCraft code under MIT, while the released model
weights are under CC-BY-NC 4.0. Do not ship those weights in a commercial KENN
product without a separate licensing review. A commercial KENN audio model
should instead use code whose license is acceptable for the intended
distribution and weights trained on data with documented rights.

If AudioCraft is explored, keep it behind an offline, opt-in experiment
boundary. Generated audio must not be imported into Ableton or used as Live
control input without its own explicit confirmation, provenance, and rollback
path. The command model, Live safety service, and real-time C++ audio thread
must not depend on AudioCraft.

## 8. Audio intelligence roadmap

### 8.1 Baseline measurements

Implement and version:

- sample peak;
- RMS;
- crest factor;
- clipping and clipped runs;
- silence percentage;
- DC offset;
- duration, sample rate, bit depth, channels;
- left/right RMS difference;
- correlation;
- mid/side energy;
- mono-sum level and cancellation risk;
- windowed FFT;
- band energy;
- dominant peaks with frequency, level, bandwidth, and confidence.

### 8.2 Interpretation rules

A peak is evidence of spectral energy, not proof of a bad mix. Each finding must contain:

- measured fact;
- possible interpretation;
- alternative explanation;
- listening test;
- bounded Ableton workflow;
- confidence;
- limitation.

Examples:

- “There is elevated energy around 250 Hz” is a fact.
- “This may contribute to muddiness” is a hypothesis.
- “Check the vocal and bass together before cutting” is a listening test.
- “Try a narrow, small EQ cut only after confirming” is a workflow, not an automatic command.

### 8.3 Calibration fixtures

Use deterministic fixtures for pure sine, harmonics, white noise, pink-like noise, two-tone masking, silence, clipping, mono cancellation, inverted polarity, short files, corrupt files, mono/stereo, sample-rate changes, and 16/24-bit PCM. Report frequency error relative to FFT-bin width and amplitude error relative to a documented windowing/calibration method. Do not label RMS as LUFS or sample peak as true peak.

## 9. C++ and Python boundary

C++ is valuable where timing is continuous and local: meters, UI responsiveness, FFT windows, spectral feature extraction, and future plug-in DSP. Python is valuable where work is orchestration-heavy: LLM calls, retrieval, policy, HTTP, OSC, file analysis, and experiment/evaluation tooling.

Use C++ for:

- audio-thread-safe metering;
- local FFT and feature windows if benchmarks justify it;
- low-jitter event aggregation;
- plug-in UI model and connection state;
- a future local IPC client only if it never blocks audio processing.

Use Python for:

- AbletonOSC protocol handling;
- snapshot and action services;
- command parsing and LLM planning;
- confirmation/receipt journal;
- uploaded-file analysis jobs;
- retrieval and citations;
- test fixtures and evaluation.

Do not move OSC, HTTP, or LLM calls into the C++ audio thread. C++ will not remove the network/companion round trip from Ableton control; it can reduce plug-in-local latency and make the UI/meter path smoother. The product should report separate timings for audio-thread meter latency, UI update latency, command-planning latency, OSC round trip, and verified-readback latency.

## 10. UI/product upgrades

Replace ambiguous “ask/control” behaviour with visible cards:

### Connection card

- Ableton status;
- AbletonOSC status;
- companion status;
- last snapshot time;
- session ID;
- reconnect/test controls.

### Inspection card

- tracks and device chain;
- selected track;
- parameters with units and ranges;
- freshness warning.

### Proposal card

- “I found” exact target;
- before → after;
- reason and evidence;
- risk and scope;
- Confirm / Cancel.

### Applied card

- applied value;
- readback value;
- verified/not verified;
- receipt ID;
- Undo.

### Failure card

- what was attempted;
- whether a write may have happened;
- readback result;
- safe next action;
- no false success language.

The plug-in should work offline for meters and local analysis. Chat and Live control should show that the companion is optional for local meters but required for LLM, retrieval, and OSC operations. Avoid presenting a server-dependent command as a native plug-in feature until the companion lifecycle is made automatic and observable.

## 11. Evaluation programme

Create held-out JSONL cases for:

- beginner, intermediate, and expert audio questions;
- audio-analysis requests;
- Ableton inspection;
- supported actions;
- ambiguous actions;
- stale and unavailable Live state;
- unsupported/destructive commands;
- prompt injection in filenames, metadata, knowledge notes, and track names.

Score independently:

- intent accuracy;
- slot accuracy;
- exact target accuracy;
- clarification accuracy;
- action safety;
- stale-state rejection;
- confirmation integrity;
- readback verification;
- undo success;
- factual/audio-engineering correctness;
- evidence support;
- citation correctness;
- uncertainty quality;
- practical Ableton usefulness;
- latency;
- resource usage.

Release gates should include:

- ≥95% correct intent classification for supported actions;
- ≥99% correct abstention/clarification for ambiguous or unsupported actions;
- zero unauthorized real-Live mutations;
- zero false successful-execution claims;
- zero claims of inspecting absent audio or absent Live state;
- 100% receipt creation for attempted mutations;
- 100% replay rejection;
- 100% stale-target rejection in the qualified test suite;
- documented real-Live pass rate for each action, not one aggregate claim.

Report category-level results. Never report “100% intelligent” because a fixture passed.

## 12. Reliability and recovery

Test:

- Ableton not running;
- Live set loading;
- Remote Script missing;
- wrong OSC port;
- duplicate bridge;
- delayed reply;
- dropped reply after a possible write;
- stale snapshot;
- parameter changed manually between proposal and execution;
- Ableton crash/restart;
- companion restart;
- plug-in reload;
- duplicate user click;
- malformed model plan;
- corrupted audio file;
- oversized upload;
- simultaneous commands.

On uncertain write outcomes, do not blindly retry. Re-inspect the exact target first. If the result is unknown, tell the user that the write outcome is uncertain and show the readback. A safe retry must require a new proposal based on current state.

## 13. Delivery phases

### Phase 0: close the current qualification loop — complete

- fix device undo dispatch;
- add route-level regression coverage;
- improve vague EQ-setting clarification;
- restore the disposable test parameter to its original value;
- restart and verify the current server/Remote Script path;
- record real evidence in the qualification report;
- qualify real insertion replay rejection and identity-bound undo;
- qualify the explicit two-parameter EQ retune and restore the disposable set.

The remaining work is no longer the first mutation loop. The next phase is
broader device-matrix coverage, repeated supported Live/OS qualification, and
independent human review before any wider beta claim.

### Phase 1: dependable read-only product

- automatic companion health check;
- fresh Live snapshot UI;
- inspect tracks/devices/parameters;
- local meter and audio analysis;
- clear offline states;
- support runbook that a user can follow without developer knowledge.

### Phase 2: dependable single actions

- volume, pan, mute, solo, arm, play/stop;
- exact proposal cards;
- receipt journal;
- undo;
- replay and stale-state tests;
- real-Live qualification for each operation.

### Phase 3: EQ Eight and device intelligence

- exact band A/B language;
- gain first;
- frequency and Q after calibration;
- device parameter display/ranges;
- deterministic parameter aliases only when bound to snapshot names;
- no “setting” shorthand that hides the actual parameter.
- explicit one-based device-chain targeting when a track contains duplicate
  device names; generic requests must still clarify rather than guess.

### Phase 4: LLM planner and GLM-like interaction

- constrained plan schema;
- local model option;
- retrieval-grounded explanations;
- held-out evaluation;
- clarification and refusal quality;
- voice input only after text command correctness is high.

### Phase 5: multi-step recipes

- one-to-three-step recipes;
- preview every step;
- maximum delta and maximum action count;
- per-step readback;
- rollback strategy;
- stop on first failure;
- no arbitrary autonomous editing.

### Current next execution slice — 2026-09-03

The first GLM-like vertical slice is now live-qualified through proposal,
confirmation, readback, replay rejection, and undo for the documented EQ
Eight paths. The immediate next work is to qualify one reversible parameter
from each additional supported device family, with exact device selection and
read-only parameter discovery. After that evidence is green, introduce a
bounded recipe envelope of at most three typed actions: preview every step,
require one explicit confirmation for the exact recipe, verify each step,
stop on the first failure, and restore completed steps on rollback. The local
LLM may produce the typed recipe proposal, but it must not send OSC or bypass
the deterministic KENN service.

The bounded recipe proposal/execution component is now implemented and
fake-Live tested, including successful two-step application and rollback after
a partially written step. The real companion has also accepted a typed LLM
recipe and returned a confirmation-only proposal. A corrected real two-step
qualification then passed both writes, replay rejection, inverse recipe, and
final restoration for the narrow `4-Audio` pan plus existing EQ Eight gain
shape. This does not qualify arbitrary recipes, and hosted plug-in UI
verification remains open.

### Phase 6: internal Ableton beta

- fresh-set test procedure;
- supported-action matrix;
- tester feedback;
- crash/restart recovery;
- latency/resource report;
- known-issues list;
- rollback runbook.

### Phase 7: public product decision

Evaluate web Mix Review and Ableton integration separately. A public web beta does not prove Ableton readiness. An internal Live pass does not prove public privacy, rate-limit, deployment, or support readiness.

## 14. Definition of done

KENN is ready for an internal Ableton beta when:

- a fresh user can install/start the companion and Remote Script;
- the UI visibly reports connection state;
- read-only inspection is reliable;
- each supported action has real-Live evidence;
- every mutation is confirmed, exact, verified, receipted, and undoable;
- failures do not claim success;
- ambiguous commands clarify;
- unsupported/destructive commands refuse;
- test fixtures and held-out evaluations pass their stated gates;
- the C++ plug-in remains real-time safe;
- the support and rollback procedures work from a clean machine.

The correct readiness label is one of `not ready`, `internal Ableton beta`, `public beta with restrictions`, or `public beta ready`. The evidence chooses the label.

## 15. Mega prompt for the KENN autonomous lead engineer

Use the following as the master implementation prompt for a future KENN build/review run. It is deliberately strict: it asks the agent to improve the product, but not to hide uncertainty or bypass the safety boundary.

```text
You are the autonomous lead engineer, audio DSP engineer, Ableton Live integration engineer, LLM product engineer, evaluation lead, QA lead, security engineer, and product owner for KENN.

Mission: turn KENN into a genuinely useful Ableton-focused audio assistant with the interaction quality of an LLM and the deterministic safety and state awareness of a GLM-style product.

Repository: <LOCAL_VOLUME>/Shenrendao/KENN

Work as an evidence-driven engineer. Inspect the repository, current diffs, tests, runtime, Ableton connection, and actual installed integration before making claims. Preserve all user changes. Never reset, force-push, rewrite history, overwrite Ableton projects, delete audio, or broaden permissions without explicit authorisation. Never add AI tags to commit messages or source metadata. Do not commit or push unless explicitly requested.

Product loop:
  observe → analyse → explain → propose → explicit confirm → execute → read back → receipt → undo

Hard truth rules:
  - Never claim to have heard audio that was not attached and analysed.
  - Never claim Ableton is connected without a fresh successful snapshot.
  - Never let an LLM call an OSC address or mutation function directly.
  - Never invent a track, device, parameter index, range, or value.
  - Never mutate without explicit confirmation bound to the exact proposal.
  - Never report success without verified readback.
  - Never retry an uncertain write blindly; re-inspect first.
  - Clarify ambiguous targets, A/B EQ bands, units, devices, and parameters.
  - Refuse delete, remove, overwrite, destructive, and unsupported operations.
  - Keep Auto mode disabled unless every separate safety gate is met.

Architecture:
  1. Keep C++ responsible for real-time-safe plug-in metering, UI state, and optional local DSP.
  2. Keep Python responsible for HTTP, AbletonOSC, orchestration, retrieval, analysis jobs, policy, receipts, and evaluation.
  3. Never perform HTTP, OSC, LLM, disk, or blocking operations on the C++ audio thread.
  4. Treat Ableton's current snapshot as the authority for all Live names and indices.
  5. Treat KENN's typed action service as the only mutation boundary.

Operating modes:
  Ask, Inspect, Analyse, Suggest, Assist, Execute, Auto.
  Make the mode visible in the UI and in every response.

Required supported commands:
  - list tracks;
  - inspect devices and parameters;
  - mute, solo, arm;
  - set volume and pan;
  - play and stop;
  - one exact device parameter;
  - exact EQ Eight band gain using A/B identity;
  - undo the last verified KENN action.

For every command:
  1. capture a fresh snapshot;
  2. parse action, track, device, parameter, value, relative/absolute meaning, unit, confidence, and ambiguity;
  3. use a constrained JSON plan if an LLM is enabled;
  4. validate that plan against the current snapshot;
  5. clarify instead of guessing;
  6. generate a typed proposal containing exact target, before, after, range, unit, reason, evidence, risk, timestamp, session version, expiry, and undo data;
  7. wait for explicit confirmation;
  8. execute exactly once through the typed service;
  9. read back the exact target;
  10. create a receipt and expose undo only when verified.

LLM plan schema:
  kenn.ableton_llm_plan.v1 with action, exact track/device/parameter identity, typed value, relative flag, unit, optional EQ band/frequency, and clarification. The LLM may describe a plan only. It may not claim execution.

Live action safety:
  - use schema-specific executors;
  - device parameter undo must use the device executor;
  - insertion/removal undo must use their typed executors;
  - generic executor is only for track/transport proposals;
  - enforce confirmation tokens, expiry, session binding, idempotency, exact identity, stale before-value, valid ranges, one-write behaviour, readback tolerance, receipts, and undo;
  - persist a bounded non-secret receipt journal so a restart does not erase action history;
  - invalidate or revalidate pending proposals after restart.

Audio analysis:
  Implement auditable versioned WAV analysis for sample peak, RMS, crest factor, clipping, silence, DC offset, duration, sample rate, channels, left/right balance, correlation, width, mono cancellation, mid/side energy, FFT peaks, band energy, and confidence. Distinguish sample peak from true peak and RMS from LUFS. Use fixtures for sine, harmonics, noise, masking, phase cancellation, clipping, silence, corrupt files, short files, sample rates, bit depths, mono, and stereo. Every finding must distinguish fact, interpretation, alternative cause, listening test, Ableton workflow, confidence, and limitation.

Evaluation:
  Create held-out cases for audio questions, Live inspection, supported actions, ambiguity, unavailable Live, stale state, unsupported/destructive requests, and prompt injection through filenames, metadata, knowledge notes, and track names. Measure intent accuracy, slot accuracy, exact-target accuracy, clarification accuracy, safety, stale rejection, confirmation integrity, readback, undo, engineering correctness, evidence support, citation correctness, latency, and resources. Report category-level results. Never claim “100% intelligent.”

Engineering process:
  - inspect git status and current diffs first;
  - run the relevant tests before editing;
  - make the smallest safe implementation;
  - add regression tests for every bug;
  - qualify mocks and real Ableton separately;
  - rebuild/reload only the components needed;
  - run the real-Live test procedure on a disposable set;
  - record exact evidence and limitations in docs;
  - do not hide failures by weakening tests or changing labels;
  - finish with exact commands to install, build, test, start, connect, inspect, confirm, undo, and roll back.

Immediate priorities for this repository:
  1. fix and test device-undo route dispatch;
  2. complete restoration of the disposable EQ test value and verify 0 dB readback;
  3. make vague wording such as “EQ Eight setting” produce a useful clarification;
  4. qualify the standard AbletonOSC path on a fresh Live set;
  5. add route-level and real-Live evidence to the readiness report;
  6. improve the proposal UI;
  7. expand one supported action at a time;
  8. only then enable a constrained LLM planner and evaluate whether it improves results.

At the end of each run, state:
  - what changed;
  - what was tested;
  - what was verified against real Ableton;
  - what remains disabled;
  - known failure modes;
  - exact next milestone;
  - whether the evidence supports not ready, internal Ableton beta, public beta with restrictions, or public beta ready.
```

## 16. First execution command set

Use these as the first practical runbook sequence after saving this plan:

```bash
cd <LOCAL_VOLUME>/Shenrendao/KENN
git status --short
PYTHONPATH=source python3 -m pytest -q
PYTHONPATH=source python3 scripts/test_kenn_live_queries.py
PYTHONPATH=source python3 scripts/qualify_ableton_live.py
```

For a disposable real-Live mutation qualification, enable the DAW write policy only for that session, inspect first, confirm one exact proposal, verify readback, then undo and verify again. Keep the companion and AbletonOSC logs available. Do not test destructive or multi-step mutation until the single-action lifecycle passes repeatedly.

## 17. Final product principle

KENN becomes “like a GLM controlled by an LLM” when the user experiences confident, low-friction, state-aware assistance while the system remains conservative underneath. The magic should be in the explanation and workflow; the trust should come from exact state, typed actions, explicit permission, verified readback, and undo.
