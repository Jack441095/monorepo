# SLO Classification L-05 Evidence Gap V1

**Date:** 2026-09-01  
**Candidate:** `engineering/slo-build-entry-v1`  
**Purpose:** fail-closed status of the classification evidence required by the
SLO brief. This is an audit receipt, not a qualification approval.

## Current conclusion

The runtime classification path has received useful hardening, but SLO
classification is **not qualified for a release claim yet**. The remaining
block is evidence quality and repeatability, not permission to continue
engineering.

## Concrete findings

1. **Group leakage control was claimed but not enforced.**
   `run_research_v3.py` described its cross-validation as source-family-aware,
   but used ordinary `StratifiedKFold` and did not pass `source_family` to the
   splitter. A read-only check of the current manifest found 60 of 147 source
   families appearing in more than one of those folds. The script now uses
   `StratifiedGroupKFold` and raises if a group crosses train/test.

2. **The scorecard can silently lose a taxonomy class.**
   The tracked `dataset_manifest.json` contains 17 known classes, while the
   tracked `per_class_metrics.csv` contains 16 rows and omits Atmosphere. The
   research script now fails unless the cleaned dataset contains exactly the
   frozen 17 classes and every fold contains every class in both train and
   test. Existing metrics must therefore be regenerated before being treated
   as current evidence; no replacement numbers are fabricated here.

   The subset builder also silently wrote a partial manifest (only one
   Atmosphere sample) and its output path pointed at the shared checkout rather
   than the isolated candidate. It now resolves output beside the script and
   refuses to publish unless every frozen class has at least five samples from
   five distinct source families, with no source family carrying mixed class
   labels.

3. **The prior published metrics were also in-sample.**
   Before this checkpoint, the script fit `lr_final` on all cleaned samples and
   used that same fit for `metrics.json`, per-class metrics, calibration, and
   the known side of OOD scoring. The harness now uses out-of-fold known
   predictions and cross-fitted OOD scores for those published measurements;
   the full-data fit is retained only for runtime-weight export and review
   queue generation. Existing numbers remain historical until regenerated.

4. **The real-corpus labels are not independent ground truth.**
   `REAL_CORPUS_CROSS_VENDOR_V2_REPORT.md` covers 5,157 files/17 classes/15
   vendors, but labels come from vendor folder names and are not manually
   verified per file. The report itself identifies likely Atmosphere-versus-
   Synth label contamination. This supports exploratory measurement, not an
   owner/blind-reviewed qualification set.

   A metadata-only preflight of the available corpus confirms the same
   inventory without decoding, hashing, copying, or modifying audio: 5,157
   files, 15 vendors, all 17 classes, no missing mapped folders, and three
   unmatched filename-split files. The existing three-token filename grouping
   is still blocked (Music Loop has one family and 20 mixed-label families).
   A candidate boundary of vendor + mapped source folder + five filename
   tokens has 25+ families for every class and zero mixed-label groups. That
   is a useful engineering lead, not an accepted leakage boundary: it must be
   validated against provenance and approved in the qualification receipt
   before the research manifest or product claim changes.

   The metadata preflight also reports duplicate basenames explicitly; the
   current mapped corpus contains 49 duplicate-basename groups (98 rows),
   which is why the research runner must resolve cache rows by path identity.

   A read-only availability check confirms the declared 43 GB source root is
   present and the metadata audit still returns 5,157 files, 15 vendors, and
   all 17 classes. The available legacy V5-C data-engine cache has 26,739
   rows but zero matching `sample_id` values for the current 1,607-row
   qualification manifest. It also uses a different `samples` schema and
   stores 2,048-dimensional embeddings, whereas this candidate's runner and
   runtime contract require `sample_cache` rows with 512-dimensional
   embeddings. It is therefore not a valid input for this candidate and must
   not be reused to manufacture a scorecard.

5. **The OOD evidence is materially adverse and not independently reviewed.**
   The cross-vendor OOD report records 72.0% false-known (121/168) on two OOD
   sources and states that its ground truth was not independently verified.
   The V4-H calibration report records 41.6% full-corpus and 47.2% holdout
   false-known on its earlier population. These are different populations;
   they must not be blended into one product claim.

