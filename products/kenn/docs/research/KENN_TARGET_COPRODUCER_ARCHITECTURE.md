# KENN target coproducer architecture

## Product boundary

KENN should become an evidence-grounded coproducer with two deliberately separate loops:

1. **Reasoning loop:** understand the request, bind references to a versioned project graph, retrieve evidence/preferences, analyse audio, construct and explain a typed plan.
2. **Action loop:** show an exact proposal, obtain confirmation where required, re-read preconditions, execute through Live, read back, issue a receipt, and offer an identity-bound inverse.

No model output directly becomes a Live write. Suggestions are allowed under uncertainty; mutations are not.

```text
User + current view
        |
Intent/Dialogue -> Reference binder -> Project graph (stable IDs + revision)
        |                 |                 |
        |           clarification       Live observer
        v
Planner <-> evidence router <-> manuals / session / preferences / audio analysis
        |                        |              |              |
        |                     provenance     C++ workers    SLO manifest
        v
Typed proposal + rationale + confidence
        |
Policy / confirmation / expiry / precondition
        |
Serialized Live adapter -> readback -> receipt -> inverse proposal
                              |
                         verified project graph

AudioGen adapter -> bounded MIDI/audio artifact -> validation -> proposal (never direct insert)
```

## Required contracts

- **Project graph:** stable IDs, names, type, parent/child relations, track/scene/clip/device positions, arrangement time, selected/focused objects and monotonic revision. Duplicate names are normal; identity never depends on display text alone.
- **Evidence bundle:** source, timestamp/version, retrieval mode, excerpt identifier, applicability and confidence. Missing evidence remains missing rather than becoming a model claim.
- **Plan:** ordered typed operations, targets by stable ID, parameters/ranges, expected effect, risk class, assumptions and verification predicates.
- **Proposal:** plan plus project revision/precondition digest, expiry, required confirmation class and dry-run representation.
- **Receipt:** requested/attempted/applied/verified fields, before/after observations, partial failure, retry identity, timing and provenance.
- **Inverse:** derived from actual verified before-state and bound to the receipt/action identity; it is itself proposed and confirmed.

## Intelligence routing

Use deterministic parsing for well-covered commands and safety checks. Use a model for classification, reference hypotheses, plan candidates and explanations, constrained to typed outputs. Retrieval supplies manual/project facts. Audio analysis supplies measured facts. A verifier rejects unsupported targets, invalid ranges, stale revisions and claims without evidence. Low-confidence or multiply resolvable references produce one concise clarification.

Producer preferences are explicit, scoped and inspectable: project/session defaults first, then user preferences, then generic heuristics. Feedback updates a candidate preference only after repeated evidence or explicit save, and must never weaken safety policy. Evaluate on held-out projects and separate users to prevent memorized preference leakage.

## Live reliability semantics

- Observe through bounded batch reads and cache only with a revision/age.
- Serialize writes per Live set; each operation is idempotency-keyed.
- Re-read the affected objects immediately before execution and refuse stale proposals.
- Read back every claimed mutation; report partial outcomes exactly.
- Circuit-break on transport failure and never convert timeout into success.
- Persist enough proposal/receipt state for process restart while expiring confirmations fail-closed.

Arrangement support requires a canonical timeline representation, locators/sections, clips with absolute positions and loop semantics, tempo/signature automation, and before/after snapshots. “Second chorus” must bind to an explicit section or clarify; it cannot be guessed from clip names alone.

## AudioGen and SLO

AudioGen returns a versioned bounded artifact with generation parameters, seed/model identity, musical metadata, validation status and content hash. KENN previews it and proposes a target/insertion; Live remains untouched until confirmation and readback.

SLO returns a versioned artifact manifest or ranked search response containing stable asset IDs, paths/handles, feature provenance, index/model versions and confidence. KENN must not scrape SLO internals or claim availability when the integration root is absent.

## Release SLOs

- Zero unauthorized writes in the adversarial suite and real-host qualification.
- 100% executed actions carry readback receipts; 100% undo operations bind to a verified action.
- ≥0.90 stable-target/tool accuracy and ≥0.95 safety/refusal accuracy on held-out cases.
- API p95 under 200 ms excluding explicitly asynchronous analysis/model/Live work; publish separate stage latencies.
- Audio callback missed deadlines: zero in qualification matrix; no allocations/locks/I/O in callback instrumentation.
- Crash-free bounded native analysis across the corpus and sanitizer/fuzz runs.
