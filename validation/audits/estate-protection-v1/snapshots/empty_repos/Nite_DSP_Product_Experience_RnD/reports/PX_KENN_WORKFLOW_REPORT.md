# PX-B - KENN Workflow Report

## Status

**PASS WITH LIMITATIONS**

KENN and AutoMix already contain substantial measurement and grounding infrastructure. The product-experience gap is presenting that evidence as a small number of trusted, reversible decisions rather than expanding chat or surfacing every detector.

## Evidence

### OBSERVED

- KENN lives under `Audio_Too/studio/kenn/kenn`; local AutoMix orchestration is in `Audio_Too/scripts/automix_local.py` and related business modules.
- The local AutoMix path classifies stems, prepares/alines them, analyses masking, generates a mix plan, infers musical roles and arrangements, checks mono compatibility, analyses dynamics, infers relationships, and builds an automation preview.
- Masking, mono-compatibility, and proactive crest reduction corrections are explicit opt-in flags in the local CLI. Reference spectral, dynamics, and width matching are also opt-in.
- `Audio_Too/business/app/automix_kenn_explain.py` reshapes a render manifest into the existing `kenn_mix_review_handoff.v1` context. It carries decisions, quality receipts, technical metrics, safety diagnostics, and bounded priority actions. Relationship actions are labelled with `measured` confidence.
- `Audio_Too/studio/kenn/kenn/server_payloads.py` supports structured flags, priority actions, metrics, reference comparison, and reference EQ moves. The payload builder bounds several lists rather than dumping unlimited detail.
- `mixing_doctor.py` keeps active alerts and polls Ableton mixer state. Its own comments explicitly distinguish track parameter state from actual audio signal, and state that spectral masking or reference comparison cannot be claimed from volume-only data.
- Ableton write actions are opt-in and confirmation-backed in the bridge/package documentation. The audited KENN surfaces do not establish a single end-to-end in-plugin Apply/Reject/Undo interaction for every AutoMix correction.

### MEASURED PROTOTYPE

The isolated [kenn_workflow_results.json](../experiments/kenn_workflow_results.json) ran three deterministic fixtures:

- A noisy fixture produced three findings, ranked high-to-medium, with evidence, frequency focus, cause, and recommendation.
- All proposals stayed `provisional` until a decision.
- Apply changed the state to `applied` and retained `undo_available`.
- Reject changed the state to `rejected` without applying.
- A healthy fixture produced `nothing_important_needs_fixing: true` and no proposal.

This validates state invariants only. It does not measure human trust, audio quality, or KENN production thresholds.

## Required Closeout

### ISSUE PRESENTATION

Prefer a compact issue card with: severity text chip, evidence sentence, frequency/time focus, affected channel or stem, cause hypothesis, and one proposed next action. Use confidence only when it describes evidence quality. The existing structured flags and actions are a sound contract basis; a constant decorative percentage is not.

### EVIDENCE UX

**Strong foundation exists.** Use the actual measured region, comparison, or receipt as the first explanation surface. Distinguish mix-quality evidence from operational telemetry. The AutoMix grounding adapter already makes that distinction explicitly for resource profiles and quality receipts.

### PRIORITISATION

The R&D recommendation is **Top issue, Next issue, Optional improvement, No action needed**, with a default cap of three visible issues. The existing detectors provide enough raw material, but the audited workflow does not prove that all surfaces converge on that hierarchy. Validate cognitive load with real engineers.

### AUTOMIX PROPOSAL UX

AutoMix has an important safety shape: corrections are opt-in, plans include an automation preview, and render decisions can be grounded later. Treat the render as a proposal and show a before/after diff. Apply, reject, and undo must be visible operations with a durable receipt. Do not infer that a quality gate means the user's artistic decision has been made.

### REFERENCE WORKFLOW

The existing reference pipeline supports measured comparisons and opt-in spectrum/dynamics/width movement. The correct experience is deviation plus context and bounded direction, not spectrum matching as an artistic target. The source history already records that a cut-heavy reference match was rejected in favor of a boost-only, listening-gated approach; preserve that caution.

## Top 5 KENN Workflow Improvements

1. Make the default surface a ranked issue queue with a confident no-action state.
2. Put evidence and scope beside every proposal, with an inspectable before/after diff.
3. Make Apply, Reject, Modify, and Undo explicit and receipt-backed across AutoMix and KENN surfaces.
4. Separate measured audio evidence from render telemetry and reference targets in the visual hierarchy.
5. Run a human cognitive-load test comparing all-findings, top-three, and no-action presentations.

## Anti-Feature Finding

Do not build a chatbot-first KENN panel that turns every detector into a conversational suggestion. It hides evidence, adds mode switching, and performed negatively in the synthetic corpus. Chat can explain a selected issue; it should not own the workflow.

## Promotion Decision

Promote evidence-first issue cards and reversible proposal grammar to a human test. Continue R&D on prioritisation thresholds, reference presentation, and complete Apply/Reject/Undo parity. Do not make AutoMix silently authoritative.

## Artifacts

- [kenn_workflow_probe.py](../experiments/kenn_workflow_probe.py)
- [kenn_workflow_results.json](../experiments/kenn_workflow_results.json)
- [automix_kenn_explain.py](../../Audio_Too/business/app/automix_kenn_explain.py)
