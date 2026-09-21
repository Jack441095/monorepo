# KENN Phase 4 Release Qualification Handoff

For the shortest path to closing the remaining external gates, use
`CPP_DSP_PHASE4_UNBLOCK_CHECKLIST.md` alongside this handoff.

**Status (2026-09-20):** internal representative-audio evidence complete;
release qualification remains open for rights-cleared matrix coverage,
cross-platform host validation, and signing credentials.

The external-fixture harness has been smoke-tested against the ten internal
anonymous WAV samples; see `CPP_DSP_PHASE4_INTERNAL_FIXTURE_SMOKE_RECEIPT.md`.
That smoke run is intentionally not counted as the real-mix gate because the
files are short mono samples rather than full mixes.

The repository's AutoMix listening benchmark independently records the licensed
corpus as `0/20`, so no checked-in audio is being promoted to a real-mix claim.

The supplied `testing-assets` directory now provides an internal 8-mix corpus;
the complete reference/native result is recorded in
`CPP_DSP_PHASE4_TESTING_ASSETS_RECEIPT.md`. It clears parity and bounded
analysis, but the native path averages `0.98962x` end to end, so the release
default remains Python. Its existing seven-track AutoMix validation is
recorded in `CPP_DSP_PHASE4_AUTOMIX_ASSETS_RECEIPT.md`; it provides real
multitrack evidence. A deterministic 1/8/16/32 subset matrix has now also
completed with safety passes, but all four advisory technical scores remain
below the 65-point quality threshold; 64 stems are unavailable.

The existing stem-masking path was profiled as a follow-on candidate: an
8-stem, 30-second synthetic request spends 280.679 ms cumulative in
`_band_energy_over_time` (receipt:
`results/phase4_masking_profile.json`). This is prioritization evidence only;
it does not justify release promotion by itself. A portable scalar native POC
was measured and rejected as slower than NumPy, then an Accelerate/vDSP build
was measured at 2.51x faster with exact findings parity on the bounded fixture;
both decisions are recorded in `CPP_DSP_PHASE4_MASKING_NATIVE_POC_RECEIPT.md`
and `CPP_DSP_PHASE4_MASKING_ACCELERATE_RECEIPT.md`.

A fresh real-mix cProfile run now shows that the next complete-request target
is PCM decode plus bulk channel statistics/correlation, not another isolated
FFT. See `CPP_DSP_PHASE4_REAL_MIX_PROFILE_RECEIPT.md` and its JSON receipt.

That bounded bulk-metrics slice now passes the eight-mix parity and performance
gate: `0.522969x` native/reference latency with 36.5% lower peak RSS. It is
still opt-in pending rights-cleared and cross-platform release evidence; see
`CPP_DSP_PHASE4_NATIVE_BULK_METRICS_RECEIPT.md`.

The native spectral call now also emits the optional 40-band LTAS levels in the
same FFT pass, removing the Python report rescan when LTAS is requested. Native
and forced-reference LTAS rows are exact on the deterministic fixture; the
bounded warm complete-request receipt is `CPP_DSP_PHASE4_LTAS_RECEIPT.md`.

The same call now emits aggregate and localized dominant peaks, removing the
Python local-max scan in native mode while preserving the reference fallback;
see `CPP_DSP_PHASE4_PEAK_REPORT_RECEIPT.md`.

The follow-on native PCM decoder now removes the remaining Python byte-to-sample
loop for the opt-in path. Direct 16/24/32-bit integer and 32-bit float parity
passes, and the eight-mix internal timing receipt records a 99.0% lower
complete-request time than the forced Python reference. This remains internal
`TODO-vendor-pack` evidence; see `CPP_DSP_PHASE4_NATIVE_DECODER_RECEIPT.md`.
The same native spectral call now returns localized window RMS and band energy,
reducing the warm synthetic request from 21.027 ms to 5.163 ms; the receipt
records the refreshed 99.0% eight-mix improvement.
The decoder now transfers its channel allocations directly to nanobind-owned
NumPy arrays, avoiding a second full PCM copy; see
`CPP_DSP_PHASE4_DECODER_OWNERSHIP_RECEIPT.md`.
Spectral, LTAS, masking, and window-RMS result vectors now use the same
nanobind ownership handoff, avoiding a second result-array allocation; see
`CPP_DSP_PHASE4_SPECTRAL_OWNERSHIP_RECEIPT.md`.

A separate zero-lag stereo-correlation POC reduced that isolated stage but
improved complete requests only 9.0–10.1% on two long supplied mixes, below the
25% adoption gate. It was removed after measurement; see
`CPP_DSP_PHASE4_CORRELATION_POC_RECEIPT.md`.

## What is already green

- Python reference and scalar C++/nanobind spectral paths are numerically
  equivalent on the deterministic comparison fixture.
- The native path is approximately 43–50% faster end to end on the bounded
  WAV benchmark with a 1.37% peak-RSS increase.