6. **Required qualification fields are incomplete across the artifacts.**
   Existing artifacts provide some per-class precision/recall/F1, confusion,
   calibration, and OOD results, but not one reproducible, leakage-controlled,
   cross-vendor, blind-reviewed receipt containing all required fields:
   coverage, confidence, false-known OOD, false-unknown, abstention, and
   per-class confusion/metrics for all 17 classes. The owner-review CSV is a
   generated queue, not evidence that review occurred. The corrected v3
   harness now emits an OOF threshold sweep in `abstention_metrics.json`, adds
   per-class coverage/confidence fields, and records the default acceptance
   policy in `metrics.json` and `ood_results.json`; those outputs still need a
   real rerun and independent review before they become qualification
   evidence. Its temperature scaler is also constrained to a strictly
   positive value so confidence and OOD ordering cannot be invalidated by an
   optimizer step.

   The v3 runner now applies the cross-vendor, OOD-vendor, source-family,
   mixed-label, and frozen-taxonomy checks before model fitting as well as in
   the package validator. Calling the runner directly therefore cannot bypass
   the L-05 metadata gate.

   `tools/classification_benchmark/validate_l05_qualification_package.py`
   now checks that these outputs actually cohere before a qualification claim
   can be made, including an evidence-linked explicit decision for the weak
   `Atmosphere` and `Vocal Loop` classes. Against the current tracked artifacts it fails closed: the
   known set and OOD set each have only one vendor, seven classes lack five
   source families, one family has mixed labels, the scorecard lacks the new
   OOF fields, the confusion and abstention files are absent, and no
   independent blind-review receipt exists.

7. **Fine-grained tags remain evidence-bounded.**
   The 808/Reese and Open/Closed reports document held-out experiments, but
   also record thin-class/vendor limitations and no hard confidence gate.
   Kick Short/Long is an explainable duration split, not a discovered natural
   class. Vocal Loop remains explicitly unreliable cross-vendor (4.5% after
   the BVs fix in the cited report), so it must remain claim-suppressed until
   dedicated remediation and requalification.

8. **The cache did not version the acoustic classifier head separately.**
   AcousticClassifierWeights::modelVersion existed in the compiled runtime,
   but cached ML decisions were keyed only by file identity, embedding-model
   version, feature version, and taxonomy version. A future head update could
   therefore leave a valid embedding paired with an obsolete classification
   after restart. The candidate now persists classification_model_version and
   performs a head-only refresh when it is stale; user overrides remain
   untouched. This is a cache-consistency fix, not a change to weights,
   centroids, thresholds, or OOD policy.

9. **The research scorecard lacked the next recommended OOD signal.**
   The existing corrected runner reported MSP, entropy, and margin, while the
   prior centroid-recalibration null result recommended an energy-based
   experiment as a genuinely different signal. The runner now records a
   numerically stable, research-only `-T*logsumexp(logits/T)` Energy metric
   from cross-fitted logits, with finite-input and positive-temperature guards.
   No full-corpus Energy result is claimed yet: the external cache and OOF
   scratch package must be regenerated under an owner-approved before/after
   receipt before this signal can influence a product decision.

## What is already hardened

- The current runtime truth is documented in `CURRENT_PIPELINE.md` and
  `CLASSIFICATION_SIGNAL_MAP.md`: the 512D embedding is followed by a frozen
  16-class acoustic head and OOD gate, while the product taxonomy remains
  17-class. `Atmosphere` is intentionally heuristic-only until a trained,
  leakage-controlled, independently reviewed head covers it; no 17-class ML
  coverage is implied by the current runtime.

- Invalid/non-finite/overflow-scale embeddings are rejected before
  classification, caching, indexing, similarity, or UMAP use.
- The runtime OOD norm calculation now uses the same double-precision
  accumulation as the input validator, including for near-limit finite
  embeddings; the boundary regression keeps the derived norm and centroid
  score finite.
- OOD output is presented as review/unknown rather than a stale known label;
  evidence source and taxonomy version are visible in the UI.
