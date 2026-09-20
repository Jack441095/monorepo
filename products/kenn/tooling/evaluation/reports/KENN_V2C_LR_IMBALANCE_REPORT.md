# Mix-Wide L/R Imbalance

The detector measures whole-file RMS delta, 100 ms window deltas, median
delta, P95 absolute delta, and direction consistency. Its score requires both
level difference and persistence; alternating panning is a context-required
case rather than a pan-correction instruction.

The audio-derived holdout reports 20/20 persistent mix-wide cases and no
recommendations on alternating-pan controls. The limitation remains important:
a stereo render cannot prove whether an asymmetric arrangement is intentional.
Source/stem context is a V2-D requirement for stronger real-world claims.
