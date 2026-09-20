# SLO Full Qualification Refresh Receipt V1

Date: 2026-08-30

Status: isolated engineering qualification refresh; not a release approval.

## Package identity and boundary

- Branch: `engineering/slo-format-aware-scan-v1`
- Source/package HEAD at observation: `bcdbadfdfe37c8cdcd8164f51d95b17f05757489`
- Build tree: `/tmp/slo-format-aware-scan-v1-build`
- Configuration: Release, arm64, LTO off, Apple dependency bundling off,
  plugin auto-install off
- No shared `products/slo` checkout, production cache, owner audio, holdout,
  secret, model, or customer data was modified.

## Full build

```text
cmake --build /tmp/slo-format-aware-scan-v1-build \
  --target ssm_qual_full --parallel 8
```

Result: exit 0; the full custom qualification target reached 100%. It built
all defined test/benchmark groups plus Smart Sample Manager standalone, AU,
and VST3 targets. Existing compiler warnings and ONNX CoreML partition
warnings were emitted; no build or link error occurred.

CTest is not the suite runner for this project: `ctest --test-dir
/tmp/slo-format-aware-scan-v1-build --output-on-failure` reported no registered
tests. The direct-binary inventory was therefore executed explicitly.

## Direct-binary results

The 38 executable entries in the isolated build were accounted for as:

- 35 ordinary test binaries passed on the first direct run;
- `BenchmarkScan` passed after receiving a disposable 10-file synthetic WAV
  fixture directory;
- `ClassificationBenchmark scan` passed against the same disposable fixture
  directory and wrote its result JSON under `/tmp`;
- `TestLicensing` was not executed as a test because it requires a license key
  and live/dev licensing state; its no-argument invocation returned the
  documented usage message.

Final accounting: **37 passed, 1 owner/environment-blocked, 0 code failures**.

The two initial benchmark no-argument exits were documented usage responses,
not test failures. The ordinary passing set included format-aware scan,
malformed-audio rejection, cache/resilience, path traversal, concurrency,
read-only safety, classification, search, RT deadline, and UI/state coverage.

## Benchmark receipts

Synthetic fixture generation:

```text
python3 products/slo/SmartSampleManager/generate_benchmark_fixtures.py \
  /tmp/nite-slo-benchmark-fixtures-v1 10
```

`BenchmarkScan` result: 10/10 samples processed, full scan 1350.16 ms,
incremental rescan 534.083 ms, search p50 0.014334 ms, p99 0.035792 ms,
RSS after scan 434.328 MB. These are a small synthetic smoke measurement, not
a professional-library capacity claim. The ONNX runtime reported five CoreML
partitions and CPU-assigned shape operations.

`ClassificationBenchmark scan` result: 10 samples scanned and output written
to `/tmp/nite-slo-full-tests-v1/ClassificationBenchmark-scan.json`.

Test-generated diagnostic receipts observed during the run were:

| Receipt | Result | SHA-256 |
| --- | --- | --- |
| `results_readonly_safety_receipt.json` | 4/4 fixture files byte-identical before/after; all checks passed | `03e0f7348e812e24e66490888e9f1a4bccef13a396fa372c14c478b392b2aa35` |
| `results_rt_deadline_stress.json` | 2,000 iterations; 0 deadline misses; 0 allocations | `3e5f6c49472ef500df90d95e051884e24771e7dae19a478ec9945139a97a4664` |

The generated JSON files were exact disposable test outputs and were removed
after their contents and hashes were recorded in this receipt. No tracked
source or pre-existing work was removed.

## Decision and remaining gates

This refresh strengthens the SLO engineering qualification evidence and closes
the local full-build/direct-binary accounting gap. It does not close:

- live standalone/AU/VST3 DAW and UI validation;
- protected evaluation or holdout review;
- production signing/notarisation, clean-machine installation, or licensing;
- MP3 support, which remains outside the declared enabled decoder matrix;
- large-library capacity and controlled performance baselines.

Rollback is to decline this isolated receipt; no production state changed.
