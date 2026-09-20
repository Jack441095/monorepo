# SLO -> KENN reuse plan

**Status:** assessment and implementation plan — 2026-09-05

This plan identifies ideas from the SLO codebase that can improve KENN. It does
not propose copying SLO's audio-classifier implementation into KENN: SLO is a
C++/JUCE sample-library product, while KENN is a Python/C++ Ableton-control
product. The useful transfer is the evidence, state, naming, and safety design.

## Source material reviewed

- SLO repository: `<LOCAL_VOLUME>/NITE_DSP/products/slo`
- `SLO_PRODUCER_TAXONOMY_REQUIREMENTS_V1.md`
- `SLO_PRODUCER_TAXONOMY_IMPLEMENTATION_PLAN_V1.md`
- `SLO_OOD_UNKNOWN_REPORT_V1.md`
- `SLO_FILE_DATA_SAFETY_AUDIT_V1.md`
- `SLO_SOURCE_ARCHITECTURE_MAP.md`
- `docs/NITE_DSP_SLO_FINE_SUBCATEGORIZATION_V1.md`

## Highest-value reuse

### 1. Evidence-first classification for Live tracks

SLO separates primary type, subtype, attributes, confidence, and Unknown/OOD
instead of forcing one label. KENN currently has a useful name-based
`track_classifier.py`, but its result is effectively one role plus a fixed
recommendation.

Add a KENN `TrackContext` result with:

- `role` and optional `subrole`;
- `confidence` plus `confidence_band` (`high`, `medium`, `low`);
- `evidence` such as exact name token, alias, device chain, clip presence,
  or user confirmation;
- `uncertainty_reason` such as `name_only`, `ambiguous_alias`, `empty_track`,
  or `conflicting_evidence`;
- `candidates` when two roles are plausible;
- `masking_partners` and suggested actions as advisory data only.

This lets an LLM use classification as bounded context without treating a
track name as proof of its audio content. A track named `Bass` should be
described as “likely bass by name” until Live/audio evidence supports more.

### 2. SLO's Unknown discipline for KENN commands

SLO deliberately distinguishes “not scanned” from “scanned but Unknown/OOD.”
KENN should apply the same distinction to Live control states:

| KENN state | Meaning | Safe behavior |
|---|---|---|
| `offline` | Ableton or companion cannot provide a fresh snapshot | No proposal |
| `unknown_target` | Track/device identity is not exact | Clarify |
| `unsupported` | The requested operation is outside the allowlist | Refuse |
| `ambiguous` | Multiple interpretations remain | Clarify |
| `proposal_ready` | Exact target and before/after are known | Require confirmation |
| `transport_uncertain` | Write outcome cannot be trusted from transport alone | Reconcile, never retry |
| `applied_verified` | Readback confirms the requested change | Receipt and undo path |

The MCP facade already implements most of this boundary. The next step is to
make these statuses first-class in the user-facing response and UI rather than
allowing a generic “KENN could not answer” message to hide the reason.

### 3. Safe rename and organization workflow

SLO's file-operation design is directly useful if KENN eventually renames Live
tracks, clips, exported stems, or project assets. Reuse the workflow, not the
file paths:

1. classify and show the exact source target;
2. generate a proposed destination/name mapping;
3. show every mapping before mutation;
4. require explicit confirmation;
5. apply through one typed operation;
6. record a reversible receipt/journal;
7. support identity-bound undo;
8. never delete automatically.

For Live, the first safe feature should be **rename track**, not bulk file
renaming. It should resolve an exact track identity from a fresh snapshot and
produce a proposal such as:

```text
Track 4-Audio -> Bass Synth
Before: 4-Audio
After:  Bass Synth
Reason: explicit user request
Nothing has changed yet.
```

Bulk project/file renaming can come later, behind a separate filesystem
permission and path-safety boundary. Classification must never silently rename
files merely because a model guessed a category.

### 4. Versioned context and cache invalidation

SLO persists taxonomy, feature, and embedding-model versions and invalidates
stale classifications. KENN should apply the same idea to control context:

- `live_snapshot_schema_version`;
- `device_capability_version`;
- `command_parser_version`;
- `llm_plan_schema_version`;
- `planner_version` and `backend_version` in receipts.

This prevents a proposal created against an older device map or parser from
being treated as current after a plug-in rebuild or Live-session reload. KENN
already has session fingerprints, stale-state checks, and proposal schemas;
this is an additive way to make their provenance easier to inspect.

### 5. Evidence-gated model evaluation

SLO measures separability on real, cross-vendor data before shipping a new
label and reports contradictory datasets instead of merging them silently.
KENN should use the same rule for LLM command planning:

- keep deterministic parsing authoritative;
- run local-model plans in shadow mode first;
- compare action, target, value, unit, and clarification status;
- reject mismatches before proposal creation;
- measure latency separately from correctness;
- activate only after every holdout case is schema-valid and agrees;
- retain the model/provider/version in the evaluation receipt.

The current local Qwen smoke test demonstrates why this matters: the 0.5B
model produced a schema-valid plan but confused a user-facing “track 2” with a
zero-based Live index and invented unrelated EQ fields. KENN correctly rejected
it. The larger 7B model timed out on the same case. This is evidence for
improving the contract and evaluation, not permission to enable autonomous
Live writes.

## What should not be copied

- SLO's PANNs/ONNX sample classifier: not relevant to a Live command boundary.
- SLO's audio taxonomy labels: useful only as optional producer vocabulary,
  never as asserted facts about a Live track without evidence.
