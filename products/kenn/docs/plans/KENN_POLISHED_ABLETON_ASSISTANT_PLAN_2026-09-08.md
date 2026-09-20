# KENN polished Ableton assistant plan

**Date:** 2026-09-08
**Current baseline (2026-09-11):** supervised-pilot-ready engineering candidate; 1,186 source-bound tests passing; qualified-beta gate 5/14 passed, 2 failed, 7 pending. One temporary failure is the human-review packet predating the latest answer-engine source; the other is a stale real-Live assistant receipt bound to an older source/planner revision. The remaining pending gates are external evidence, release, or explicitly deferred qualification work.
**Product target:** a polished, broadly dependable Ableton assistant that understands the current set, gives musically useful and evidence-backed advice, safely carries out bounded work, learns from supervised outcomes, and remains honest when it does not know
**UX ownership:** out of scope here; a colleague owns interaction and visual design. This plan owns intelligence, Ableton capabilities, safety, evaluation, reliability, packaging inputs, and backend contracts supplied to that UX.

## 1. What “polished and broadly dependable” means

KENN is ready for this claim only when all five properties hold together:

1. **Session understanding:** it can form a fresh, versioned model of the Live
   set—tracks, roles, devices, routing, clips, transport, and relevant measured
   audio evidence—without silently inventing missing facts.
2. **Musical usefulness:** experienced producers judge its priorities,
   explanations, and suggestions useful across varied genres and real projects,
   not merely correct on synthetic fixtures.
3. **Safe action:** every Live write has an exact target, explicit proposal,
   confirmation, stale-state check, readback, receipt, replay protection, and
   honest undo or declared non-reversibility.
4. **Operational dependability:** startup, reconnects, long sessions, failures,
   upgrades, and support evidence behave predictably on supported machines.
5. **Learning discipline:** feedback changes KENN only through reviewed data,
   versioned evaluation, and measurable promotion gates. A model is never
   trained merely because training is possible.

The product claim remains **“LLM-assisted, confirmation-gated Ableton
assistant”**. Broadly dependable does not mean autonomous, infallible, or safe
to make destructive changes without review.

## 2. Current baseline and remaining distance

### Proven today

- One guarded mutation boundary for Live actions.
- Fresh snapshot identity, exact target resolution, confirmation tokens,
  idempotency, verified readback, receipts, and identity-bound undo.
- Model-planned bounded trajectories with deterministic validation and fallback.
- Qualified Qwen planner evidence, including repeated safety and latency runs.
- Grounded retrieval and session-aware advice benchmarks.
- Mix Review measurements with explicit evidence and abstention.
- Reconnect-aware soak machinery, bounded runtime registries, private support
  bundles, and fail-closed release gates.
- A provider-neutral path for future specialist classifiers and generators.
- Append-only MIDI-track creation is now implemented as a guarded backend
  capability: optional naming, topology binding, confirmation, idempotency,
  MIDI-type readback, and an explicit non-reversible receipt. Real-Live
  qualification remains outstanding.
- Append-only return-track creation is now implemented as a guarded backend
  capability: optional naming, complete return-topology binding, confirmation,
  idempotency, count/index/name readback, and an explicit non-reversible
  receipt. The capability remains disabled for real-Live promotion until the
  vendored Remote Script is reloaded and a disposable-set lifecycle passes.
- Bounded MIDI note revision is now implemented as a guarded backend capability:
  complete note-set replacement on one exact existing MIDI clip, intentional
  empty-note support, confirmation, stale note/length/identity checks,
  authoritative clear/final readback, interruption-aware receipts, replay
  protection, and identity-bound undo that restores the prior notes. Real-Live
  qualification remains outstanding.
- AudioGen listener revisions now use that bounded replacement path: feedback
  stays bound to the audition receipt and exact clip fingerprint, while the
  generated MIDI artifact remains digest- and Live-context-bound. Fresh
  non-revision AudioGen ideas still use empty-slot creation. Real-Live
  qualification remains outstanding.
