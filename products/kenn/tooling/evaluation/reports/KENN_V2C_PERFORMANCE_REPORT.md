# Performance

End-to-end WAV round-trip, measurement, candidate extraction, and V2-C gate
on the 0.8-second audio holdout measured p50 **23.2 ms** and p95 **66.8 ms**
per case in the observed run. Gate computation itself is negligible compared
with PCM operations. Measurements remain finite for the generated mono/stereo
paths; no NaN/Inf leaked into a candidate.
