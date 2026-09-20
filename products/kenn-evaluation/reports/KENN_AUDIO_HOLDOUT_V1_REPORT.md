# KENN_AUDIO_HOLDOUT_V1

440 deterministic, mix-like synthetic cases were generated across 44.1, 48,
and 96 kHz. Every case runs through 16-bit WAV encode, standard WAV decode,
PCM measurement, candidate construction, and recommendation gate. Split:
264 development / 88 calibration / 88 frozen holdout.

Composition: 120 healthy/acceptable, 80 clipping, 80 headroom-related
(including 20 mastered-like controls), 100 L/R cases (including 20 alternating
arrangement controls), 40 multi-fault, plus DC and resonance regressions.
The manifest records generation settings and ground truth; it does not encode
pre-baked candidate scores.
