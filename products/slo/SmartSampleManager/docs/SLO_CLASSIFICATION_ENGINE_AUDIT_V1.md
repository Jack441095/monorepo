# SLO Classification Engine Audit V1

**Package:** `L-05-classification-input-safety-v1`  
**Objective:** inspect the SLO classification boundary for the historical
failure mode where unusable model output can become a confident-looking
classification or poison downstream similarity state.

## Audit scope

The audit traced the current path from `runInferenceBatch()` through
`AcousticClassifier::classify()`, `MlOverrideGate::evaluate()`, cache hydration,
and the HNSW indexing guards. It also reviewed the current V4-G/V4-H OOD
reports, parity tests, and the evidence-source hierarchy. No real/private
corpus, model weights, holdout data, production cache, host, or deployment was
opened or changed.

## Finding and change

The classifier previously treated a 512-float buffer as sufficient evidence of
a valid embedding. A zero vector or a vector containing NaN/Inf could therefore
enter the linear-head calculation. Depending on the values, this could yield a
named top-1 class, non-finite diagnostics, or an OOD comparison that did not
represent a meaningful embedding. The inference path also marked the output
`Valid` before checking its contents, and cache hydration checked only blob
length.

The boundary is now fail-closed:

- `AcousticClassifier::isValidEmbedding()` rejects null, zero-norm,
  non-finite, and arithmetic-overflow-scale 512D buffers.  The upper norm
  bound protects the existing float-based similarity/index consumers; it is
  not a model-calibration threshold.
- `AcousticClassifier::classify()` returns an empty subcategory, zero
  confidence, no centroid, and `isOod=true` for invalid input.
- The ONNX batch and reference-search paths validate that the runtime output
  is exactly one float tensor with the expected `[batch, 512]` shape before
  taking a typed pointer.
- `runInferenceBatch()` converts invalid model output into the existing
  retryable/permanent failure states before classification, caching, or index
  insertion.
- Cache hydration refuses a same-sized blob unless its floats pass the same
  validity check, causing a safe reprocess rather than trusting corrupted
  state.
- Cache writes, classifier invocation, HNSW insertion, UMAP projection, near-
  duplicate detection, and similarity queries now reuse the same
  status-plus-numerical validity predicate; a 512-float length check alone is
  no longer sufficient for any downstream consumer.
- The additive 808/Reese and open/closed hi-hat centroid taggers now apply
  their own null, finite, non-zero, and arithmetic-safe checks and use double
  precision for norm/dot accumulation. A direct future caller therefore cannot
  turn a corrupt embedding into a fine-grained label merely because the main
  engine currently calls them behind its guard.

The existing evidence hierarchy and calibrated V4-G/V4-H OOD thresholds are
unchanged. This package does not retrain weights, alter taxonomy, loosen OOD
thresholds, or let ML override filename/metadata evidence.

## Finding and change: abstention presentation

The engine intentionally keeps the legacy `instrumentType` field separate from
the Ableton taxonomy fields. On the `ml_ood` path, the taxonomy fields are
cleared, but the map previously used `instrumentType` as a display fallback and
as its category/style input. A stale coarse value such as `Kick` could therefore
still look like a current taxonomy decision even though the classifier had
abstained.

`ClassificationPresentation` now gives the canvas one explicit field-precedence
contract:

- `ml_ood` renders as `Needs review` and uses a neutral map style;
- OOD samples match only the `Unknown Other` filter text, so they remain visible
  under the default `Other` view but do not masquerade as a known class;
- known samples continue to prefer subcategory, then category, while retaining
  legacy fields in filter matching;
- the raw `instrumentType` value remains untouched for metadata editing,
  diagnostics, and search.

The dependency-free `TestClassificationPresentation` regression target covers
these precedence and visibility cases and is enrolled in the fast and
classification qualification groups.

The same presentation contract now exposes the already-recorded provenance in
the selected-sample status line: metadata-assisted, filename/folder heuristic,
audio-only, audio-model, user override, OOD abstention, or not-run, together
with the taxonomy version. This closes the UI-side provenance gap without
changing the stored classification or its decision logic.

## Finding and change: derived-tag coherence after ML/OOD decisions

The primary taxonomy fields were correctly cleared for a weak-evidence OOD
abstention, but the old secondary-tag vector could still contain heuristic
values such as `Loop`, `One-Shot`, `Atonal`, or a fine-grained bass/hi-hat tag.
Because secondary tags are searchable and feed Suggested Tags, that left an
abstained sample discoverable as if it still had a known derived label. A stale
taxonomy refresh could also append a new fine-grained tag without removing one
from the superseded heuristic result.

The current candidate lineage now:

- clears all derived secondary tags when the final gate decision is `ml_ood`;
- rebuilds only the conservative Loop/One-Shot implication of the final ML
  subcategory when an ML override is applied;
- preserves the documented duration-only Kick Short/Long attribute when the
  acoustic head supplies `Kick`; and
- appends Bass 808/Reese and Hi-Hat Open/Closed labels uniquely, preventing
  duplicate labels during repeated cache refreshes.

The cache-version regression fixture now seeds a stale derived tag and asserts
that it cannot survive taxonomy refresh; OOD specifically must end with an
empty secondary-tag vector. These are source-level/static checks in the current
low-CPU run. Native execution remains environment-gated.

## Finding and change: provenance and reset persistence

`winningEvidence` was present on `SampleItem` and used by the evidence
hierarchy, but it was not part of the persisted `sample_cache` schema. A cold
hydration therefore lost the evidence source and defaulted it to `UNKNOWN`,
including after a user correction. The cache now migrates an additive
`winning_evidence` column, writes it with every eligible cache row, and restores
it on hydration. Persisted user overrides also restore the explicit
`USER_OVERRIDE` provenance.

