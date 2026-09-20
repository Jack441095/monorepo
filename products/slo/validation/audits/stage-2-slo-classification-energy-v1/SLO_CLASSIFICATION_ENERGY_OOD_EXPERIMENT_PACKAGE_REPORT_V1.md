# SLO Classification Energy OOD Experiment Package V1

## Package identity

- ID: `SLO-L05-ENERGY-OOD-EXPERIMENT-V1`
- Product/system: SLO classification research harness
- Owner: NITE DSP; named owner/reviewer sign-off remains pending
- Worktree: `workspace/worktrees/slo/slo-build-entry-v1`
- Base SHA: `3da72b8`
- Status: instrumentation and improvement playbook complete; full-corpus experiment pending

## Problem statement

The current SLO research runner reports MSP, entropy, and margin OOD signals.
The prior centroid/threshold recalibration was a verified null result and
recommended testing a different signal based on classifier-logit energy. The
production classifier, centroids, thresholds, and OOD policy must remain
frozen until a reviewed before/after experiment exists.

## Current evidence

The latest corrected OOF scorecard reports 45.8% OOD false-known at the 0.75
threshold, while the direct native centroid-gate fixture reports 72.0%
(121/168). The external cache and scratch OOF outputs used for those results
are not durable product artifacts, so this package does not fabricate an
Energy result from incomplete or mismatched inputs.

## Files in scope

- `SmartSampleManager/tools/classification_benchmark/run_research_v3.py`
- `SmartSampleManager/tools/classification_benchmark/test_research_v3_reporting.py`
- `SmartSampleManager/docs/classification/SLO_CLASSIFIER_IMPROVEMENT_PLAYBOOK_V1.md`
- `SmartSampleManager/docs/SLO_CLASSIFICATION_ENGINE_AUDIT_V1.md`
- `SmartSampleManager/docs/classification/SLO_CLASSIFICATION_L05_EVIDENCE_GAP_V1.md`

## Explicitly out of scope

- `AcousticClassifierWeights.h`
- `AcousticClassifierCentroids.h`
- runtime OOD thresholds or `MlOverrideGate`
- taxonomy labels or product claims
- external audio, private corpora, protected labels, holdouts, or production cache
- signing, licensing activation, host qualification, or release promotion

## Implementation

The runner now computes the research-only Energy signal
`-T*logsumexp(logits/T)` from the same cross-fitted known/OOD logits and
positive calibrated temperature as the existing scorecard. It publishes
Energy AUROC, AUPR, and FPR@95 in `ood_results.json` and uses a stable
row-wise log-sum-exp implementation. Invalid logits and non-positive or
non-finite temperatures fail closed.

The companion improvement playbook translates the evidence into an executable
data/training loop: reviewed labels, provenance, group-safe holdouts, candidate
comparison, independent review, owner decision, and rollback. It does not
authorize a production model change.

## Tests and adversarial cases

- `python3 -B -m unittest -q SmartSampleManager/tools/classification_benchmark/test_research_v3_reporting.py`
  — **17 tests passed**.
- `python3 -m py_compile SmartSampleManager/tools/classification_benchmark/run_research_v3.py SmartSampleManager/tools/classification_benchmark/test_research_v3_reporting.py`
  — passed.
- `git diff --check` — passed.
- Improvement playbook reviewed for explicit data, split, decision, and
  rollback requirements.
- Focused Energy cases cover large finite logits without overflow, expected
  score direction, one-dimensional logits, NaN logits, and zero temperature.

## Evidence outputs

The next approved run should retain the external cache, exact known/OOD
manifest, source SHA, reviewer receipt, and generated `ood_results.json` with
MSP, entropy, margin, and Energy side by side. Until then, this package is an
instrumentation receipt, not a classification qualification receipt.

## Rollback

Revert the package commit from the isolated SLO worktree and rerun the 17-test
research suite. No production classifier or data state requires rollback.

## Exit criteria

Instrumentation exits when the runner and focused tests pass, which is
complete here. The experiment exits only after a regenerated, path-identified,
cross-vendor, independently reviewed known/OOD package produces a before/after
receipt and an explicit owner decision. No threshold or weight change is
authorized by this package.

## Known limitations and next package

Energy has not yet been measured on the current full corpus because the prior
external scratch cache is unavailable as a durable receipt. The next package
is to regenerate the cache/manifest/OOD overlay under the qualification
runbook, execute the real end-to-end comparison, and obtain independent blind
review plus explicit decisions for weak classes including Atmosphere and
Vocal Loop. The data-collection and candidate-training requirements are now
captured in `SLO_CLASSIFIER_IMPROVEMENT_PLAYBOOK_V1.md`.