- The pure taxonomy regression contract now verifies that all 16 frozen
  acoustic-head outputs map to product labels and that `Atmosphere` remains
  outside the acoustic head; this prevents the 16-versus-17 class boundary
  from being silently presented as full ML taxonomy coverage.
- A stale taxonomy row whose source can no longer be decoded now fails closed:
  its derived label is cleared and taxonomy remains at version zero until a
  later scan can produce a current result.
- Winning evidence and taxonomy reset state persist correctly through cache
  hydration; reset clears persisted user taxonomy without deleting the legacy
  instrument field.
- A stale-taxonomy cache refresh now reapplies the frozen acoustic head to a
  valid persisted embedding when the prior row came from `ml_v3` or `ml_ood`,
  so cache hydration cannot silently downgrade an ML result to the heuristic
  baseline or resurrect an OOD label. `UNKNOWN` evidence is now explicitly
  treated as untrusted by the OOD gate. The cache-version regression test and
  pure gate tests cover the preserved-embedding and refreshed-ML paths. The
  native classification, cache/metadata, and fast safety qualification groups
  have now been built and executed locally; the receipt is recorded below.
- Cached acoustic decisions now carry a separate
  classification_model_version, so a changed linear head invalidates only the
  decision and reuses the compatible embedding. The native cache-version test
  covers this head-only refresh, while persisted hydration and numerical parity
  remain green.
- The research runner now records a research-only Energy OOD signal from
  cross-fitted logits using stable log-sum-exp arithmetic; it does not change
  the frozen runtime classifier or production OOD gate. Focused tests cover
  score direction, large finite logits, and invalid inputs.
- The research runner accepts explicit cache/manifest paths and no longer
  writes the runtime classifier-weight header by default; weight export is
  opt-in to an explicit path, preserving the frozen classifier boundary during
  ordinary research runs.
- The research runner now writes generated scorecards to an explicit external
  output directory (defaulting outside the product source tree), rejects
  source-tree output paths including symlink-resolved paths, and copies the
  input manifest into the generated package for provenance.
- Manifest-to-cache matching now prefers exact/relative path identity and
  rejects ambiguous duplicate basenames instead of silently assigning a
  vendor's ground-truth label to the wrong cache row.
- The research runner also fails closed when any declared manifest row lacks a
  usable cached embedding, preventing a partial cache from becoming an
  apparently complete qualification scorecard.
- The research runner now validates the current SQLite cache schema and each
  embedding's exact 512-float, finite, nonzero contract before fitting or
  reporting metrics; legacy tables and incompatible 2,048-dimensional caches
  fail with an explicit contract error.
- The subset-preparation handoff now defaults to the declared corpus root,
  accepts explicit source/output/manifest paths, recognizes the admitted WAV,
  AIFF, and FLAC extensions, supports a no-mutation dry run, and stages all
  copies before replacing a prior subset. Failed coverage validation therefore
  leaves the previous fixture and manifest untouched; a successful replacement
  preserves the prior subset as a recoverable sibling backup.
- The full-corpus builder now supports a manifest-only mode with canonical
  source paths, vendor IDs, candidate source-family keys, and label-authority
  metadata. A fresh no-copy run against the declared corpus produced 5,157
  rows across all 17 classes and 15 vendors, with at least 25 candidate source
  families per known class and three unmatched keyword-split files. This is a
  provenance/inventory receipt only; it does not establish independent labels
  or classifier performance.
- The native `ClassificationBenchmark` scan receipt now records the full file
  path in `filePath` and keeps the basename separately in `fileName`; this is
  required because basename-only receipts cannot disambiguate the corpus's 49
  duplicate-basename groups. A clean `ssm-qualification` build and direct
  classification-group execution have now completed successfully.
- The scan receipt writer now uses a sibling staging file and refuses to
  overwrite an existing output or reuse stale staging state, so a failed or
  repeated qualification attempt cannot silently destroy a prior receipt.
- Pure input-safety, taxonomy, and classification-presentation checks pass;
  the native classification and cache/metadata groups, plus the full-corpus
  scan, also pass. The
  research package remains exploratory because the OOD result is adverse and
  independent review/owner decisions are still missing.

## Latest local execution receipt

