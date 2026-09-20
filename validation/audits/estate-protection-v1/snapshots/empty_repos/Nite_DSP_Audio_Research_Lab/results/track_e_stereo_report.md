# Track E - Stereo/Phase Intelligence STEREO_BENCH_1.0

Cases: 320 (healthy fraction 62%)

| Detector | Recall | Healthy FP rate |
|---|---|---|
| Naive broadband corr<0.2 | 0.667 | 0.2 |
| Band-aware side/sub detector | 1.0 | 0.015 |

## Healthy-case false positives by construction kind

| Case | Naive FP | Band-aware FP |
|---|---|---|
| haas_widened_guitar | 0.0 | 0.0 |
| wide_reverb_return | 1.0 | 0.075 |
| detuned_wide_pad | 0.0 | 0.0 |
| narrow_kick_bass_mono | 0.0 | 0.0 |
| slight_balance_offset | 0.0 | 0.0 |

## Problem-case recall by kind

- antiphase_lowband: naive=1.0 bandaware=1.0
- bass_only_right_55hz: naive=0.0 bandaware=1.0
- side_heavy_bass: naive=1.0 bandaware=1.0