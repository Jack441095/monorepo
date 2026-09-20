# AutoMix Dynamic EQ (Automatic Resonance Detection and Cutting)

Type: AutoMix decision logic
Tags: automix, dynamic eq, resonance, harshness, spectral, erb, masking, mastering, master bus
Status: Approved
Source: studio/audio_analysis/audio_analysis/analysis_core/resonance_detection.py, dsp_engine/dynamic_eq.py, mixdown/mix_renderer.py (Audio Too codebase)
Reviewed: 2026-07-09

Short answer:
AutoMix runs an automatic dynamic EQ pass on the master bus, late in the render chain (after stereo width, before final gain/limiting). It detects narrow frequency bands that stick out above their own local neighborhood *and* persist across most of the track — not a single transient peak — then applies a surgical, level-triggered cut only at those bands, only while they're actually loud.

Try this — how detection works (`detect_resonant_bands()`):
1. The master bus signal is split into 40 ERB (psychoacoustic) frequency bands across 16 analysis frames.
2. For each band in each frame, its energy is compared to the mean energy of its immediate neighbors (default: the 4 bands on either side) — this "local neighborhood prominence" is what distinguishes a genuine narrow resonance from a broad, natural spectral tilt.
3. A band is flagged in a given frame if it exceeds its neighborhood by at least 6 dB (`prominence_threshold_db`).
4. A band only becomes a real candidate for cutting if it's flagged in at least 40% of analyzed frames (`persistence_threshold`) — this is what filters out one-off transients (a single kick hit, a cymbal crash) that shouldn't be treated as a mix problem.
5. Bands with negligible energy relative to the frame's total (under 0.2%) are skipped, to avoid noisy comparisons between two near-silent bands.

Try this — how the cut itself works (`apply_dynamic_eq_band()`/`apply_dynamic_eq_bands()`):
1. Each candidate band is isolated with a resonant bandpass filter (`scipy.signal.iirpeak`), Q defaults to 6 (narrow — surgical, not broad).
2. That isolated band is envelope-followed and compared to a threshold (-24 dBFS default); when it's over threshold, gain reduction is computed with a compressor-style curve (ratio scales with how prominent the resonance is: `ratio = min(2.0 + prominence_db / 6.0, 6.0)`, so a mildly-persistent resonance gets gentler treatment than a consistently loud one).
3. Reduction is capped per band (default: the band's own measured prominence, capped at 6 dB maximum) — this prevents an aggressive detection from dulling the mix.
4. Only the reduced portion is subtracted back out of the original signal (a "parallel dynamic EQ" reconstruction: output = original − isolated_band × (1 − gain_reduction)), so everything outside the targeted band passes through unchanged.
5. At most 6 simultaneous bands are processed per render (`max_simultaneous_bands`), so a busy spectrum with many minor resonances doesn't get over-processed everywhere at once — only the most persistent/prominent ones are addressed.
6. When nothing meets the persistence+prominence bar, the stage is a complete no-op — a clean mix is untouched.

Why it matters:
The prominence-plus-persistence gate is what makes this safe to run automatically on every render without a human checking it first: a single loud transient can't trigger a cut (persistence requires it to reappear in ~40% of frames), and a broad, natural spectral tilt can't trigger one either (prominence requires standing out from its own immediate neighbors, not just being loud in absolute terms). Only genuinely narrow, recurring resonances — the kind that read as harshness or boxiness on repeated listens — get touched, and only for as long as they're actually audible, which keeps the correction inaudible as a static EQ move would not be.

Common mistakes:
- Confusing this with a static EQ cut: nothing here is a fixed, always-on notch — every cut is level-triggered and only engages while the resonance is actually present.
- Confusing prominence with loudness: a band that's simply the loudest part of the mix (e.g. a bassline's fundamental) won't trigger this unless it's narrow and sticks out above its *immediate neighbors specifically* — broad energy isn't the same as a resonant peak.

When this does not apply:
- A mix with no narrow, persistent resonances (clean sources, well-balanced arrangement) gets no cuts at all — this stage is a complete no-op in that case, not a forced minimum-intervention pass.

Related questions:
- How does AutoMix decide which frequency a resonance is at?
- Why didn't AutoMix cut an obviously harsh frequency in my mix?
- What's the difference between AutoMix's dynamic EQ and a static EQ cut?
- How many resonant bands can AutoMix correct at once?