On 2026-09-01, the candidate was configured with `ssm-qualification` and
`ssm_qual_classification` built to 100% in the out-of-tree
`_build/ssm-qualification` directory. The direct classification regression
executions passed, including taxonomy, input safety, presentation, audio
features, auto-tagging, collections, clustering, C++/Python parity, bass
timbre, kick length, and hi-hat type. The benchmark's initial no-argument
invocation printed its usage (expected exit 1); the corrected `scan` command
then exited 0.

The cache/metadata group also ran with all eight direct exit codes at 0:
resilience, cache integrity, cache-version enforcement, persisted-cache
hydration, malformed audio, format-aware scanning, multi-instance scanning,
and async sorting. These tests verified malformed-file rejection, WAV/AIFF/
FLAC admission, stale metadata repair, embedding preservation, taxonomy reset
semantics, and concurrent-cache safety.

The fast safety group then ran with all ten direct exit codes at 0: taxonomy,
classifier input safety, classification presentation, XMP writing, path
traversal, duplicate detection, missing-file pruning, general safety
regression, cached reclassification, and read-only safety qualification.

The UI/sample-engine group built successfully. Five of its six direct tests
returned exit 0: browser sorting, favorites, history, sample-engine
integration, and RT deadline/allocation stress. The RT stress receipt reported
0/2,000 deadline misses and zero allocations in tracked callbacks. The
licensing test was not executed because it requires a provisioned license key
and running licensing server; the no-argument invocation only printed usage
and returned 1, so it is an external environment gate rather than a
classification-engine failure. The follow-up environment check found that the
SLO licensing server has no virtualenv and no matching private signing key
(only the DEV/TEST public key is present). The only private signing key found
elsewhere is Platform staging material and its public half does not match the
SLO client key, so it must not be borrowed. The shared checkout also contains
orphaned SQLite `-wal`/`-shm` sidecars without a live server or main database;
they were left untouched. This gate therefore remains unexecuted and is not
evidence of a classifier defect.

Separately, the client licensing URL boundary is now fail-closed: loopback HTTP
is permitted only for the documented DEV/TEST server, while non-local HTTP and
lookalike loopback hosts are rejected; HTTPS endpoints remain supported. The
no-network `TestLicensing --url-policy` regression passes. This hardens the
release boundary without changing classifier weights, OOD thresholds, or
classification decisions.

The aggregate `ssm_qual_full` target then built with exit 0, including the
Standalone, AU, VST3, `BenchmarkScan`, and all qualification groups. The build
emitted a VST3 packaging warning that an artifact with no resources carried a
signature and was replaced with an ad-hoc signature; this is a distribution
signing/resources gate, not evidence of a signed release. A six-file native
`BenchmarkScan` smoke exited 0: full scan 560.385 ms (93.3975 ms/file),
incremental rescan 17.5367 ms, search p50 0.006 ms, and p99 0.013417 ms,
with zero reported RT relevance. These numbers are fixture smoke evidence
only and must not be generalized to full-library performance.

After the licensing URL hardening, the same `ssm_qual_full` target was rerun
at candidate commit `5827c68` and exited 0. The rebuilt
`TestLicensing --url-policy` command also exited 0. This revalidation confirms
the client security-boundary change is included in the aggregate build; it
does not close the separate activation-server/key, signing, or host gates.

After the classifier-head cache-version change, the focused
TestCacheVersionEnforcement target rebuilt successfully. Its native run passed
the fresh-row version assertion, unchanged-cache fast path, stale DSP and
taxonomy selective refreshes, stale classifier-head selective refresh,
malformed-source fail-closed path, user-data preservation, stale embedding
full re-inference, and changed-file invalidation. TestPersistedCacheHydration
and TestAcousticClassifierParity were rebuilt and passed as well. The parity
run retained max logit error 3.16082e-06 and max probability error
2.9717e-07; all V4-H gate regressions passed.

The release-candidate preset was then configured and built with dependency
bundling enabled. VST3, AU, and Standalone all built successfully and emitted
the current SLO artifact names (`SLO.vst3`, `SLO.component`, `SLO.app`). The
identity guard passed, and the release manifest passed against all three
bundles with 96, 95, and 96 files respectively. The dependency preflight also
passed for all three: 88 arm64 Mach-O binaries checked per bundle, no
Homebrew/dev-machine dependency paths, and no missing bundled dependencies.
The repeated `install_name_tool` signature-invalidation warnings are expected
during dependency rewriting; the bundles still require real Developer ID
signing/notarization and clean-machine validation before release.

