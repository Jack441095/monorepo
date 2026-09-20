# SLO M-06A Full Qualification Receipt V1

Date: 2026-08-30

Status: fresh isolated engineering qualification; not a release approval.

## Candidate and command

- Source code checkpoint: `68b67009dc25bd9424d0c7cdbc11d2a7ce487c2f`
- Package candidate: `bfe067c5d05edf8b2c7f6775028d39a7e8242a6f`
- Branch: `engineering/slo-m06-canonical-source-v1`
- Build tree: `/tmp/nite-slo-m06-build.Pb959H`
- Configuration: Release, arm64, `SSM_ENABLE_LTO=OFF`, `SSM_TEST_LTO=OFF`,
  Apple dependency bundling off, plugin auto-install off

```text
cmake --build /tmp/nite-slo-m06-build.Pb959H \
  --target ssm_qual_full --parallel 8
```

Result: exit 0; `ssm_qual_full` reached 100% and built all declared
qualification groups plus standalone, AU, and VST3 product targets.

## Executed qualification

Thirty-five ordinary test binaries passed, the malformed-audio test passed,
`BenchmarkScan` passed on ten generated WAV fixtures, and
`ClassificationBenchmark scan` passed and wrote its output receipt. Accounting
is **37 passed, 1 owner/environment-blocked, 0 code failures**.

`TestLicensing` was not counted as a code failure: its no-argument execution
requires a live license key/dev licensing state and is the declared owner/
environment gate.

Synthetic benchmark result:

- 10/10 samples processed;
- full scan: 2201.97 ms / 220.197 ms per file;
- incremental rescan: 547.752 ms;
- search p50/p99: 0.013541 / 0.041791 ms;
- RSS after scan: 412.578 MB.

The benchmark and classification inputs were generated under
`/tmp/nite-slo-m06-fixtures.1lEZHU`; no owner audio or protected corpus was
used. Test-generated diagnostic receipts were hash-recorded and removed from
the candidate after the run:

- read-only safety receipt: `03e0f7348e812e24e66490888e9f1a4bccef13a396fa372c14c478b392b2aa35`
- realtime deadline receipt: `732b2efe4c92004135078d8bb589cdcf066b53d430f95cab48ab2364265960fc`

## Interpretation and next gate

This closes the fresh clean-candidate build/direct-binary qualification gap for
the declared local scope. It does not close live licensing, host/DAW behavior,
large-library capacity, supported-format policy beyond WAV, signing,
notarisation, installation/update, support, rollback observation, protected
data cutover, duplicate-platform consumer migration, or release approval.

The shared `products/slo` checkout and root gitlink remain unchanged.
