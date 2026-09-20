# Real-song Mix Review Check — 2026-09-10

## Input

- Source: `/Volumes/Jack_Gandy_1TB_SSD/testing-for-NITE-DSP/testing_track_stems/_automix_out/ae_mere_humsafar/ae_mere_humsafar/mixdown_v1.wav`
- Filename presented to the analyzer: `ae_mere_humsafar_mixdown_v1.wav`
- Format: stereo 24-bit PCM WAV, 44.1 kHz, 263.897 seconds
- Source SHA-256: `1aff8ca03a9c6aa535ed217db42ea8955bccbf04975306cd3f42c23ae09e8c5c`
- Engine: KENN-owned `mix-review/core/local_engine.py`
- Analysis location: isolated remote `/mnt/data` test directory; audio was not added to this repository

## Measured result

The reviewer completed successfully and reported **no qualified issues found**:

- Sample peak: **−1.80 dBFS**; no sustained near-full-scale clipping runs
- Whole-file RMS proxy: **−16.88 dBFS**; this is not calibrated LUFS
- Left/right RMS difference: **2.14 dB**, below the 3 dB imbalance threshold
- Stereo correlation: **0.501**; mono-sum drop **2.23 dB**, with no strong cancellation signal
- DC offset: approximately **−0.0123 / −0.0119**, below the detection threshold
- Content was present through the file; no effective-silence/truncation finding

## Useful hypotheses for a human listening pass

These are deliberately not presented as confirmed mix faults:

- A narrow spectral peak was measured around **293.86 Hz**. Sweep a narrow EQ band around that region in the densest section, bypass at matched level, and keep it only if the resonance is audible.
- A possible spectral overlap was measured around **439.66–462.82 Hz**. Mute/solo the likely sources and compare in mono before making any masking decision.

The analyzer did not evaluate source-separated masking, tonal balance, arrangement/dynamics, genre context, calibrated LUFS, or true peak for this run. It abstained on those areas rather than inventing track-level advice or a pink-noise-relative dB claim.

## Next product step

The report is useful as a measured preflight, but the next Mix Reviewer increment should add time-localised, source-aware evidence and a proper reference comparison so Kenn can turn these hypotheses into better Ableton-specific suggestions without overclaiming.
