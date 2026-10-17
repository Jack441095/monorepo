# Native ERB spectrum accumulation, 17 Oct 2026

`compute_erb_spectrum` in
[psychoacoustics.py](../../apps/backend/src/kenn/core/psychoacoustics.py)
moved from NumPy (`np.arange`, `np.log10`, `np.bincount`) to the C++ extension:
`erb_spectrum` in
[kenn_dsp_native.cpp](../../tooling/native/dsp_core/kenn_dsp_native.cpp),
wrapped by `native_fft.erb_spectrum` in
[native_fft.py](../../apps/backend/src/kenn/core/native_fft.py).
`psychoacoustics.py` no longer imports NumPy.

## What it computes

- Maps one-sided FFT magnitude bins (`i = 0 .. N-1`, `f = i * sample_rate / fft_size`)
  within `20 Hz .. 20 kHz` onto `num_bands` equal-ERB steps using Glasberg &
  Moore (1990), `E(f) = 21.4 * log10(0.00437 * f + 1.0)`.
- Sums `mag^2` into `energies[band_idx]` where
  `band_idx = int((E(f) - E(20)) / (E(20000) - E(20)) * num_bands)` lies in
  `0 .. num_bands - 1`.
- Rejects non-finite (`NaN`/`Inf`) magnitudes and `num_bands` outside `1..4096`
  with `ValueError` in C++; returns `[]` for `num_bands <= 0` and `[0.0] * num_bands`
  for empty spectra or non-positive `sample_rate`/`fft_size`.
- Fixes a Python edge case where passing a 1D NumPy array directly to
  `compute_erb_spectrum` raised `ValueError` on `if not magnitudes:`.

## Parity and timing

Measured on one arm64 Mac against the deleted NumPy implementation:

| Check | Cases | Max abs energy difference | Timing |
| --- | --- | --- | --- |
| Synthetic random spectra (`sr` in `22.05, 44.1, 48, 96 kHz`, `fft_size` in `1024..16384`, `num_bands` in `24, 32, 40, 64`) | 80 | `2.274e-13` | — |
| 20 real corpus stems (`Audio-Assets/SLO-Testing/testing_track_stems`, 4096-pt FFT, 40 ERB bands, 100 passes = 2000 calls) | 20 stems (2000 calls) | `5.421e-20` | `105.23 ms` → `79.33 ms` |

## Portable scalar build

Built with `-DKENN_USE_ACCELERATE=OFF` and with Accelerate enabled: all 29
tests across `test_psychoacoustics.py` (7 tests, including 2 new tests for
NumPy array input, out-of-band frequencies, non-finite magnitudes, and band
count bounds) and `test_reference_matcher.py` (22 tests) pass on both builds.
