# Low-end stem significance evidence — 15 October 2026

The optional legacy stem-spectrum path now qualifies raw source and actual FFT-window activity before publishing normalized measurements. E2 and the significance checkbox remain open: this receipt does not qualify acoustic significance, whole-song coverage, meters or live producer usefulness.

## Published behavior

- `stem_spectrum_comparison` reuses decoder full-source mono RMS and the existing `rms_db` helper. Both source and exact unwindowed centered FFT-window RMS must be finite and strictly above -60 dBFS. Direct sample callers must supply raw unnormalized mono samples and a finite positive effective sample rate.
- Existing FFT selection remains unchanged: the largest power-of-two window from 256 through 4096 samples, centered at `(sample_count - frame_size) // 2`. Effective decoder rates retain fractional Hz. No new DSP, dependency, threshold, Live write or GPU operation was introduced.
- Missing audio, invalid rates or samples, failed decoding, quiet sources/windows, and ambiguous or invalid identities abstain locally. Other valid stems remain available. Valid zero low-end shares remain measured zeros.
- Existing short FFT bins can overlap between sub and bass. When their combined fraction exceeds one, retain valid per-band measurements but withhold only that combined ranking; do not clamp or change the FFT.
- Handoff carries at most two qualifying ranked previews, selected after excluding invalid entries, with `kenn.low_end_stem.activity.v1` provenance: raw source/window RMS, -60 dBFS floor, effective Hz, sample count, frame size and exact window start. Unknown fields are omitted. Supplied invalid sections retain an empty sentinel.
- Typed evidence and repeated history replay rebuild names from bounded provenance, remove stale stem aliases, and retain scope limitations. Ordinary uploads with no optional stem analysis acquire neither a provenance marker nor a false limitation across replay. Independent whole-mix `low_end_share` remains available.
- Cached chat prose is rebuilt when optional low-end evidence fails or the historical overlap/EQ repair sentence appears, including alongside valid new activity proof. Independently qualified upload, reference, transient and ERB evidence survives.
- HTML reports qualify every ranked row, preserve valid zero and unrelated valid rows, escape names, and withhold saved overlap/carving/clarity claims. Own-spectrum fractions do not compare relative stem levels, establish simultaneous audible masking, select an EQ/sidechain repair, or represent a whole song.

## Verification

All checks used `KENN_LIVE_BACKEND=fake`.

- Producer plus existing Stage 10 integration: **70 passed**.
- Handoff plus backend typed evidence/history: **268 passed**.
- Handoff, HTML, chat payloads, diagnostic loop and server evidence context: **130 passed** before the final whole-mix isolation regression; final chat payload scope: **59 passed**.
- Final combined scoped run across every changed test area plus diagnostic-loop/server-evidence integration: **433 passed** (3.59 s).
- Full backend and mix-review suite: **5989 passed, 55 skipped, 3 pre-existing failures** (138.27 s). The same existing failures are `test_mixing_doctor.py::test_low_end_name_and_fader_overlap_is_an_advisory_candidate`, `test_mixing_doctor.py::test_near_ceiling_track_meter_creates_track_specific_headroom_advisory`, and `test_session_grounded_advice_evaluation.py::test_fixed_session_grounded_benchmark_qualifies`. The Doctor cases expect absent advisory candidates; the retrieval benchmark lacks its embedding index and runs BM25-only. Final added whole-mix isolation and rounding regressions were included in the 433-test scoped run.
- Generated in-memory mono PCM16 WAVs traversed producer, handoff, typed evidence, history and chat: 65,536 samples at 44,100 Hz, center 4096 samples starting at 30,720. Active 80 Hz Bass produced a 0.9954 share; active 8 kHz Air retained measured zero. A quiet source and an active full file with silent center were withheld independently; valid Bass survived. Quiet-only and decode-failure-only inputs retained empty abstention markers. No private or generated audio was committed.
- Removing source/window activity checks caused **5 expected failures**. Bypassing history qualification caused **30 failures**. Restoring the absent-history-marker bug caused **1 failure**. Disabling the chat low-end rebuild gates caused **9 failures**. Each mutation was temporary and restored before final scoped verification.
- An independent read-only review checked the producer geometry, handoff, replay, cached prose, rendering, whole-mix isolation and short-window fractions. Root review additionally caught and covered the absent-marker two-hop replay edge case.

