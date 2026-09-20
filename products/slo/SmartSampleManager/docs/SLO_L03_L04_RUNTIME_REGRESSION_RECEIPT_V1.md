# SLO L-03/L-04 Runtime Regression Receipt V1

## Package record

- **ID/title:** `SLO-L03-L04-RUNTIME-REGRESSION-V1`
- **Product/system:** SLO scan, cache, classification, and presentation runtime
- **Worktree/source SHA:** `workspace/worktrees/slo/slo-build-entry-v1` at `7b284eecb87f0ce5db0b95950ea734570a14bf77`
- **Build artefact directory:** `_build/ssm-qualification`
- **Run date:** 2026-09-01
- **Qualification level:** targeted regression evidence; not a release receipt

## Objective

Recheck the current native runtime boundaries after the classifier evidence
tooling changes, without starting a new build or the paused external corpus
scan. The run covers the known failure surfaces in L-03/L-04 and does not
change production model or OOD policy.

## Exact command

```bash
for test_binary in TestTaxonomy TestAcousticClassifierInputSafety \
  TestAcousticClassifierParity TestCacheVersionEnforcement \
  TestCachedReclassification TestFormatAwareScan TestMalformedAudio \
  TestPersistedCacheHydration TestClassificationPresentation; do
  ./_build/ssm-qualification/$test_binary
done
```

## Direct results

**9/9 binaries passed.**

| Binary | Result and covered boundary |
|---|---|
| `TestTaxonomy` | Taxonomy and heuristic classification tests passed. |
| `TestAcousticClassifierInputSafety` | Null, non-finite, zero-norm, and invalid embedding input safety passed. |
| `TestAcousticClassifierParity` | Python/C++ parity passed: maximum logit error `3.16082e-06`, maximum probability error `2.9717e-07`; V4-H OOD regression checks passed. |
| `TestCacheVersionEnforcement` | Stale feature/taxonomy/classifier/embedding versions, malformed source retry, user-data preservation, and changed-file invalidation passed. |
| `TestCachedReclassification` | 1,000 cached files reclassified successfully; measured throughput `23,914.5 files/sec` in this run. |
| `TestFormatAwareScan` | WAV/AIFF/FLAC admission, unsupported extension rejection, and malformed FLAC handling passed. |
| `TestMalformedAudio` | Four malformed WAV cases rejected cleanly without poisoning the batch; valid sibling processed. |
| `TestPersistedCacheHydration` | Cold hydration restored library, embeddings, DSP features, taxonomy, map coordinates, user data, HNSW, and reset semantics. |
| `TestClassificationPresentation` | Classification presentation contract passed. |

The ONNX runtime emitted informational CoreML partition-assignment warnings
during model-backed tests. They did not fail the tests; a separate host and
performance package is still required before making performance claims.

## Evidence and safety checks

- The SLO worktree was clean before and after the run.
- No source files, production weights, thresholds, taxonomy, OOD policy, or
  external audio were changed.
- The external Energy benchmark remains paused for CPU protection and has no
  receipt.
- This receipt covers targeted existing binaries, not a fresh clean-machine
  configure/build or the full external corpus.

## Limitations and remaining gates

- The 9/9 result does not establish cross-vendor classification accuracy.
- Independent blind review, reviewed labels, candidate-vs-baseline metrics,
  signing/notarisation, installation, host matrix, and release approval remain
  open.
- The paused scan must not be treated as complete until its result receipt is
  written and checked against the manifest hash.

## Rollback

No runtime rollback is required. This is a documentation-only receipt. Remove
the receipt from the isolated worktree if the evidence is superseded or found
to be incorrectly scoped; do not alter the tested binaries or user caches as a
rollback action.

## Next package

When CPU capacity is available, finish the paused Energy scan and review its
receipt. Separately, obtain independent labels through the L-05 review packet
and run one candidate-vs-baseline comparison on a sealed, vendor/source-family
holdout.

