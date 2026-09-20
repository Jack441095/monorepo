# AutoMix Mono-Compatibility Correction

Type: AutoMix decision logic
Tags: automix, mono compatibility, stereo width, phase, fold-down, correlation, mixdown, master bus
Status: Approved
Source: studio/audio_analysis/audio_analysis/mixdown/mix_renderer.py (_mono_compat_severity_by_stem, _MONO_COMPAT_CORRECTION_FACTOR, stage 7B), mixdown/mix_decision_engine.py (MixPlan.apply_mono_compat_correction)
Reviewed: 2026-07-17

Short answer:
AutoMix's mono-compatibility detector already flags stems at risk of phase cancellation or loudness loss when a mix is folded down to mono (warning/critical severity) — but that detection alone didn't change anything about the render. This stage closes that gap: when a mix plan opts in (`apply_mono_compat_correction`), any flagged stem gets a bounded additional stereo-narrowing pass sized by its severity, on top of whatever stereo width the decision engine already chose for it.

Try this — how the correction is sized and applied:
1. Only stems the mono-compatibility detector already flagged `warning` or `critical` are touched — an unflagged stem's stereo width is left exactly as the decision engine set it.
2. The narrowing factor is fixed per severity: `warning` gets a 0.6 correction factor, `critical` gets 0.35 — floored well above 0.0 so a flagged stem is narrowed, never collapsed to fully mono. Full mono collapse would erase the element's character (e.g. a hi-hat's natural "air") rather than just taming the fold-down/phase risk that's actually the problem.
3. This is applied as a *second* `apply_stereo_width` pass, after the decision engine's own width pass (stage 7). That composes safely rather than fighting the earlier pass: mid (`0.5*(L+R)`) is invariant under width scaling, so two sequential width passes with factors w1 then w2 produce the same result as one pass at w1*w2 — the correction genuinely multiplies the existing width, it doesn't reset or override it.
4. Runs stem-by-stem, before stems sum into the master bus, so the correction is local to the specific problem element rather than a blanket master-bus narrowing that would also affect unflagged stems.

Why it matters:
This mechanism was ear-confirmed on real material, not just measured. A hi-hat/cymbal element in a real mix (internally referred to as `DRUM_BREAK`) was flagged critical, measured at a raw stereo correlation of ~0.076 (source-material decorrelation — a naturally very wide element, not a rendering bug). Applying this correction brought its correlation up to ~0.74. Separately, Jack's own blind listening on a full render flagged this exact same element's phasing as audible before the fix and confirmed less phasing after it (`stranger_v5_vs_v6` A/B) — the detector's flag and the correction's effect both lined up with what was actually heard, not just what a correlation number predicted.

Common mistakes:
- Assuming this fully mono-sums a flagged stem — it doesn't; even `critical` severity only narrows to a 0.35 width factor, well short of mono, specifically to preserve the element's stereo character.
- Confusing this with the decision engine's own stereo-width choice (stage 7) — this is a second, additive pass gated entirely on the mono-compatibility detector's flag, not part of the initial per-instrument width decision.
- Assuming a wide, naturally-decorrelated element (like a drum-break fill) is a mixing mistake that needs "fixing" outright — the detector flags mono-*compatibility* risk (what happens on a mono system/venue), not that the width itself is wrong; a legitimately wide creative choice can still get flagged and correctly narrowed for playback-system safety without being a mixing error.

When this does not apply:
- Off by default (`apply_mono_compat_correction=False` on `MixPlan`) — listening-gated diagnostic functionality, not yet a production default, despite the strong verified/ear-confirmed evidence above. Promotion still needs the same §10.2/§10.10 Phase F gate as every other AutoMix correction (≥20 rated projects, ≥2 raters, Wilson lower bound above chance) before flipping to a default.
- Does nothing on a stem the mono-compatibility detector didn't flag — a mix with no real fold-down risk anywhere is untouched.

Related questions:
- Why is one of my stems narrower in the final render than what the mix plan initially chose for its stereo width?
- What does a "mono compatibility: critical" flag mean and does AutoMix actually do anything about it?
- Why did AutoMix narrow my drum/cymbal element specifically?
