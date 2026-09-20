# KENN session intelligence implementation plan

**Date:** 2026-09-08

**Purpose:** turn KENN from a safe Ableton control surface with advice into a
musically useful assistant whose recommendations are grounded in the current
Set, measured audio, approved technical documentation, and reviewed producer
feedback.

This is an implementation programme within the
[polished Ableton assistant roadmap](KENN_POLISHED_ABLETON_ASSISTANT_PLAN_2026-09-08.md).
It deliberately excludes UX design. Its outputs are stable backend contracts
and receipts that the UX can present.

## Product contract

Every KENN response must identify which of these it used:

| Evidence class | Examples | What KENN may say or do |
|---|---|---|
| Fresh session fact | track routing, devices, clips, selected object | State it as observed; use it to target a proposal only after a fresh identity check. |
| Audio measurement | LUFS, headroom, LTAS/reference delta, stereo correlation | Give a bounded listening-oriented interpretation; never present a measurement as a command. |
| Specialist inference | SLO role/classification, section/energy detection | State confidence and limitations; advisory/ranking only until separately promoted. |
| Official technical reference | authorized local Ableton manual | Answer technical workflow questions with provenance. |
| Producer suggestion | arrangement, sound selection, creative alternatives | Label it as a suggestion and preserve user intent. |

No item in this plan permits unattended mixing, destructive edits, raw OSC,
arbitrary Live-object-model access, or automatic mastering.

## The shared Session Intelligence Brief

Build one versioned, bounded read-only object instead of letting each feature
assemble private context. It will be the input to advice, retrieval, planning,
and evaluation.

```text
kenn.session_intelligence.v1
  snapshot: identity, revision, transport, tracks, groups, returns, routing,
            devices, clips, locators, automation-presence, selection
  project_intent: user-declared genre, references, goal, constraints, memory
  track_roles: user-confirmed roles + SLO advisory evidence/confidence
  audio_evidence: mix/stem measurements and optional uploaded-reference deltas
  realtime_mix_comparison: optional scope-labelled plugin-bus versus render comparison
  arrangement: sections, density, energy, repetition, transitions, confidence
  retrieval: selected source ids, evidence classes, source versions
  capability_state: supported operations and current prerequisites
  freshness: capture time, expiry, unavailable fields, known limitations
```

Rules:

- Keep it small, schema-validated, versioned, and free of raw audio, prompts,
  paths, and personal identities by default.
- User corrections outrank inferred roles, metadata, and model predictions.
- Missing observations remain unknown; they are never filled by an LLM.
- A write proposal must re-fetch a fresh snapshot rather than trust this brief.

## Delivery sequence

### Phase 1 — unify existing evidence

**Outcome:** KENN has one reliable basis for explaining its advice.

1. Add the `kenn.session_intelligence.v1` schema and builder with explicit
   provenance, freshness, and truncation limits.
2. Feed the existing Live snapshot, manual retrieval results, current mix
   measurements, and reference-comparison findings into it.
3. Add an explanation renderer that separates observed facts, measurements,
   manual-backed facts, inferences, and creative suggestions.
4. Record which evidence classes were actually used in session-outcome
   telemetry.

**Acceptance gate:** fixtures prove that stale/missing/conflicting evidence is
visible, not invented; answers cite the right evidence class; no additional
Live write path exists.

Official-manual retrieval is separately qualified with the versioned
`kenn.ableton_manual_grounding_evaluation.v1` gate. It covers MIDI, routing,
automation, workflow, clips, recording, devices, transport, and export, and
checks only that an explicit documentation question selects official local
manual evidence. It does not certify generated-answer correctness or create a
Live write path.

### Phase 2 — reference-aware Mixdown Coach

**Outcome:** useful, modest mix feedback based on the user’s own reference.

1. Promote the completed 40-band LTAS reference comparison to the Session
   Intelligence Brief.
2. Add measured diagnostics for integrated/short-term loudness, true peak or
   stated approximation, dynamics/crest factor, stereo correlation and
   width, mono-compatibility warning, and low/mid/high spectral balance.
