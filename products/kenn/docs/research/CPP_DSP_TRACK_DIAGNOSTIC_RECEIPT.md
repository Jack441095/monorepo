# Native track diagnostic, 17 Oct 2026

Track diagnostic analysis (`analyze_track_diagnostic` in
[track_diagnostic.py](../../apps/backend/src/kenn/core/track_diagnostic.py))
moved from pure-Python loops, `pyloudnorm`, `librosa` and `scipy` to the C++
extension: `track_diagnostic_features` in
[track_diagnostic_bindings.cpp](../../tooling/native/dsp_core/track_diagnostic_bindings.cpp),
together with `decode_pcm` and `loudness_metrics`. Its callers are
`routes/audio_handler.py` (`handle_track_diagnostic_scan`) and
`routes/daw_routes.py`.

## What it computes

- **Decode:** mono and stereo 16/24/32-bit PCM and 32-bit float WAVs decode
  through `native_fft.decode_pcm` (capped at the first 4,000,000 frames, 83 s
  at 48 kHz, while `duration_seconds` still reports the full file). The Python
  `_decode_pcm_channels` path stays only for 8-bit WAVs and files with more
  than 2 channels, which `decode_pcm` refuses.
- **Peak and RMS:** peak across all channels and the mean of per-channel RMS,
  matching `analyze_wav`.
- **Analysis signal:** the mono mean across channels, or the side signal
  `(L - R) / 2` when a stereo pair cancels in the sum (`mono_peak < peak * 0.001`,
  60 dB down).
- **Waveform envelope:** `WAVEFORM_POINTS` (300) peak and RMS chunks over the
  analysis signal.
- **Spectrogram:** 64 time slices across 31 log-spaced frequencies from 20 Hz
  to 20 kHz (`SPECTROGRAM_FREQUENCIES_HZ`), evaluated by Goertzel over at most
  the first 2048 samples of each slice with a symmetric Hann window. Slices
  shorter than 64 samples or bands at or above Nyquist return `NaN` from C++
  and map to the `-80.0` dB floor in Python.
- **Loudness:** ITU-R BS.1770 integrated LUFS via `native_fft.loudness_metrics`
  on the per-channel audio (replacing `pyloudnorm`). Stems gated below
  `-70 LUFS` or shorter than a gating block return `None`.
- **Spectral centroid and flatness:** 2048-point periodic-Hann STFT at 512-sample
  hops with centred zero-padded frames (`librosa`'s geometry), skipping frames
  more than 60 dB (`1e-6` in power) below the loudest frame. Pure digital
  silence returns `None` for both instead of `0.0 Hz` and `1.0`.
- **Resonance peaks:** Welch PSD (`nperseg = min(4096, max(512, n // 4))`,
  periodic Hann, 50% overlap, constant detrend, one-sided density) followed by
  peak picking (`distance = 8` bins, `prominence = 5.0` dB), filtered to
  `40..14000 Hz` and sorted by level (top 6).

## Parity on 20 corpus stems

We compared the old Python implementation (`git show main:products/kenn/apps/backend/src/kenn/core/track_diagnostic.py`)
against the new C++ path on 20 stems from `Audio-Assets/SLO-Testing/testing_track_stems`
(`al_james`, `ae_mere_humsafar`, `amyhelmandthehandsomestrangers_rescueme`,
`angeloboltini_fragments`, `atlantisbound_itwasmyfaultforwaiting`, and
`dream_of_you`), on one arm64 Mac:

| Quantity | Max difference across 20 stems | Notes |
| --- | --- | --- |
| `peak_dbfs` | `0.0 dB` | Exact match on all 20 stems |
| `rms_dbfs` | `0.0 dB` | Exact match on all 20 stems |
| `lufs_integrated` | `0.0 LU` | Exact match on all 19 voiced stems; both return `None` on silent `06_Claps.wav` |
| `waveform.peaks` (300 pts) | `0.0` | Exact match at 4-decimal rounding |
| `waveform.rms` (300 pts) | `0.0` | Exact match at 4-decimal rounding |
| `spectrogram.matrix` (64x31) | `0.0 dB` | Exact match across all 39,680 cells |
| `resonant_peaks` (freq & dB) | `0.0 Hz`, `0.0 dB` | Same peak count, frequencies and levels on all 20 stems |
| End-to-end time (20 stems) | `34.37 s` → `14.97 s` | `3.75 s` → `0.82 s` on `al_james/29_ElecGtr4.wav` (200.5 s stereo) |

## Silent-frame flatness and centroid fix

`librosa.feature.spectral_flatness` floors each bin's power at `1e-10` before
taking the geometric-to-arithmetic mean ratio, so a silent frame scores `1.0`
(white-noise flat) and `0.0 Hz` centroid. Averaging over all frames dragged
stems with rests toward white noise and 0 Hz. Skipping frames more than 60 dB
below the loudest frame fixes this:

| Stem | Total frames | Silent frames | Old centroid → New | Old flatness → New |
| --- | --- | --- | --- | --- |
| `al_james/29_ElecGtr4.wav` | 7813 | 5152 (65.9%) | `538.8 Hz` → `1558.3 Hz` | `0.65787` → `0.00016` |
| `ae_mere_humsafar/06_RevCymbal.wav` | 7813 | 6240 (79.9%) | `943.1 Hz` → `4571.8 Hz` | `0.79469` → `0.00731` |
| `al_james/04_Snare3.wav` | 7813 | 7687 (98.4%) | `81.2 Hz` → `2470.2 Hz` | `0.97888` → `0.00176` |
| `al_james/06_Claps.wav` (digital silence) | 7813 | 7813 (100%) | `0.0 Hz` → `None` | `1.0` → `None` |
| `amyhelmandthehandsomestrangers_rescueme/Bass-DI.wav` | 7813 | 0 (0%) | `210.6 Hz` → `210.6 Hz` | `0.0` → `0.0` |

Note on `al_james/29_ElecGtr4.wav`: the plan note from 17 Oct quoted 38%
silent frames (`0.376` flatness, `998 Hz` centroid), which was measured on the
full 200.5 s stem (8.84M frames). `analyze_track_diagnostic` caps decoding at
the first 4,000,000 frames (90.7 s at 44.1 kHz, 7813 STFT frames), where the
guitar is tacet for 5152 frames (65.9%), so the old code reported `0.65787`
flatness and `538.8 Hz` centroid and the new kernel reports `0.00016` flatness
and `1558.3 Hz` centroid.

## Portable scalar build

Built with `-DKENN_USE_ACCELERATE=OFF`: `track_diagnostic_bindings.cpp` uses
the shared radix-2 `kenn::dsp::fft_in_place` and direct DFT for non-power-of-two
short Welch segments on both builds, so its output is identical between the
Accelerate and scalar builds, and all 13 tests in `test_track_diagnostic.py`
pass on both.