Scoped commands use `products/kenn/apps/backend/.venv/bin/python -m pytest -q -p no:randomly` with `PYTHONPATH=shared:audio-technology/audio-analysis:products/kenn/apps/backend/src:products/kenn/packages/mix-review/core`. Full suite runs from `products/kenn/apps/backend/src` with `PYTHONPATH=../../../packages/mix-review/core ../.venv/bin/python -m pytest -q -p no:randomly kenn/tests ../../../packages/mix-review/tests`.

## Exact changed files

- `audio-technology/audio-analysis/audio_analysis/mixdown/stem_solo.py`: raw activity, provenance, identity isolation, scope wording and short-window ranking abstention.
- `audio-technology/audio-analysis/audio_analysis/integration/handoff.py`: bounded qualified low-end handoff.
- `audio-technology/audio-analysis/audio_analysis/integration/report_rendering.py`: qualified rows and removal of unsupported cached repair claims.
- `products/kenn/apps/backend/src/kenn/core/evidence.py`: typed evidence, bounded replay and measurement scope.
- `products/kenn/apps/backend/src/kenn/server_payloads.py`: cached prose qualification and independent metric preservation.
- Regressions: `Audio_Too/tests/mix/test_mix_review_stage10.py`, audio-analysis tests `test_stem_spectrum_significance.py`, `test_handoff_scenarios.py`, `test_low_end_rendering_significance.py`, `test_report_rendering_scenarios.py`, backend tests `test_evidence.py` and `test_server_payloads.py`.
- Documentation: `products/kenn/KENN_PLAN.md` and this receipt.

## Remaining plan work

Audit remaining significance/publication paths before closing the shared checkbox, then finish the E2 offline comparison, grade determinism and producer listening checks recorded in `KENN_PLAN.md`. This change qualifies a legacy optional preview; it does not certify that preview as a calibrated audibility or masking metric.

## Reuse screen and generated benchmark

# Low-end stem preview activity reuse screen — 15 October 2026

Read-only task evidence, no repository edits/dependencies/new DSP. The KENN plan remains the sole roadmap. Current primary documentation, source and licences were checked again for this slice.

## Exact existing measurement scope

`stem_solo.stem_spectrum_comparison` resolves decoded mono samples then calls `_stem_bands` -> `dsp_metrics.spectrum_magnitudes` -> existing `band_ratios`. The FFT selects the largest power of two `n <= min(4096, len(samples))`; fewer than 256 samples yields no measurement. It takes the CENTER window starting at `(len(samples)-n)//2`, then applies Hann weighting. Thus existing ratios describe a single 256/512/1024/2048/4096-sample centered preview window, not full-file low-frequency energy or simultaneous stem overlap. Reuse this geometry exactly and qualify the unwindowed samples actually fed to this FFT; do not replace it with first-window activity, whole-file RMS or normalized ratios.

Existing `analysis_features.rms_db` computes unweighted mono sample RMS in dBFS. Reusing it on the selected window adds no new Python DSP implementation, in keeping with the plan's C++ constraint. It floors silence at -180 dBFS and returns -99 on empty input; validate finite, numeric decoded samples and nonempty geometry before calling. Its list truth check requires plain lists rather than ndarray input.