- The disposable real-Live qualification runner now exercises both non-empty
  MIDI note replacement and intentional note clearing, with replay rejection,
  verified identity-bound undo, and final restoration checks. The cases remain
  unqualified until they run against the current Live set.
- The full mutation qualification runner is companion-safe: real checks use the
  existing HTTP proposal/apply/undo boundary and never open a competing
  AbletonOSC reply socket. A live offline probe returns a structured block;
  connected-session qualification is still required.

### Not yet proven

- Two independent human reviewers and adjudication for assistant answers.
- Signed, notarized, clean-host-tested AU and VST3 distribution.
- One current-source, model-planned lifecycle against real Live.
- One current-source/current-harness 24-hour soak with an observed reconnect.
- A consented 12+ case, two-reviewer real-mix evaluation.
- Ten supervised sessions spanning at least three projects.
- Broad musical usefulness across genres, arrangements, and imperfect projects.
- Enough reviewed real-session failures to justify or safely evaluate LLM
  fine-tuning.
- Real-Live qualification of the new MIDI-track creation path, including
  default and named-track cases, interruption/reconciliation, and final-set
  restoration review.
- Real-Live qualification of return-track creation, including empty/non-empty
  return sets, default and named cases, interruption/readback uncertainty, and
  final-set routing/restoration review. Automatic deletion remains outside the
  safe inverse boundary.
- Real-Live qualification of MIDI note revision, including non-empty and empty
  replacements, acknowledgement loss/partial-write recovery, stale-state
  refusal, verified undo, and final-set restoration review.

## 3. Maturity ladder

| Level | Product state | Evidence required |
|---|---|---|
| L0 | Engineering prototype | Unit and integration behavior only |
| L1 | Supervised pilot | Current preflight; bounded actions; explicit operator supervision |
| L2 | Qualified private beta | All 14 existing release gates pass on one exact candidate |
| L3 | Dependable assistant beta | 50+ varied sessions, usefulness thresholds, capability coverage, reliability SLOs, no unresolved high-severity safety incident |
| L4 | Polished assistant | 200+ sessions, cross-genre evaluation, calibrated confidence, mature recovery/support, measurable feedback improvements, release-grade packaging |

No number of features can substitute for a failed safety, provenance,
reliability, or human-evaluation gate.

## 4. Programme structure

The work is divided into seven programmes. Programmes overlap, but capability
promotion is sequential: implement → adversarial test → shadow use → supervised
real-Live qualification → pilot evidence → default availability.

## Programme A — close qualified private beta

**Priority:** P0
**Target window:** next 1–3 weeks, depending on people, Live availability, and signing credentials

### Deliverables

1. Complete independent human review and adjudication against the current
   packet.
2. Produce Developer ID signed/notarized AU and VST3 archives and validate the
   exact archive on a clean account or second Mac.
3. Run one current-source Qwen-planned proposal/apply/replay-rejection/undo
   lifecycle on an unsaved disposable Live set.
4. Run a new current-source/current-harness 24-hour companion soak with one
   manual Live close/reopen cycle and connected final state.
5. Prepare a consented, category-balanced real-mix corpus and obtain two
   independent reviews.
6. Complete ten signed-off supervised sessions across at least three hashed
   projects with bound support evidence.
7. Generate the final exact-release provenance receipt and require 14/14.

### Exit gate

- Qualified profile: **14/14 pass, 0 pending, 0 failed**.
- No evidence predates the final candidate or fails exact-source checks.
- No unauthorized mutation, false success, lost undo, unrecoverable state, or
  secret leakage is recorded.

## Programme B — build the real-session learning system

**Priority:** P0/P1
**Target window:** begin during private beta; mature over 6–12 weeks

### Session evidence contract

For every supervised assistant task, retain privacy-safe structured evidence:

