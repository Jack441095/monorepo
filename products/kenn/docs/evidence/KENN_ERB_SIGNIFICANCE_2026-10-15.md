# Legacy ERB preview source significance

Recorded 15 October 2026 on `feature/reference-review-grade`, after `1a581cd0`.

## Behavior and limits

Legacy stem masking now qualifies each complete 4096-sample decoded mono preview frame with the existing `analysis_features.rms_db` helper, before spectral normalization. Activity must be strictly greater than -60 dBFS RMS. Only real jointly active frames at matching effective sample rates contribute to a published pair, visibility or heatmap. The preview budget remains 16 frames. Quiet, short, failed, nonfinite, duplicate-identity and unaligned sources abstain rather than acquire spectra from their filenames or repeated tails. An unrelated failed or quiet source does not remove a valid pair.

The decoder adds `preview_analysis_sample_rate`; existing native-rate fields remain compatible. That effective rate travels through stem preparation and both local and queued AutoMix annotation paths, preserving the single-decode optimization. Using effective Hz corrects an existing frequency-axis error for decimated previews; it changes their reported frequency interpretation. This is an explicit correction, not numerical parity with the erroneous native-rate result. Primary and piggyback decoding agree under the corrected geometry. No decoder, filter, resampler, RMS algorithm, FFT or ERB model was added.

The versioned `kenn.erb_masking.activity.v1` receipt records source identities, effective rates, complete/active frame counts and positive jointly active pair counts. Handoff and typed evidence project bounded fields: at most 64 sources, 96-character exact names, 16 frames per source and one entry per unordered pair. Ranking covers exactly the participating stems. Visibility zero is valid. Legacy/malformed sections become abstention markers; scalar aliases cannot qualify them. History rebuilds facts from validated provenance. Cached chat prose, including the actual old “simultaneous-masking visibility” sentence, is rebuilt when optional evidence is unqualified while independent upload, reference and transient evidence survives.

ERB visibility remains an uncalibrated relative-spectrum preview. It establishes neither whole-song audible masking severity nor a causal diagnosis. Unsupported carving suggestions and clarity predictions are empty. Deterministic critique, LLM input, evidence observations and diagnostic rationale carry the narrower interpretation; absent optional stem analysis stays absent.

## Changed files

Paths are relative to the monorepo root.

- `audio-technology/audio-analysis/audio_analysis/mixdown/stem_analysis.py`: real-frame qualification, joint-frame comparisons, explicit abstentions and withheld repair predictions.
- `audio-technology/audio-analysis/audio_analysis/utils/audio_io.py` and `mixdown/stem_prep.py` under the same `audio_analysis` directory: effective preview Hz metadata and propagation.
- `audio-technology/audio-analysis/audio_analysis/analysis_core/analysis_core.py`: corrected wrapper contract.
- `audio-technology/audio-analysis/audio_analysis/integration/handoff.py`: shared bounded projection and abstention marker.
- `audio-technology/audio-analysis/audio_analysis/mix_review/mix_review_critique.py`: qualified critique input and relative-preview wording.
- `Audio_Too/scripts/automix_local.py` and `Audio_Too/server/app/automix_worker.py`: retain effective preview metadata at actual call sites.
- `products/kenn/apps/backend/src/kenn/core/evidence.py`: typed provenance, history requalification, alias removal and scope limitations.
- `products/kenn/apps/backend/src/kenn/core/diagnostic_framework.py`: narrow the existing preview rationale; no threshold change.
- `products/kenn/apps/backend/src/kenn/server_payloads.py`: unified optional-section rebuilding, bounded ERB summary and historical prose gate.
- Producer tests: `test_stem_masking_significance.py`, `test_stem_analysis_masking_preview.py`, `test_stem_analysis_scenarios.py`, `test_erb_critique_significance.py`, `test_handoff_scenarios.py` in `audio-technology/audio-analysis/tests`; actual local/queued integration in `Audio_Too/tests/automix/test_masking_preview_handoff.py`.
- Backend tests: `test_evidence.py` and `test_server_payloads.py` in `products/kenn/apps/backend/src/kenn/tests`.
- `products/kenn/KENN_PLAN.md` and this receipt: progress, reuse evidence and remaining work.

## Verification

Scoped producer, handoff, critique and actual AutoMix route verification: **138 passed** in 4.92 seconds. Command from the monorepo root:

```sh
KENN_LIVE_BACKEND=fake \
PYTHONPATH=audio-technology/audio-analysis:shared:products/kenn/apps/backend/src:products/kenn/packages/mix-review/core \
products/kenn/apps/backend/.venv/bin/python -m pytest -q -p no:randomly \
  audio-technology/audio-analysis/tests/test_stem_masking_significance.py \
  audio-technology/audio-analysis/tests/test_stem_analysis_masking_preview.py \
  audio-technology/audio-analysis/tests/test_stem_analysis_scenarios.py \
  audio-technology/audio-analysis/tests/test_erb_masking.py \
  audio-technology/audio-analysis/tests/test_erb_critique_significance.py \
  audio-technology/audio-analysis/tests/test_handoff_scenarios.py \
  Audio_Too/tests/mix/test_mix_review_stage10.py \
  Audio_Too/tests/automix/test_masking_preview_handoff.py \
  Audio_Too/tests/automix/test_automix_local.py \
  Audio_Too/tests/automix/test_automix_worker.py
```
 Tests cover silence, exact/above floor, cancellation, malformed/nonfinite audio, short and missing tails, alternating activity, mismatched effective geometry, valid-zero retention and unrelated-source isolation. A genuinely decimated 100 Hz generated tone checks corrected frequency interpretation. Local and queued integration tests reject a second decode and verify 22050 Hz effective previews with 16 jointly active frames.

Scoped backend command from the monorepo root:

```sh
KENN_LIVE_BACKEND=fake products/kenn/apps/backend/.venv/bin/python -m pytest -q -p no:randomly \
  products/kenn/apps/backend/src/kenn/tests/test_server_payloads.py \
  products/kenn/apps/backend/src/kenn/tests/test_evidence.py \
  products/kenn/apps/backend/src/kenn/tests/test_diagnostic_loop.py \
  products/kenn/apps/backend/src/kenn/tests/test_server_evidence_context.py
```

Result: **252 passed**. Independent review caught and fixed the actual historical critique wording bypass and absent-section critique noise. Gate mutations produced 3 failing producer floor regressions, 27 failing history regressions and 4 failing legacy cache regressions; each source was restored before final scoped verification.

Generated in-memory PCM16 WAV smoke traversed producer → handoff → typed evidence → history → chat. A 65536-sample 44100 Hz pair (80 Hz at amplitude 0.2 and 110 Hz at 0.15) retained 16 jointly active frames and Kick visibility 0.915. Adding a quiet 160 Hz source at amplitude 0.00001 or a failed decode preserved that pair. Quiet-only and invalid-WAV-only cases published no visibility facts. No audio files were retained.

Full backend/mix-review suite from `products/kenn/apps/backend/src`:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH=../../../packages/mix-review/core \
  ../.venv/bin/python -m pytest -q -p no:randomly kenn/tests ../../../packages/mix-review/tests
```

Result: **5936 passed, 55 skipped, 3 failed** in 134.45 seconds. Same pre-existing failures as the preceding transient receipt:

- `test_mixing_doctor.py::test_low_end_name_and_fader_overlap_is_an_advisory_candidate`: expected advisory absent (`StopIteration`).
- `test_mixing_doctor.py::test_near_ceiling_track_meter_creates_track_specific_headroom_advisory`: expected advisory absent (`StopIteration`).
- `test_session_grounded_advice_evaluation.py::test_fixed_session_grounded_benchmark_qualifies`: missing embedding index leaves retrieval BM25-only.

The final scoped backend run additionally covers the historical-phrase regression added after the full run. No new failures appeared. No dependency, CI, permission, GPU or real Live changes.

## Remaining work

E2 and the significance checkbox remain open. Next: raw per-stem activity before low-end rankings, then remaining source-significance paths. This slice does not qualify the ERB model against listening judgments, approve EQ repairs, or complete meter conformance.

## Reuse screen and benchmark

## Existing code and semantics

- `analysis_core/analysis_features.py:rms_db` already computes unweighted mono sample RMS in dBFS with `sqrt(sum(x*x)/len(x))`, floors silence at -180 dBFS, returns -99 dBFS for an empty list. It neither normalizes nor applies loudness weighting. Reuse it on each existing complete 4096-sample preview frame; it can establish preview-frame activity, not frequency masking audibility. Reject nonfinite/malformed samples before using its result. Use plain lists: `if not samples` is ambiguous for ndarray input.
- Decoder `audio_io.py:read_wav_mono` already returns full-file mono `true_rms`, measured BEFORE preview low-pass/decimation. That cannot prove simultaneous preview-frame activity and cannot qualify ERB fallback profiles.
- Both legacy preview routes decimate across the file using integer `frame_count // 65536`, not a contiguous first 1.5 seconds. Preview samples are low-pass filtered when decimating. `sample_rate` and `preview_sample_rate` deliberately retain the NATIVE rate; `analysis_sample_rate` alone reflects the primary preview's effective rate. Existing `stem_analysis.py` uses native rate on either path. Therefore comparing frame indices across stems requires proven equal effective sampling geometry and source origin, not merely equal nominal rates. Preserve compatibility fields; add separate provenance or withhold qualification where geometry is unknown. This slice explicitly corrects the effective-rate frequency axis and verifies it with generated tones, as described above.
- Existing native `kenn_dsp_native.cpp` computes mono channel RMS in bulk summaries, and unwindowed frame RMS alongside FFT spectral output. The former is aggregate only; the latter adds FFT allocation/coupling and float32 conversion to otherwise list-based legacy code. This does not save integration effort for the bounded metadata task. Do not add a native build/runtime requirement.
- KENN_PLAN says all NEW DSP is C++, no new Python/numpy DSP. Reusing existing `rms_db` is the appropriate path; benchmark alternatives below are references, not proposed replacement implementations.

