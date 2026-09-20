# KENN Audio Analysis Schema

Schema identifier: `kenn.audio_analysis.result.v1`

Implementation: `apps/backend/src/kenn/core/audio_analysis.py`

Version: `kenn.audio_analysis.v1`

Each result contains `input_hash`, `filename`, `analysis_timestamp`, `receipt_id`, `ok`, `analysis_status`, `metrics`, `spectral`, `findings`, `confidence`, `severity`, `evidence`, `explanation`, `limitations`, and `suggested_ableton_workflow`.

`metrics` includes duration, sample rate, bit depth, channels, layout, sample peak dBFS, RMS dBFS, crest factor dB, clipping sample/run counts, silence percentage, DC offset, and—when stereo—L/R RMS, correlation, stereo width ratio/dB, mono-sum RMS, and mono cancellation drop.

`spectral` includes FFT size, Hann window, windows averaged, bin width, dominant peaks (`frequency_hz`, `level_dbfs`, `bandwidth_hz`, `confidence`, `fft_bin`), bounded `time_localized_windows`, and low/low-mid/mid/upper-mid/high band energy. Each localized window records source `start_seconds`, `end_seconds`, window `rms_dbfs`, and its own dominant peaks. The windows are a bounded audit aid, not a continuous STFT or source separation. It can be `{status: "abstained", reason: ...}`.

All levels are sample/FFT-derived dBFS values. There is no `integrated_lufs`, `lra`, or `true_peak_dbfs` field because those algorithms are not implemented and calibrated here. A spectral finding is a hypothesis with a required listening test.