Decoder `true_rms` is full-file, pre-preview-filter/decimation mono RMS. It cannot qualify a quiet FFT center surrounded by active audio. Decoder `analysis_sample_rate` is the actual effective preview rate and may be fractional; preserving it avoids shifted frequency bins from integer truncation. Raw supplied `samples` must have an explicit positive finite matching rate. Do not infer simultaneous overlap or common song position across independent center windows.

Counterexample executed against real helper/spectrum: 4096 active samples, 4096 silent samples, 4096 active samples yields whole-source -21.7609 dBFS, actual 4096-sample center -180 dBFS. Whole-file qualification would publish proportions for silence.

## Candidates, sources, licences and fit

- Existing `rms_db`: exact required semantics; no new dependency; generator reduction without signal-sized array allocation. Retain. No rate restriction beyond producer geometry.
- [Python fsum documentation](https://docs.python.org/3/library/math.html#math.fsum), [CPython source](https://raw.githubusercontent.com/python/cpython/3.13/Modules/mathmodule.c), [licence](https://docs.python.org/3/license.html): partial-sum accurate accumulation; generator and partial storage. Already maintained with interpreter under PSF terms. Useful numerical reference, but replacing existing RMS would add unnecessary measurement code.
- [NumPy mean documentation](https://numpy.org/doc/stable/reference/generated/numpy.mean.html), [source](https://raw.githubusercontent.com/numpy/numpy/main/numpy/_core/_methods.py), [licence](https://numpy.org/doc/stable/license.html): explicit float64 accumulation available; list-to-array conversion and squaring require linear temporary storage (4096 float64 samples = 32768 bytes per array). BSD 3-clause, already installed/maintained. Benchmark reference only; adopting another Python implementation does not meet the plan's new-DSP constraint.
- [SciPy norm documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.linalg.norm.html), [licence](https://github.com/scipy/scipy/blob/main/LICENSE.txt): vector 2-norm divided by sqrt(sample count) could calculate RMS, but adds coupling/checking/BLAS surface with no needed semantic benefit over the existing helper. BSD 3-clause. Screened out; no dependency addition proposed.
- Existing KENN native mono summary computes aggregate RMS, while native spectral output carries its own frame RMS/FFT. Requiring a native module for this legacy optional list-based producer adds build/integration/conversion cost and changes window semantics; not necessary to reuse the existing qualified helper. A future full C++ migration needs separate parity/distribution evidence.

No rate-specific DSP is needed for the raw activity reduction; FFT rate correctness remains independent. These primitive references are not evidence of calibrated audibility, same-time source activity, or whole-song representativeness.

## Synthetic benchmark

The earlier ERB benchmark's 4096-sample RMS reduction requirements apply unchanged, but this slice also supports smaller existing FFT windows. Therefore a NEW expanded benchmark was executed rather than extrapolating earlier results: `/tmp/kenn-low-end-rms-benchmark.py`, results `/tmp/kenn-low-end-rms-benchmark.json`.

Real imported `rms_db` versus generator `fsum` and float64 NumPy references, 240 cases: window lengths 256/512/1024/2048/4096, rates 32/44.1/48/88.2/96/192 kHz, 997 Hz active (-20 dBFS) and quiet (-80 dBFS) tones, exact -60 dBFS constant, +/-1e-12 relative-amplitude boundary neighbours, mono-cancelled antiphase zero, one NaN, one infinity. All finite outputs agreed exactly (maximum discrepancy 0 dB). Strict > -60 boundary behaved as intended; NaN and infinity propagated and must be explicitly rejected. This bounded corpus does not establish general numeric conformance or acoustic significance.

Median isolated 4096-list-window time, five repetitions of 100 calls, seeded synthetic data: existing helper 77.74 us; fsum reference 134.90 us; NumPy including list conversion 54.61 us. Same Python 3.13.7/NumPy 2.5.3 arm64 environment as the ERB check. Whole-request latency, sample decoding and FFT costs were not measured here. Retain existing helper: correct scope, tested boundaries, no new DSP/dependency, modest bounded extra cost.