- release, planner, parser, capability, and schema versions;
- opaque session/project/tester buckets scoped to the release;
- intent class and requested outcome, without raw prompt retention by default;
- context freshness and evidence classes used;
- proposal/action/receipt identities and lifecycle outcome;
- latency by stage: context, retrieval, planning, proposal, apply, readback,
  undo;
- user verdict: keep, revise, reject, or unsafe;
- reason codes for clarification, abstention, correction, and failure;
- optional consented notes, separated from operational telemetry.

`scripts/evaluate_session_outcomes.py` validates this contract and emits only
aggregate counts, latency, and root-cause coverage. Start from
`evaluation/review/SESSION_OUTCOME_LOG_TEMPLATE.json`; do not add raw prompts,
audio, paths, or identities to the log.

### Feedback taxonomy

Every miss must be assigned to one primary cause:

1. session perception;
2. classification;
3. retrieval;
4. musical judgement;
5. intent parsing;
6. planning/tool selection;
7. target resolution;
8. Live transport/action execution;
9. readback or recovery;
10. unsupported capability;
11. unclear user request;
12. evaluation ambiguity.

This prevents “train the LLM” from becoming the default response to failures
caused by retrieval, tools, Live state, or product contracts.

### Ableton manual grounding

Use the current Ableton manual as an authorized, local-only opt-in retrieval
source for technical facts and device workflows. Answers must distinguish a
manual-backed fact from a session measurement and from a producer suggestion;
the manual should make advice more accurate, not turn subjective musical ideas
into false certainty.

### Promotion cadence

- Triage every 10 sessions.
- Convert every confirmed failure into a minimal regression fixture.
- Re-run sealed benchmarks before accepting a fix.
- Review aggregate trends every 25 sessions.
- Freeze a new evaluation set before any model training round.
- Never train on the final sealed holdout.

### Exit gate

- At least 95% of pilot misses have an agreed root-cause label.
- At least 90% of confirmed reproducible failures have regression coverage.
- Raw audio and prompts are absent unless separately and explicitly consented.
- A release can be compared to its predecessor on fixed quality, safety, and
  latency metrics.

## Programme C — improve session intelligence and SLO integration

**Priority:** P1
**Target window:** 2–6 weeks after the current SLO training artifact is final

### SLO integration boundary

Source project: `<LOCAL_VOLUME>/NITE_DSP`. Do not couple KENN to
its training code or copy artifacts before training is complete and evaluated.

Introduce a versioned read-only contract:

```text
kenn.audio_classification.v1
  audio_sha256
  model_id / model_sha256 / label_map_sha256
  inference_version
  audio_only: top_k labels + calibrated probabilities
  metadata_assisted: top_k labels + calibrated probabilities
  selected_label or unknown
  confidence_band
  out_of_distribution score/status
  evidence used
  latency_ms
  limitations
```

### Integration rules

- Preserve audio-only and metadata-assisted predictions separately.
- Do not let filenames overwrite contradictory acoustic evidence invisibly.
- Use calibrated confidence and an explicit Unknown/OOD outcome.
- Initially expose classification only through context/search/ranking tools.
- Classification may inform an LLM proposal but may never directly trigger a
  Live mutation, file move, rename, or deletion.
- Hash and pin the exported model, label map, preprocessing, and test receipt.
- Keep inference off the real-time audio callback.

KENN now has a disabled-by-default, model-neutral adapter at
`apps/backend/src/kenn/core/audio_classification.py`. It accepts only this contract,
preserves both evidence streams, and marks every result advisory-only with no
Live mutation authority. A real backend remains blocked on the completed SLO
artifact and its evaluation manifest.

Completed observations are exposed only through the bounded read-only session
context; disabled, unavailable, and malformed classifier output is omitted.

### Evaluation required before default use

- Frozen cross-vendor, artist-disjoint, and pack-disjoint holdouts.
- Per-class precision/recall/F1 and confusion matrix, not accuracy alone.
- Calibration error and selective accuracy at confidence thresholds.
- Unknown/OOD evaluation on unsupported sounds.
- Separate audio-only and metadata-assisted results.
- Latency, memory, malformed-file, long-file, and concurrency tests.
- Focused improvement plan for claps, Foley, and snares; confidence limits for
  low-sample classes such as risers, bass loops, FX, and synths.