- The shared realtime core passes numerical parity, concurrent stress, and
  callback-budget checks.
- Universal macOS Release VST3 and AU bundles contain both `arm64` and
  `x86_64` slices.
- Independent macOS AU/VST3 and Ableton Live discovery/load validation is
  recorded in `docs/evidence/KENN_PLUGIN_HOST_VALIDATION_2026-09-07.md`.
  That receipt explicitly records ad-hoc signing and therefore does not clear
  the distributable-archive gate or Windows validation.
- A cross-platform native-wheel workflow now builds on macOS 14 and Windows
  2022, and the CMake install rules include Windows `.pyd` runtime payloads.
- The wheel workflow runs the reusable `tooling/scripts/test_native_dsp.py`
  smoke/parity contract after installation. It checks all required exports,
  supported PCM decoder metadata/sample parity, deterministic mono/stereo
  metrics, finite spectral output, and malformed input rejection; the same
  contract passes against the macOS Accelerate and scalar fallback builds
  locally.
- The same wheel job runs `tooling/scripts/test_native_fallback.py` with
  `KENN_DSP_NATIVE=0`, proving the installed package exposes a visible,
  working Python-reference fallback when native DSP is disabled.
- The no-copy stem-matrix helper and its tests now cover the complete
  1/8/16/32/64 selection contract and fail-closed rights labels using
  generated-internal fixtures. That proves the harness path only; it does not
  substitute for owned/licensed real-mix or AutoMix evidence.
- A fresh end-to-end synthetic matrix smoke passes the complete WAV analysis
  request at 1/8/16/32/64 stems in both reference and native processes; see
  `results/phase4_synthetic_stem_matrix_smoke.json`. The receipt is explicitly
  harness-only and makes no real-mix or perceptual claim.
- The same workflow now has a Windows 2022 VST3 compile job; its hosted-runner
  result and DAW loading remain required evidence before claiming Windows
  support.
- The recovered AutoMix C++ kernels now compile into the optional KENN nanobind
  wheel and pass deterministic binding/finite-output smoke checks through the
  `automix` submodule. Runtime dispatch into the full AutoMix worker and
  complete-request parity are still pending because the current checkout does
  not contain the active Python worker sources and the supplied corpus remains
  `TODO-vendor-pack`; see `CPP_DSP_PHASE4_AUTOMIX_DISPATCH_RECEIPT.md`.

## Required inputs

1. At least five owned or licensed representative real-mix WAV files, with
   source hash, sample rate, channel count, and duration recorded.
2. Rights-cleared AutoMix projects or exported stem sets covering 1, 8, 16,
   32, and 64 stems where those workflows are intended to be supported. The
   supplied corpus currently has 15, 18, 19, 22, 44, and 62 WAV stems and is
   marked `TODO-vendor-pack` in its manifest, so it is not a substitute. A
   no-copy selection manifest prepares 1/8/16/32-stem subsets from
   `al_james`; those renders are recorded as safety-only evidence, and no
   64-stem source is available.
3. A supported Windows x64 build runner.
4. Developer ID and notarytool credentials for the macOS release archive.

Do not copy third-party audio into the repository without confirming its
licence. Keep private fixtures outside Git and pass their paths to the
qualification harness.

The no-copy matrix helper reports `rights_cleared: false` for unverified labels
and supports a fail-closed `--require-rights-cleared` mode. The supplied
`TODO-vendor-pack` manifest intentionally fails that mode until its terms are
verified.

## Qualification sequence

1. Run the Python reference and native candidate in fresh processes against
   every fixture. The benchmark accepts private WAVs without copying them
   into Git, for example:

   ```sh
   python3 tooling/scripts/benchmark_audio_analysis.py \
     --fixture /private/path/mix-a.wav \
     --fixture /private/path/mix-b.wav \
     --repeats 10 \
     --json-out /private/path/kenn-real-mix-reference.json
   ```

   Set `KENN_DSP_NATIVE=1` and use the native-built environment for the second
   run; the receipt records fixture hashes and WAV metadata for comparison.
2. Compare complete-request latency, p95/p99 tails, peak RSS, output hashes,
   and declared numerical tolerances; include binding/copy overhead.
3. Run the AutoMix end-to-end matrix, not only isolated kernels.
4. Load the built VST3 and AU in the supported DAW matrix after fully
   restarting each host.
5. Run the Windows x64 build and repeat parity, sanitizer, and performance
   checks.
6. Use `tooling/scripts/package_macos_plugins.sh --preflight`, then sign,
   notarize, staple, Gatekeeper-check, and checksum the release archive.

The automated native-wheel check is defined in
`.github/workflows/kenn-dsp-native.yml`; it is evidence for the Python native
package only, not a substitute for Windows VST3 host validation.

The native spectral path remains opt-in (`KENN_DSP_NATIVE=1`) until this
qualification receipt records a passing real-mix and cross-platform result.
