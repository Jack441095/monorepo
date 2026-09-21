# C++ DSP Phase 4 unblock checklist

The native bulk-metrics candidate is technically qualified but remains
opt-in. These are the remaining inputs required before release promotion.

## 1. Rights-cleared audio

Provide private paths (outside Git) to at least five owned or licensed
representative mix WAVs, plus an AutoMix/stem set covering 1, 8, 16, 32, and
64 stems where those workflows are supported. The manifest must include:

- source SHA-256, sample rate, channel count, and duration;
- a verified license label accepted by
  `tooling/scripts/prepare_stem_count_matrix.py`;
- `--verify-files --require-rights-cleared` passing.

Then run fresh reference/native processes and attach the parity, timing, and
peak-RSS receipts. The current `TODO-vendor-pack` manifest must not be
relabelled without verifying its terms.

## 2. Windows and host validation

The macOS AU/VST3/Ableton load check is already recorded in
`docs/evidence/KENN_PLUGIN_HOST_VALIDATION_2026-09-07.md`; it is ad-hoc-signed
evidence, not distribution approval. The remaining platform work is to run the
`kenn-dsp-native.yml` wheel and Windows VST3 jobs on the supported Windows x64
runner. Preserve the wheel smoke, fallback smoke, sanitizer/CTest logs, and
the produced VST3 bundle path. Load the bundle in each supported DAW after a
clean host restart and record the host/version/architecture result.

## 3. macOS distribution credentials

On the release owner’s Mac, install a Developer ID Application identity and
create a `notarytool` keychain profile. Verify the non-mutating preflight:

```sh
bash tooling/scripts/package_macos_plugins.sh --preflight
```

Only after it passes, create the signed/notarized/stapled archive and attach
its checksum plus clean-host AU/VST3 validation receipt.

## Promotion rule

Until all three sections have current evidence bound to the reviewed source
revision, keep `KENN_DSP_NATIVE=1` opt-in and retain the Python reference as
the default.