`Reset to Auto` now clears derived taxonomy fields, confidence, source,
provenance, and version in memory and in `sample_cache`, in the same transaction
as removing the dedicated override row. This prevents stale user tags from
returning after restart while preserving the legacy `instrumentType` and its
metadata role. The existing persisted-cache hydration test now covers both
provenance round-trip and post-reset cold hydration.

## Finding and change: untrusted audio metadata

The format-aware metadata reader is an input boundary: imported files can
carry malformed or adversarial tags. Generic-container BPM parsing already
rejected non-finite values, but the WAV `TBPM` path did not apply the same
validation, and an empty WAV `InstrumentType` value could suppress the
filename/DSP fallback chain.

The current candidate now accepts BPM metadata only when it is finite,
positive, fully consumed, and no greater than 1000 BPM, across WAV and generic
admitted formats. Empty WAV instrument tags normalize to `Unknown` so they
cannot masquerade as authoritative metadata. `kFeatureAnalysisVersion` is now
`3`, causing stale rows to refresh their metadata/evidence contract while
preserving the existing embedding and frozen user overrides. Selective refresh
also clears legacy non-finite/out-of-range BPM values and normalizes legacy
empty instrument values instead of carrying them forward.

## Finding and change: classifier-head cache invalidation

The cache already versioned the embedding model, DSP feature extraction, and
Ableton taxonomy, but it did not version the acoustic classifier head itself.
AcousticClassifierWeights::modelVersion existed in the compiled header yet
was not persisted or compared during cache hydration. A future head update
could therefore leave a valid 512D embedding paired with an obsolete ML label
after restart.

The candidate now persists classification_model_version as a separate
additive cache column. Legacy rows with valid embeddings are stamped once with
the current head version during migration; a later non-current value is a
cache hit with a cheap head-only refresh, preserving the embedding and avoiding
another ONNX pass. User overrides remain authoritative and are not reclassified.
Fresh inference and selective refresh both write the current head version.

The native cache-version regression forces a stale classifier-head version and
sentinel ML label, then verifies that the label is recomputed, the version is
refreshed, and the embedding remains bit-for-bit identical.

## Finding and change: research-only energy OOD instrumentation

The existing leakage-controlled research runner reported maximum softmax
probability, entropy, and class margin, but did not expose the energy signal
recommended by the prior centroid-recalibration null result. The runner now
calculates the numerically stable research signal
`-T*logsumexp(logits/T)` from the same cross-fitted logits and positive
temperature used by the existing OOF scorecard, and records its AUROC,
AUPR, and FPR@95 alongside the existing methods.

This is measurement-only: it does not alter the frozen runtime head, centroid
thresholds, cache decisions, or production OOD policy. The helper rejects
non-finite logits and non-positive temperatures, and the focused research
suite covers overflow-safe arithmetic, score direction, and invalid inputs.
The full-corpus energy result remains pending because the prior external
cache/OOF scratch package is not a durable product artifact and must be
regenerated under an approved before/after receipt.

## Direct validation

The lightweight classifier-only smoke compiled the production header and
verified:

- zero embedding remains unclassified and fail-closed OOD;
- NaN/Inf embedding remains unclassified and fail-closed OOD;
- null embedding is rejected without dereference;
- an ordinary finite embedding still produces a finite classification result;
- the classifier-only production header compiles cleanly with the new guard;
- an accepted near-limit finite embedding still produces finite classifier
  confidence and entropy, in addition to finite norm and centroid diagnostics;
- the additive bass-timbre and hi-hat taggers reject null, zero, and non-finite
  embeddings and keep their diagnostics finite at the accepted near-limit;
- an explicit `ml_ood` result cannot fall back to a stale coarse display label;
- stale derived secondary tags are removed on ML/OOD cache refresh and fine
labels are not duplicated;
- classification provenance and taxonomy version are rendered from their
  existing recorded fields;
- taxonomy provenance survives cold cache hydration, and Reset to Auto does
  not resurrect stale user tags;
- `git diff --check` passes.

These cases are now permanently executable as the dependency-free CMake target
`TestAcousticClassifierInputSafety`, enrolled in both
`ssm_qual_fast_regression` and `ssm_qual_classification`.  This keeps the
boundary regression cheap to rerun while the full native parity and host
qualification remain environment-backed gates.

The existing JUCE parity target also contains the new regression cases in
`Source/TestAcousticClassifierParity.cpp`; running that full target still
requires the configured native SLO build environment and was deliberately not
started during this low-CPU audit.

## Limitations and next evidence

This package proves the pure boundary behavior, not the complete product
qualification. Still required before any release claim:

1. execute the native parity target and the SLO qualification suite from a
   clean out-of-tree build;
2. exercise an injected invalid ONNX output through `runInferenceBatch()` and
   confirm retry/persistence/index behavior end to end;
3. rerun the authorised, leakage-controlled classification/OOD corpus and
   preserve the exact source, dataset, reviewer, and limitation receipts,
   including the new research-only Energy score;
4. complete host/runtime, signing, installation, support, rollback, and owner
   decision gates.

## Deliberately not touched

No classifier weights, centroids, thresholds, taxonomy labels, historical
reports, private audio, real validation corpus, production cache, or external
services were modified.

## Rollback

Revert the isolated candidate package commits only after recording the reason
and rerunning the previous parity/safety checks. Do not reset, clean, delete,
or overwrite the shared root or other product worktrees.
