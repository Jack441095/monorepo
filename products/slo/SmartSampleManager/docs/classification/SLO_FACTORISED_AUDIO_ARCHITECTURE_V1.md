# SLO factorised audio architecture v1

## Decision

SLO will represent sound identity, temporal form, physical attributes, and
similarity as independent evidence.  A policy layer may combine those facts
into a review suggestion or proposed filename, but an analysis component may
not authorize a filesystem action.

This is an additive migration.  The current product classifier remains the
behavioural baseline until a replacement passes collection-held-out and native
parity gates.

## Contract

The canonical wire contract is
`tools/classification_benchmark/audio_evidence_schema_v1.json`.  Its Python
reference implementation and legacy adapter are in
`tools/classification_benchmark/audio_evidence_schema.py`.

Every claim contains a value, confidence, source, state, and optional ranked
alternatives.  Every physical measurement contains its unit and extraction
method.  Original flat taxonomy fields are retained under `legacy` during the
migration so parity is directly testable.

## Components

1. **Ingest and identity** decode safely, create a content identity, and resolve
   exact and acoustic duplicate groups.
2. **Evidence producers** independently emit metadata/name evidence, neural
   embeddings, physical measurements, and user corrections.
3. **Prediction heads** independently estimate family, identity, form,
   attributes, and rejection/OOD state.
4. **Similarity** indexes the stable embedding and exposes neighbours; it does
   not require or manufacture a class.
5. **Policy** consumes evidence and chooses `review`, `suggest`, or an explicitly
   qualified automatic action.  It cannot weaken duplicate/path/collision
   guards.
6. **Naming** is a deterministic preview-only transformation from approved
   fields.  Mutation remains a separate journalled executor.

## Training protocol

- Keep the 120-item Clap/Kick/Snare validation set sealed.
- Collapse exact duplicates before splitting or sampling.
- Split by collection/vendor only; assert zero group overlap on every fold.
- Use identical folds for the incumbent and every candidate.
- Report exact accuracy, macro-F1, family/form metrics, rejection false accepts,
  calibration, and useful coverage at target precision.
- Measure collection decodability before and after representation training.
- A candidate must improve macro-F1 by at least 2 percentage points or remove a
  material product risk without regressing validated classes.
- Re-extract through the native production window before any promotion; cached
  research embeddings alone cannot establish deployability.

## Migration sequence

1. Land and validate the decision-neutral evidence contract.
2. Add a C++ compatibility adapter that mirrors current taxonomy output without
   changing cache or UI behaviour.
3. Freeze a content-addressed, duplicate-collapsed experiment manifest and
   collection-held-out folds.
4. Train factorised heads in research-only mode on GPU 1, without restarting or
   altering the remote host.
5. Compare against the frozen centroid incumbent and publish a fail-closed
   receipt.
6. Run successful heads in shadow mode and compare their proposed evidence to
   current product output.
7. Only after native parity, explicit class approval, and rename canaries may a
   policy version consume the new claims.

