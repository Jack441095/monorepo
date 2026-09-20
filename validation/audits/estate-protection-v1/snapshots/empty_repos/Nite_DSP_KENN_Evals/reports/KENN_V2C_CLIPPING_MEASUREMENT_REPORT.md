# Clipping Measurement

`clipping_candidate()` measures maximum sample peak, near-full-scale samples,
plateau events, event density, and affected channels after WAV round-trip.
It classifies no clipping, near full scale, likely sample clipping, and likely
hard clipping. A plateau requires at least two consecutive near-full-scale
samples, avoiding a single transient sample as the sole condition.

Audio-derived holdout: 20/20 clipping candidates detected, 0 false positive
recommendations, and 0 saturation/limiter confusion in the supplied controls.
This does not claim analogue/soft-distortion classification or true-peak
coverage; those remain explicit limitations.