The scan covered 28,344 source-root files and produced 28,344 unique absolute
paths with valid 512-float embeddings in an isolated external cache. The
labelled manifest contains 5,157 known rows. A documented cross-vendor OOD
overlay contributed 168 real OOD rows from the existing Syd Park, Leichhardt,
and Guitar Loops fixture sources; all 168 original paths were present and
matched by path identity. No audio was copied or modified for this overlay.

The corrected research run loaded 5,157 known and 168 OOD samples, removed 909
duplicate embeddings under source-family leakage control, and retained 4,248
clean known samples across all 17 classes. OOF results were: accuracy 80.5%,
macro-F1 0.699, known coverage 67.7% at the 0.75 abstention threshold,
false-unknown/abstention 32.3%, and OOD false-known 45.8% (77/168). OOD
AUROC was 0.679 (MSP), 0.682 (entropy), and 0.678 (margin); FPR@95 ranged
from 89.9% to 93.5%. These are exploratory measurements, not a ship claim.

The same current native binary was also run directly against the documented
cross-vendor OOD fixture. It rejected 47/168 and accepted 121/168 as known
(72.0% false-known), matching the existing cross-vendor runtime report; every
false-known result was attributed to DSP evidence. This direct centroid-gate
measurement is distinct from the OOF MSP acceptance proxy above, and both are
adverse.

An offline sweep of the native receipt's recorded centroid scores shows that a
single stricter global threshold is not a safe standalone repair: 0.92 would
still accept 38.1% of OOD while rejecting 43.4% of known files; 0.94 would
accept 25.0% of OOD while rejecting 53.8% of known files; 0.96 would accept
3.0% of OOD but reject 77.6% of known files. These are exploratory operating
points, not a threshold-change approval. No production OOD threshold or
classifier weight was changed; the next repair requires an owner-approved
before/after experiment on a broader, independently reviewed OOD population.

The external scratch receipt root was
`/tmp/slo-qualification-64e4d5b.N0Y1o7/`. The known-manifest SHA256 was
`a36a3eed0f2bae8218741733d56f2d8772a648d3d29bcbf7256a62b670665254` and the
native scan SHA256 was
`a6055d579fb4d25ae29a9e2ccfa90980450e837cdf09bc8077dee96101e44559`.
The direct native OOD scan SHA256 was
`bcf3fa73d5af56d85054ac6859e5af53a5174da667ff0c78b045ebffccbbc46f`.
Scratch artifacts are not part of the product repository and must be retained
or regenerated under the runbook before being treated as a durable receipt.

## Required next evidence

1. Retain or regenerate the external native cache, manifest, OOD overlay, and
   OOF research outputs using the runbook. Resolve and owner-approve the
   source-family boundary before converting these exploratory measurements
   into a product claim; the metadata-only preflight is at
   `tools/classification_benchmark/audit_corpus_metadata.py`, and its current
   SHA-bound revalidation is recorded in
   `SLO_CLASSIFICATION_CORPUS_METADATA_PREFLIGHT_V4.json`. Use
   `--weights-output` only inside an owner-approved before/after receipt. Include
   the new Energy score in the regenerated OOD comparison and keep it
   research-only until the comparison is reviewed.
2. Produce a genuinely independent, cross-vendor known/OOD set with explicit
   reviewer identities/roles, review timestamps, disagreement handling, and
   owner sign-off; preserve the raw receipt and do not infer approvals.
3. Publish one qualification receipt with all L-05 metrics and explicit
   abstention/unknown policy, including Atmosphere and Vocal Loop decisions;
   run `validate_l05_qualification_package.py` and retain its passing output
   alongside that receipt.
4. Requalify fine-grained tags under the same leakage and evidence rules before
   expanding the taxonomy or making product claims.

Until those receipts exist, the honest status is **engineering candidate / not
release-qualified**.
