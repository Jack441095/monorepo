# KENN V2 Baseline Audit

Current KENN has two distinct boundaries. Ableton session analysis is explicitly
structural: it has track names, mixer state, devices and transport, while it
declares spectrum, loudness, width and phase unavailable. Mix Review is the
render-analysis path and exposes peak/true-peak, RMS, LUFS, crest, spectral
bands, stereo correlation/width/balance, DC, silence, dynamics, resonances and
section data.

The product does not establish a reliable current capability for frequency
masking causes, subjective tonal correctness, clip/source causality, or safe
automatic correction. Its evidence layer correctly distinguishes supplied
measurements from inferences, but the report-level flagger currently defeats
that caution through uncalibrated recommendation triggers.

Automix was inspected read-only. Its analysis primitives may be reused only
after the above qualification; recommendation-to-parameter-write remains a
separate safety domain.