- SLO's bulk file movement as a first KENN feature: Live identity and project
  filesystem identity are different safety domains.
- Any model-generated filename or category as an implicit mutation instruction.
- SLO's historical metrics without their dataset, split, vendor coverage, and
  evidence status.

## Recommended implementation order

### Phase A — classification contract

- Extend `apps/backend/src/kenn/core/track_classifier.py` with evidence, confidence
  bands, candidates, and uncertainty reasons while preserving its current API.
- Add deterministic alias tests for producer abbreviations (`vox`, `bgv`,
  `808`, `drum bus`, `fx`, and similar terms).
- Expose the result in the Live snapshot and MCP read-only tools.

### Phase B — command/status contract

- Normalize the response status vocabulary above across HTTP, MCP, and the
  plug-in UI.
- Keep `proposal_ready`, `applied_verified`, and `transport_uncertain`
  distinct in every client.
- Add planner/backend/version metadata to receipts and proposal diagnostics.

### Phase C — supervised track rename

- Add a typed `rename_track` proposal to `LiveActionService`.
- Require exact track identity, explicit before/after values, confirmation,
  readback, idempotency, receipt, and identity-bound undo.
- Qualify it on the disposable Live set before exposing it to an MCP client.

### Phase D — optional file organization

- Design a separate filesystem service with path-component sanitization,
  source/destination preview, collision handling, cancellation, journal, and
  undo.
- Keep it disabled by default and never combine it with a Live mutation in one
  opaque LLM action.

## Bottom line

SLO can improve KENN substantially through its **classification model, Unknown
handling, evidence discipline, versioning, audit receipts, and reversible
rename workflow**. The strongest immediate upgrade is a richer, read-only
`TrackContext` plus the supervised `rename_track` proposal path. The audio
classifier itself is not the right piece to transplant, and the current LLM
shadow evidence says the guarded deterministic boundary should remain
authoritative for now.

## Integrating the intelligence surfaces

The best architecture is one supervised pipeline, not several independent
agents:

```text
Live/MCP + plug-in capabilities + SLO classification
                         |
                         v
                 KENN SessionContext
                         |
          +--------------+--------------+
          v                             v
      Mix Review                    LLM planner
   measured evidence          typed intent/recipe only
          |                             |
          +--------------+--------------+
                         v
                 proposal and approval
                         |
          +--------------+--------------+
          v                             v
   Ableton Live change             AudioGen job
          |                             |
          +--------------+--------------+
                         v
              AutoMix/offline comparison
                         |
                         v
              verified receipt and memory
```

### What each component contributes

- **SLO classification:** role, subtype, attributes, confidence, Unknown/OOD,
  and evidence. It should inform KENN's reasoning, never directly mutate Live.
- **AbletonOSC/MCP:** exact tracks, devices, parameters, current values,
  proposals, confirmation, readback, and undo.
- **KENN Mix Review:** measured faults and bounded corrective hypotheses. It
  should say “possible low headroom” or “phase issue measured,” not pretend to
  hear a musical intention it did not measure.
- **AudioGen:** new creative material and controlled test/reference assets. It
  should produce a provenance-rich job receipt, not a claim that the result is
  a better mix.
- **AutoMix:** offline candidate renders from stems, with before/after metrics
  and a comparison report. It should never write directly into the live set.
- **LLM:** route the request, explain evidence, and compose a typed recipe. It
  must not emit raw OSC, arbitrary Python, unreviewed file paths, or an opaque
  multi-tool mutation.

### Example end-to-end requests

For “make the vocal clearer”:

1. classify the relevant track as likely lead vocal, showing name-based
   confidence and any conflicting evidence;
2. inspect the exact Live chain and read current EQ/compressor parameters;
3. run Mix Review if a WAV or bounce is available;
4. explain the measured evidence and prepare one exact EQ proposal;
5. require confirmation, apply through MCP/AbletonOSC, read back, and record
   an undo receipt.

For “make me a darker bass loop and put it in Ableton”:

1. parse the creative brief and queue AudioGen;
2. keep the original Live set unchanged while the job renders;
3. classify and inspect the generated result, with generated provenance;
4. let the user audition or reject it;
5. only after approval, create a separate typed Live insertion/import proposal;
6. apply and verify the insertion, or leave the generated file outside Live.

For “mix these stems”:

1. validate and hash the input stems;
2. run AutoMix offline behind its approval gate;
3. compare baseline versus candidate metrics and identify the responsible
   operations;
4. deliver a rendered candidate and an explanation;
5. do not translate the candidate into Live writes automatically—create a
   separate, user-reviewed recipe if the user wants to reproduce it.

### The shared contract to build

Create one versioned context object with these fields:

- `session_id`, `snapshot_fingerprint`, and `observed_at`;
- `tracks` with SLO-style role/evidence/confidence data;
- `devices` with exact identity, capability, range, unit, and qualification;
- `measurements` from Mix Review and any supplied audio;
- `jobs` for AudioGen/AutoMix with status, hashes, provenance, and outputs;
- `user_corrections` and prior verified receipts;
- `available_actions` and explicit unavailable actions.

Every planner step should consume this context and produce a typed result:
`inspection`, `generation_job`, `offline_render`, `live_proposal`,
`clarification`, or `refusal`. A recipe must stop at the first failure or
ambiguity. This gives KENN one coherent memory and explanation layer while
keeping each high-risk executor independently gated.

That integration is the major intelligence upgrade: KENN can connect “what is
in the session,” “what is measured,” “what could be generated,” “what an
offline mix candidate changed,” and “what the user explicitly approved” into a
single chain of evidence.
