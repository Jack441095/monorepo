# SLO Qualification Runbook V1

This is the supported local entry point for SLO qualification. It documents
the current CMake target groups and the separate step that executes the
resulting binaries. The custom `ssm_qual_*` targets build dependencies only;
they do not run tests, and the project currently has no CTest registration for
these binaries.

## Configure and build

Run from `SmartSampleManager/`:

```bash
cmake --preset ssm-qualification
cmake --build --preset ssm-qualification --target ssm_qual_classification
```

The out-of-tree build directory is `../_build/ssm-qualification/`. The
qualification preset is Release with plugin LTO enabled and test LTO disabled.
It is distinct from `ssm-dev` and `ssm-release-candidate`.

Replace `ssm_qual_classification` above with one of these risk-surface groups:

| Build target | Executable targets |
| --- | --- |
| `ssm_qual_fast_regression` | `TestTaxonomy`, `TestAcousticClassifierInputSafety`, `TestClassificationPresentation`, `TestXmpWriter`, `TestPathTraversal`, `TestDuplicateDetection`, `TestPruneMissing`, `TestSafetyRegression`, `TestCachedReclassification`, `TestReadOnlySafetyQualification` |
| `ssm_qual_cache` | `TestResilience`, `TestCacheIntegrity`, `TestCacheVersionEnforcement`, `TestPersistedCacheHydration`, `TestMalformedAudio`, `TestFormatAwareScan`, `TestMultiInstance`, `TestSortLibraryAsync` |
| `ssm_qual_classification` | `TestTaxonomy`, `TestAcousticClassifierInputSafety`, `TestClassificationPresentation`, `TestAudioFeatures`, `TestAutoTagging`, `TestSmartCollections`, `TestMapClusters`, `TestAcousticClassifierParity`, `ClassificationBenchmark`, `TestBassTimbre`, `TestKickLength`, `TestHiHatType` |
| `ssm_qual_intelligence` | `TestEmbeddingQuality`, `TestFindSimilar`, `TestFindSimilarWeighted`, `TestTimbreRefinement`, `TestReferenceSearch`, `TestNearDuplicates` |
| `ssm_qual_ui` | `TestPrecisionBrowserSorting`, `TestFavorites`, `TestHistory`, `TestLicensing`, `TestSampleEngine`, `TestRtDeadlineStress` |
| `ssm_qual_full` | All groups above, `BenchmarkScan`, and the VST3/AU/Standalone plugin builds |

## Execute the binaries

After building a group, execute its binaries directly from the build tree.
For example, the classification group is:

```bash
build_dir="../_build/ssm-qualification"
for test in \
  TestTaxonomy \
  TestAcousticClassifierInputSafety \
  TestClassificationPresentation \
  TestAudioFeatures \
  TestAutoTagging \
  TestSmartCollections \
  TestMapClusters \
  TestAcousticClassifierParity \
  ClassificationBenchmark \
  TestBassTimbre \
  TestKickLength \
  TestHiHatType
do
  "$build_dir/$test"
done
```

Use the same pattern for the other rows in the matrix. Run each duplicate
target only once when executing `ssm_qual_full`; plugin targets are build
artifacts and are validated separately through the host/release procedures.

The licensing target has two distinct execution paths. The no-network URL
policy regression can always run directly:

```bash
"$build_dir/TestLicensing" --url-policy
```

This verifies that loopback HTTP is allowed only for the local DEV/TEST mock,
remote HTTPS is accepted, and remote plain HTTP/lookalike hosts are rejected.
The end-to-end activation path remains a separate command,
`TestLicensing <provisioned-key>`, and requires the matching DEV/TEST private
key, local server, and a clean test application-data directory. A missing
activation environment must not be reported as a classifier failure.

## Evidence to record

Every qualification receipt must bind the exact candidate SHA, preset, build
directory, target group, executable command, exit status/output, host and
toolchain, dataset/data class, and limitations. A successful build is not a
successful test execution. Native/audio, host, corpus, licensing, signing,
installation, support, rollback, and owner-decision gates require their own
direct receipts and must not be inferred from this runbook.

Classification research artifacts must be written outside the product source
tree. Use the v3 runner with explicit input and output paths, for example:

```bash
python3 tools/classification_benchmark/run_research_v3.py \
  --db-path "/path/to/authorised/sample_cache.sqlite3" \
  --manifest-path "/path/to/authorised/dataset_manifest.json" \
  --output-dir "/path/to/qualification-artifacts/slo-v3"
```

The runner rejects an output directory inside `SmartSampleManager/` and copies
the input manifest into the generated package for provenance. `--weights-output`
is optional and remains reserved for an owner-approved experiment receipt.

## Full-corpus cache handoff

When CPU capacity is available, use the manifest-only builder first and keep
all generated data outside the product tree:

```bash
source_root="/Volumes/Jack_Gandy_1TB_SSD/testing-for-NITE-DSP/sample_pack_testing"
artifact_root="/path/to/qualification-artifacts/slo-v3"
manifest_path="$artifact_root/dataset_manifest.json"
scan_run="$artifact_root/native-scan"
build_dir="/absolute/path/to/_build/ssm-qualification"

mkdir -p "$artifact_root" "$scan_run"
python3 tools/classification_benchmark/build_real_corpus_v2.py \
  --source-root "$source_root" \
  --manifest-only \
  --manifest-path "$manifest_path"

# ClassificationBenchmark clears and repopulates fixtures/cache relative to
# its working directory.  Keep that working directory disposable and outside
# SmartSampleManager so the production cache cannot be touched.
(cd "$scan_run" && \
  "$build_dir/ClassificationBenchmark" \
    scan "$source_root" "$artifact_root/native_scan.json")

db_path="$scan_run/fixtures/cache/sample_cache.sqlite3"
python3 tools/classification_benchmark/run_research_v3.py \
  --db-path "$db_path" \
  --manifest-path "$manifest_path" \
  --output-dir "$artifact_root/research"
```

The `build_dir` path above is illustrative: replace it with the absolute
qualification build path. The scan receipt must record the exact candidate SHA, source root,
manifest SHA, scratch working directory, database path, sample count, and exit
status. This sequence is a cache-generation/evaluation run only; it does not
constitute independent label review or release approval.

For acoustic-tempo qualification, use the isolated native receipt mode:

```bash
tempo_receipt="$artifact_root/tempo.json"
"$build_dir/ClassificationBenchmark" tempo "$source_root" "$tempo_receipt"
```

This evaluates both 5-second and bounded 20-second views, reports the fused
agreement result, and compares only against plausible BPM tokens in filenames.
Those filename values are reproducible references, not independent human
ground truth; keep the mode review-only until a collection-held-out tempo set
is available.

## Current boundary

This runbook is procedural evidence only. The 2026-09-01 local execution has
demonstrated clean native classification, cache/metadata, fast-safety,
intelligence, and UI/sample-engine builds, direct regression execution, and an
isolated full-source-root scan, aggregate full qualification build, and
small-fixture benchmark smoke. The release-candidate preset also produced
SLO.vst3, SLO.component, and SLO.app with bundled-dependency and release
manifest checks passing. The no-network licensing URL-policy regression passes,
but licensing activation was not run because its server/key environment was
unavailable; the release bundles still need Developer ID signing, notarization,
and clean-machine validation. The execution has not established independent
label review, weak-class decisions, release approval, or a passing L-05 package
validator result. Preserve the external scratch artifacts or repeat the
sequence before treating the execution as a durable release receipt.
