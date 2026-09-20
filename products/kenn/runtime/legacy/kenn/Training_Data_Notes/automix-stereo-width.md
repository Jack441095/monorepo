# AutoMix Stereo Width and Panning Choices

Type: AutoMix decision logic
Tags: automix, stereo width, panning, mono, mid-side, mix rules, imaging
Status: Approved
Source: studio/audio_analysis/audio_analysis/mixdown/mix_rules.py, mix_decision_engine.py (Audio Too codebase)
Reviewed: 2026-07-09

Short answer:
Each instrument rule declares a fixed `stereo_width` multiplier (0.0 = fully collapsed to mono, 1.0 = the stem's native width unchanged, values above 1.0 = artificially widened) and a `pan` value (-1.0 hard left to +1.0 hard right) plus a `mono_below_hz` cutoff (default 120.0 Hz) below which the stem is forced mono regardless of the width setting.

Try this — default stereo width by instrument:
1. Kick, sub bass, bass: 0.0 (strict mono) — low-frequency, phase-critical elements are always collapsed to mono in AutoMix's default rules.
2. Snare: 0.2 (mostly mono, slight width).
3. Hihat: 0.4, panned -0.25 (slightly left).
4. Percussion: 0.6, panned +0.3 (slightly right) — hihat and percussion are panned to opposite sides by default to spread the top-end of the kit.
5. Full drum bus: 0.35 (narrower than individual close mics would suggest, since it's already a stereo-miked/summed source).
6. Vocal: 0.25 (kept fairly narrow/centered since it's the focal point).
7. Backing vocal: 0.8, panned -0.4 (wide and off-center, so it doesn't compete with the centered lead vocal).
8. Guitar: 0.65, panned -0.35 (left); Keys: 0.7, panned +0.35 (right) — guitar and keys are deliberately panned to opposite sides in the default rule set.
9. Synth lead: 0.6, panned +0.15.
10. Synth pad: 1.2 (artificially widened beyond the source's native width) — the widest default of any harmonically-pitched instrument.
11. Strings: 0.9, panned center.
12. FX: 0.8, panned +0.45.
13. Ambient: 1.5 — the single widest default in the entire rule table, reflecting ambient's role as background atmosphere rather than a focal element.

Genre modifiers can override width, e.g. rock widens guitar to 0.95; EDM sets sub_bass width to 0.0 explicitly (reinforcing the mono-bass default) and synth_pad to 1.5; podcast forces vocal `stereo_width: 0.0` and `pan: 0.0` for a strict mono voice.

Why it matters:
Keeping bass-register and phase-critical elements (kick, bass, sub_bass) at width 0.0 avoids low-frequency phase cancellation when the mix is summed to mono (club systems, phones, broadcast) — this is the same "keep bass mono" principle documented in general mixing notes, applied here as a hard rule rather than a suggestion. Widening pads/strings/ambient beyond 1.0 creates a sense of space around the tighter, more mono low end and lead vocal.

Common mistakes:
- Treating `stereo_width` as a percentage of the pan value — it's an independent multiplier on the stem's inherent stereo image, separate from the `pan` position.
- Assuming `mono_below_hz` (default 120.0 Hz) is genre-adjustable in the current rule set — it is a fixed per-stem default in `StemMixConfig` unless a specific rule overrides it; it is not touched by any current `GENRE_MODIFIERS` entry.

When this does not apply:
- Stems whose `abs(stereo_width - 1.0)` is below 1e-4 don't generate a "widened/narrowed" line in the decision log, since AutoMix treats that as "left at the source's natural width" (no explicit imaging decision was made).

Related questions:
- Why does AutoMix always force the bass and kick to mono?
- Why are guitar and keys panned to opposite sides by default?
- How much does the EDM genre modifier widen synth pads?