### KENN outcomes

- Search and rank samples by role, subtype, attributes, key/BPM where measured,
  and compatibility with the observed Live context.
- Explain why a sample was recommended and which evidence was measured,
  inferred, metadata-derived, or unknown.
- Improve track-role context with SLO evidence while retaining user correction
  as the highest-priority fact.

### Exit gate

- KENN adapter works with a fake backend and the pinned real artifact.
- Classifier absence/failure leaves core KENN and Live control fully usable.
- Confidence thresholds improve useful retrieval on a fixed KENN benchmark.
- No unsupported or low-confidence class is presented as certain.

## Programme D — broaden Ableton capabilities safely

**Priority:** P1
**Target window:** 4–12 weeks

### Capability families

Promote capabilities in producer-value order:

1. richer read-only set understanding: arrangement markers, clip metadata,
   routing, return tracks, groups, automation presence, selected objects;
2. navigation and audition: select/focus exact objects, controlled clip/scene
   audition, stop and restore where Live semantics permit;
3. mixer operations: sends, pan, volume, mute/solo/arm, return levels, with
   grouped atomic recipes;
4. stock-device workflows: inspect/add/configure EQ, compression, saturation,
   filtering, delay, and reverb only after exact browser identity is proven;
5. MIDI assistance: create/revise bounded clips, notes, velocity, timing, and
   length with before/after diff and full undo;
6. arrangement assistance: duplicate/move bounded clips and create locators,
   only after identity and undo semantics are proven;
7. naming/organization: supervised Live track/clip rename before any filesystem
   organization feature;
8. offline render comparison and reference-assisted advice, kept separate from
   direct Live mutation.

### Capability acceptance template

Every promoted action must have:

- typed schema and bounded inputs;
- exact target identity from a fresh snapshot;
- ambiguity and unsupported-state handling;
- confirmation-only proposal;
- stale-state rejection and idempotency;
- authoritative readback;
- receipt and identity-bound undo, or an explicit non-reversible declaration;
- interrupted-write reconciliation;
- unit, adversarial, integration, and real-Live evidence;
- latency and support-matrix impact recorded.

### Explicitly deferred until separately approved

- deleting tracks, clips, files, or projects;
- overwrite/save-as/export automation;
- freeze, flatten, consolidate, or destructive crop;
- arbitrary Python/eval access to Live’s object model;
- unattended autonomous mixing;
- unrestricted third-party plug-in parameter control;
- any LLM-generated raw OSC or filesystem command.

### Exit gate

- The top 20 recurring pilot intents are either safely supported or receive a
  precise explanation/alternative.
- Supported capability task success is at least 95% in supervised sessions.
- Undo/readback success is 100% for reversible qualifying actions.
- No capability bypasses the shared mutation boundary.

## Programme E — musical judgement and explanation quality

**Priority:** P1
**Target window:** 4–12 weeks, continuous afterward

### Evaluation corpus

Build a consented corpus spanning:

- vocals, drums, bass, dense electronic, sparse acoustic;
- full mixes, stems, buses, and single problematic tracks;
- clean examples where KENN should remain quiet;
- intentional faults at different severities;
- stylistic alternatives where multiple answers are acceptable;
- beginner, intermediate, and expert user goals.

### What reviewers score

- evidence correctness;
- issue priority and severity ordering;
- musical usefulness;
- actionability and specificity;
- genre/context awareness;
- appropriate abstention;
- overclaiming and false positives;
- explanation clarity;
- whether a proposed change preserves user intent.

### Quality targets for dependable beta

- Evidence correctness ≥95%.
- Useful/very useful ≥90%.
- Severity ordering ≥90%.
- Appropriate abstention ≥90%.
- False-positive family rate ≤5%.
- No high-confidence recommendation unsupported by measured, retrieved, or
  freshly observed evidence.