3. Compare a selected stem or bus when supplied, without asserting that a
   whole-mix measurement identifies the responsible track.
4. Produce at most five ranked listening checks and conservative starting
   points; EQ moves remain capped and labelled advisory.
5. Add a “reference differs by intention” abstention path for genre/style
   mismatch, weak confidence, clipping, or unsuitable source material.

**Example:** “Against this uploaded reference, the normalised 40-band view is
about +5 dB around 300 Hz. Check low-mid masking between bass, kick, and
musical layers before applying a broad cut.”

**Acceptance gate:** synthetic signal checks and blinded producer review show
measurement correctness and useful priority ordering; KENN never claims a
universal pink-noise target or alters a master automatically.

### Phase 3 — SLO-powered sound and role intelligence

**Dependency:** SLO training is complete and its exported artifact,
preprocessing, label map, calibration, and holdout receipt are supplied from
`NITE_DSP`.

1. Pin the exported model through `kenn.audio_classification.v1`; keep it
   disabled by default until this gate passes.
2. Add calibrated audio-only and metadata-assisted sample search/ranking,
   Unknown/OOD behavior, and explanations of why a result matches.
3. Infer tentative track roles from explicitly supplied audio/sample evidence;
   show user correction controls and retain corrections as highest priority.
4. Detect duplicate or missing roles in an arrangement as questions, not
   assertions: e.g. “There appear to be three kick-like layers; are they
   intentional?”
5. Develop class-specific policy for known weak/rare categories, especially
   claps, Foley, snares, risers, bass loops, FX, and synths.

**Acceptance gate:** pack-/artist-disjoint KENN evaluation, calibrated
selective accuracy, useful sample-ranking lift, graceful absence/failure, and
zero classifier-driven mutation.

### Phase 4 — arrangement and energy understanding

**Outcome:** KENN can describe musical shape without claiming taste is fact.

1. Derive bounded section candidates from locators, clips, silence, rhythmic
   density, energy, and repetition; use confidence rather than forced labels.
2. Calculate coarse low/mid/high energy and event-density trends per section.
3. Detect candidate transitions, overly repeated passages, abrupt energy
   changes, and inactive sections, with direct evidence links.
4. Build explanation templates such as: “The second chorus is lower in
   high-frequency energy than the first; if you intended escalation, audition
   a small percussion, automation, or texture change.”
5. Make alternative suggestions genre/reference-aware only when the user has
   declared that context.

**Acceptance gate:** annotated arrangement corpus reaches the agreed
precision/recall targets; producer reviewers rate suggestions separately from
section-detection correctness; the assistant is quiet when evidence is weak.

### Phase 5 — safe execution recipes

**Outcome:** high-value advice can become transparent Ableton proposals.

Promote one capability at a time, in this order:

1. create and label locators/arrangement sections;
2. select/focus exact tracks, clips, devices, or browser items;
3. create controlled A/B reference routing and restore it;
4. create/adjust bounded return, send, pan, volume, mute/solo/arm recipes;
5. inspect and propose stock-device chains; then add/configure only proven
   device identities;
6. make bounded MIDI/clip variations with before/after diff and undo.

Every recipe needs typed parameters, confirmation, snapshot freshness, exact
target identity, stale-state rejection, readback, receipt, and undo or an
explicit non-reversible label. KENN should prefer proposing an auditionable
alternative over changing a mix.

**Acceptance gate per recipe:** adversarial tests, real-Live disposable-Set
lifecycle, supervised-session success >=95%, and 100% qualifying readback/undo.

**Implementation status (2026-09-09):** locator creation is implemented with
confirmation, stale-playhead checks, exact readback, and an explicit
non-reversible receipt. Exact track and device focus are implemented as
view-only, confirmation-bound actions with identity checks, readback, and
fresh-token undo. These capabilities still require current-source real-Live
qualification before they are promoted as qualified actions.

### Phase 6 — project memory and collaboration

**Outcome:** KENN improves across a project without covertly building a user
profile.

1. Store only explicit, editable project notes: goal, genre, references,
   constraints, confirmed roles, accepted/rejected suggestions, and named
   decisions.