## Current upstream source / licence screen

Inspected on 15 October 2026:

- [Python math docs](https://docs.python.org/3/library/math.html#math.fsum) and [CPython 3.13 source](https://raw.githubusercontent.com/python/cpython/3.13/Modules/mathmodule.c): `fsum` retains partial sums to reduce accumulation error; it still requires squaring samples and computing RMS. It adds no sample-rate restriction but would be a new measurement implementation here. [Python licence](https://docs.python.org/3/license.html): PSF terms and applicable component notices; already shipped with the interpreter.
- [NumPy mean docs](https://numpy.org/doc/stable/reference/generated/numpy.mean.html), [norm docs](https://numpy.org/doc/stable/reference/generated/numpy.linalg.norm.html), [reduction source](https://raw.githubusercontent.com/numpy/numpy/main/numpy/_core/_methods.py): float64 accumulation can be requested explicitly. Array conversion and a squared-sample temporary cost linear allocation for list input; existing ndarray input avoids conversion. [NumPy licence](https://numpy.org/doc/stable/license.html): BSD 3-clause. NumPy is already present, but a new RMS implementation is unnecessary under the C++ constraint.
- [SciPy norm docs](https://docs.scipy.org/doc/scipy/reference/generated/scipy.linalg.norm.html), [source](https://raw.githubusercontent.com/scipy/scipy/main/scipy/linalg/_misc.py), [licence](https://github.com/scipy/scipy/blob/main/LICENSE.txt): vector 2-norm divided by sqrt(sample count) can produce RMS, uses NumPy/BLAS machinery with finite checking. BSD 3-clause. Adds integration surface, conversion/checking and dependency coupling for no required new semantics; screened out before shortlist benchmark. No additional dependency or licence adoption proposed.

These methods are sample-value reductions; any positive rate is accepted mathematically. The spectral tool's own rate/decimation geometry remains a separate qualification obligation. Maintained Python/NumPy/SciPy implementations are suitable numerical references; their upstream claims do not qualify KENN's producer.

## Synthetic shortlist benchmark

Executed in the existing backend venv, importing the real `analysis_features.rms_db`. Script `/tmp/kenn-erb-rms-benchmark.py`; full results `/tmp/kenn-erb-rms-benchmark.json`. Python 3.13.7; NumPy 2.5.3; macOS arm64. No audio files, GPUs or external services.

4096-sample windows at 32, 44.1, 48, 88.2, 96 and 192 kHz: 997 Hz tone scaled to -20 dBFS; -80 dBFS tone; constant exactly -60 dBFS; boundary +/-1e-12 relative linear amplitude; mono-cancelled antiphase zero; one NaN; one infinity. All finite cases agreed exactly in returned dBFS among existing helper, fsum reference and float64 NumPy reference in this corpus (maximum absolute discrepancy 0 dB). Exact -60 dBFS stayed inactive with strict `> -60`; below/above cases resolved correctly. Silence was -180 dBFS. NaN/inf propagated from every candidate, proving explicit finiteness qualification is necessary. This is not a broad numerical-conformance or acoustic-significance claim.

Median microseconds per 4096-sample list window, 5 repeats of 100 calls on fixed RNG seed 20261015:

| Candidate | Time | Allocation / integration |
| --- | ---: | --- |
| Existing rms_db | 80.81 us | Generator reduction, no signal-sized array; reuse existing import |
| fsum reference | 141.73 us | Generator plus partial sums; new algorithm unnecessary |
| NumPy float64 reference | 55.82 us | Includes list-to-array conversion; 32768-byte float64 input plus squared temporary (excluding allocator overhead) |

Sixteen existing-helper frames cost approximately 1.29 ms per stem in isolation. Actual producer includes spectral analysis, input validation and slicing; do not call this a complete-request speed measurement. Retain the existing RMS helper: all required synthetic boundaries agree, no dependency or new DSP is needed, and it measures exactly the unnormalized mono preview being passed into legacy ERB analysis.