- No material regression in any represented category.

### Feedback-driven refinement order

1. fix evidence and measurement bugs;
2. improve retrieval corpus/ranking;
3. improve deterministic rules and tool schemas;
4. improve prompts and planner context;
5. add specialist models where they clearly outperform rules;
6. fine-tune the LLM only after the earlier layers stop explaining the misses.

## Programme F — LLM strategy and training decision

**Priority:** P1 decision; P2 execution
**Earliest sensible window:** after 50+ reviewed sessions and a frozen holdout

### Default strategy before training

- Keep the qualified open-weight planner behind typed tools.
- Improve context selection, retrieval, schemas, few-shot examples, and
  deterministic validators.
- Route simple intents deterministically and reserve the LLM for decomposition,
  explanation, and ambiguous multi-step goals.
- Maintain a smaller/faster fallback and a provider-independent interface.

### Fine-tuning trigger

Start a LoRA/SFT experiment only if all are true:

1. at least 500 high-quality reviewed trajectories exist, with a preferred
   target of 1,000–3,000;
2. examples cover clarification, abstention, safe planning, recovery, and
   musically useful explanations—not just successful commands;
3. train/dev/sealed-test splits are project- and session-disjoint;
4. the dominant remaining errors are demonstrably model-behavior errors;
5. prompt/retrieval/schema improvements have plateaued on the same benchmark;
6. licensing, consent, privacy, and deletion requirements are documented;
7. a reproducible baseline and rollback model are pinned.

### Training phases

1. **SFT/LoRA:** teach KENN’s schemas, clarification style, evidence language,
   and safe trajectory patterns.
2. **Preference tuning, optional:** use paired expert rankings only if enough
   consistent preference data exists.
3. **Distillation, optional:** move stable simple behavior into a smaller model
   for latency/cost, never into the mutation authority.
4. **No from-scratch pretraining:** unjustified for KENN’s scale and goal.

### Model promotion gate

- 100% schema-valid outputs on sealed safety cases.
- Zero unauthorized or destructive tool proposals on the safety holdout.
- No regression in clarification, abstention, target identity, or recovery.
- Statistically meaningful gain in musical usefulness or task completion.
- Mean and p95 latency remain within the release budget.
- Base qualified model remains an immediate rollback option.

If these criteria are not met, keep the existing model and improve the system
around it.

## Programme G — operational polish and release engineering

**Priority:** P0/P1
**Target window:** continuous through L3/L4

### Reliability service levels

- Companion startup success ≥99% on supported clean hosts.
- No duplicate companion or OSC listener ownership.
- 24-hour soak: zero unhealthy samples, bounded registries, ≤128 MiB peak RSS
  growth, ≤8 transient thread growth, required reconnect, connected end state.
- Read-only command p95 ≤1 s locally where no LLM generation is required.
- Planner mean ≤5 s and suite p95 ≤15 s for the qualified model boundary.
- Apply/readback/receipt result is always explicit; unknown transport outcomes
  never become blind retries.

### Release and support

- Reproducible AU/VST3 and companion artifacts.
- Developer ID signing, notarization, stapling, Gatekeeper, AU validation,
  VST3 validation, Ableton discovery, rollback, and clean-host evidence.
- One-click diagnostics that contain allow-listed metadata only.
- Versioned migration for stores, receipts, models, indexes, and schemas.
- Crash/recovery drills and tested rollback for every release candidate.
- Exact support matrix for Live, macOS, architecture, bridge, and model runtime.

### Exit gate

- Three consecutive release candidates pass all technical gates.
- No unresolved P0/P1 operational defect.
- Support evidence identifies failures without exposing user content.
- Upgrade and rollback succeed on clean and previously installed hosts.

## 5. Cross-cutting evaluation scoreboard

Every candidate should publish one machine-readable scorecard containing:

| Dimension | Core measure | Dependable-beta target |
|---|---|---|
| Safety | unauthorized mutation / false success / lost undo | 0 / 0 / 0 |
| Task completion | supported supervised tasks completed | ≥95% |
| Readback/undo | verified reversible actions | 100% |
| Grounding | technical claims supported | ≥95% |
| Musical usefulness | reviewer useful/very useful | ≥90% |
| Abstention | correct abstain/clarify decisions | ≥90% |
| Retrieval | fixed-corpus recall@4 | 100% or no regression from qualified baseline |
| Classification | macro F1 + calibrated selective accuracy | class-specific gate; no forced Unknown |
| Reliability | healthy long-session samples | 100% |
| Latency | deterministic p95 / planner mean and p95 | ≤1 s / ≤5 s and ≤15 s |
| Privacy | unconsented raw prompts/audio in receipts | 0 |

Scores must be segmented by genre, task family, capability, confidence band,
Live version, machine class, and cold/steady latency where applicable. An
overall average must not hide a weak class or unsupported configuration.

## 6. Execution sequence

### Horizon 1 — qualify the current beta candidate

**Weeks 0–3**

- Close all seven pending external gates.
- Freeze one exact candidate and stop source churn during evidence collection.
- Start a new qualifying soak only from that frozen source/harness.
- Begin supervised session logging with the hardened pilot contract.

### Horizon 2 — dependable assistant beta

**Weeks 2–8**

- Reach 50+ reviewed sessions across at least ten projects and five producers.
- Integrate the completed SLO artifact read-only.
- Promote the highest-value missing Ableton capabilities one at a time.
- Expand real-mix and hard-case corpora from observed failures.
- Publish candidate-over-candidate scorecards.

### Horizon 3 — broad capability and musical refinement

**Weeks 6–16**

- Reach 100–200 sessions across varied genres and workflows.
- Improve sample search, session role understanding, multi-step recipes, and
  grounded explanations.
- Calibrate confidence and Unknown behavior across specialist models.
- Conduct clean-host, reconnect, upgrade, rollback, and prolonged-session
  campaigns on every supported configuration.

### Horizon 4 — training decision and polished release candidate

**Weeks 12–24**

- Freeze a real-session model benchmark.
- Run the train/no-train decision gate.
- If justified, compare LoRA/SFT against the unchanged qualified baseline.
- Promote only a measurable, safe improvement.
- Require three consecutive fully qualified release candidates before the
  polished-assistant claim.

These windows are directional. Evidence quality, not calendar time, controls
promotion.

## 7. Immediate next actions

1. Treat the completed 8-hour run as diagnostic only; it is not current-source
   qualification evidence because its final Live state was offline.
2. Freeze the next release candidate after the current engineering batch.
3. Complete the two human-review forms and adjudication.
4. With Ableton available, regenerate the current-source real-Live
   model-planned lifecycle receipt.
5. Launch a new exact-source 24-hour qualifying soak and perform its manual
   reconnect near the planned window.
6. Prepare the consented real-mix packet and obtain two reviewers.
7. Begin the ten-session pilot log using the current evidence contract.
8. When SLO training is explicitly reported complete, inspect `NITE_DSP`
   read-only and produce an artifact/label/preprocessing/evaluation manifest.
9. With Ableton available, qualify append-only MIDI/audio/return-track
   creation on a disposable set, including interruption and final-state review.
10. Build the KENN classifier adapter behind a disabled-by-default feature flag.
11. Defer KENN LLM fine-tuning until real-session evidence satisfies the
    training trigger.

## 8. Decision rules

At each release review choose exactly one:

- **Promote:** every required gate passes and no serious unresolved incident
  exists.
- **Continue supervised pilot:** safety is intact, but quality, coverage, or
  external evidence remains incomplete.
- **Hold:** any unauthorized mutation, false success, unrecoverable state,
  privacy breach, provenance failure, or material regression appears.

The strategic rule is simple: make KENN more capable only at the speed that its
evidence, reversibility, and musical usefulness can support.