2. Scope memory to a project identifier, show provenance/age, permit edit and
   clear, and never use it as a Live action target.
3. Add a compact “what changed since last time” summary backed by snapshots and
   receipts.
4. Treat repeated rejection as a preference signal only after the user can
   inspect/correct it.

**Acceptance gate:** memory is inspectable, erasable, project-isolated, and
measurably improves repeat-session usefulness without raising false certainty.

### Phase 7 — feedback, evaluation, and model decision

**Outcome:** feature work converts into dependable capability rather than a
growing list of demos.

1. Run supervised sessions with the existing privacy-safe outcome contract.
   KENN now records only contract-validated category-level outcomes through
   `record_supervised_session_outcome`; these are bounded local records and
   reject prompts, audio, paths, names, and identities before persistence.
   The same contract powers `scripts/evaluate_session_outcomes.py`, so capture
   and review cannot silently diverge.
   Export a completed supervised batch with
   `python3 scripts/export_session_outcomes.py --database <KENN_DB> --output-dir <EMPTY_EXPORT_DIR>`,
   then pass the emitted JSON files to `scripts/evaluate_session_outcomes.py`.
2. Label every miss using the root-cause taxonomy; create a minimal regression
   fixture for confirmed reproducible failures.
3. Maintain separate scorecards for session understanding, Mixdown Coach,
   SLO ranking, arrangement analysis, advice quality, actions, and latency.
4. Assemble a consented, project-disjoint musical judgement corpus with
   blinded two-reviewer scoring.
5. After 50+ sessions, decide where the bottleneck is. Only after 500+ high
   quality reviewed trajectories and a frozen holdout may KENN trial LoRA/SFT
   for explanation, clarification, safe planning, and recovery style.

**Acceptance gate:** each feature demonstrates a measurable gain on a fixed
holdout with no safety, grounding, privacy, or latency regression.

## Suggested beta sprint order

| Sprint | Engineering deliverable | Evidence before promotion |
|---|---|---|
| 1 | Session Intelligence Brief + provenance renderer | schema/fixture tests; current retrieval and mix evidence preserved |
| 2 | Mixdown Coach v1, including LTAS and listening checks | measurement tests; blinded real-mix review |
| 3 | SLO import + advisory search/role context | pinned artifact; calibration and KENN ranking eval |
| 4 | Arrangement/energy analysis in shadow mode | annotated corpus; false-positive review |
| 5 | Locators and reference-routing recipes | disposable Live lifecycle; undo/readback receipts |
| 6 | Mixer/device recipes, one narrowly scoped workflow at a time | supervised success and recovery evidence |
| 7+ | Project memory and iterative improvement | privacy review; repeat-session usefulness evaluation |

Run the qualified-beta external gates and supervised-session collection in
parallel. Do not wait to begin read-only intelligence work, but do not promote
new mutations while the candidate is frozen for qualification.

## First engineering backlog

1. Specify and test `kenn.session_intelligence.v1`.
2. Create a builder that merges existing session, retrieval, and mix evidence
   without an LLM.
3. Add provenance-aware advice fixtures: technical question, mix-reference
   question, creative arrangement question, missing-evidence abstention.
4. Define Mixdown Coach metric contract and a small consented review packet.
5. When the SLO export arrives, write an artifact-ingestion validation command
   before connecting it to live inference.
6. Create an annotated arrangement fixture format and start with offline,
   deterministic analyses.
7. Pick one safe Ableton recipe—locators is the recommended first one—and
   qualify it end-to-end on a disposable Set.

The artifact contract and validation handoff are ready at
[`SLO_ARTIFACT_HANDOFF.md`](SLO_ARTIFACT_HANDOFF.md). The SLO export remains
read-only and disabled until its manifest verifies and KENN's own evaluation
gate passes.

## Non-goals for this programme

- replacing producer judgement with a score;
- training an LLM before we know the failure mode;
- treating a reference as a universal frequency curve;
- running model inference in the audio callback;
- autonomous master-bus EQ, destructive session changes, or filesystem actions;
- retaining uploads, raw prompts, or personal project data by default.
