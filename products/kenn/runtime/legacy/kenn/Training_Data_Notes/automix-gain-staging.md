# AutoMix Gain Staging

Type: AutoMix engine behavior
Tags: automix, gain staging, anchor, mixdown, mix decision engine, level, rms, peak, kick, vocal
Status: Approved
Source: studio/audio_analysis/audio_analysis/mixdown/mix_decision_engine.py (generate_mix_plan), studio/audio_analysis/audio_analysis/mixdown/mix_rules.py (INSTRUMENT_RULES)
Reviewed: 2026-07-09

Short answer:
AutoMix's decision engine (`generate_mix_plan` in `mix_decision_engine.py`) always picks one "anchor" stem first, sets its gain to hit a target peak level, then sets every other stem's gain relative to that anchor — either relative peak (for transient instruments) or relative RMS (for continuous instruments).

Try this:
1. AutoMix looks for a stem whose instrument rule has `gain_anchor: True` in `INSTRUMENT_RULES` (currently only `kick`). If found, that stem is the anchor.
2. If no instrument rule declares an anchor, AutoMix falls back to the loudest stem by peak dBFS (`max(valid_stems, key=lambda p: p.peak_dbfs)`), as long as its peak is above -60 dBFS.
3. The anchor's gain is set so its peak lands at `target_peak_dbfs` from its rule — for `kick` that default is -6.0 dBFS (pop genre overrides it to -5.5 dBFS, hip-hop to -4.0 dBFS, edm to -3.5 dBFS).
4. Transient instruments (kick, snare, hihat, percussion, full_drum_bus) are then gained so their peak sits `target_level_relative_to_anchor` dB from the anchor's target peak. E.g. snare defaults to -1.5 dB relative to the kick.
5. Continuous instruments (vocal, bass, guitar, keys, pads, etc.) are gained so their RMS sits `target_level_relative_to_anchor` dB from the anchor's post-gain RMS. E.g. vocal defaults to +0.5 dB relative-to-anchor RMS (so it sits slightly on top of the kick), pop genre bumps that to +1.5 dB.
6. If Stage 8.3 feedback-learned corrections are active (a `connect_func` is supplied and prior accepted/rejected mixes exist for that genre), a capped +/-2 dB crest-factor correction is added on top of the rule-based gain.

Why it matters:
Anchoring every stem's gain to one reference (instead of independent per-stem targets) keeps the whole mix's relative balance stable even when input stems arrive at wildly different recording levels — the anchor absorbs the "what's the reference loudness" decision once, and everything else is a relative offset from real, measured code constants, not a guess.

Common mistakes:
- Assuming AutoMix targets a fixed absolute dBFS per instrument regardless of genre — it does not; `target_peak_dbfs` and `target_level_relative_to_anchor` are both overridden per genre in `GENRE_MODIFIERS`.
- Assuming gain is always peak-based — continuous instruments are gained by RMS, not peak, to avoid punishing sustained instruments for a single transient.

When this does not apply:
- If no stems are supplied at all, AutoMix falls back to an arbitrary -18.0 dBFS reference RMS and logs "No stems available to anchor gain staging."

Related questions:
- Why is the kick drum the gain anchor in my AutoMix session?
- How does AutoMix decide the vocal level relative to the kick?
- What happens to gain staging if no drum stem is present?
- Does AutoMix apply gain staging by peak or RMS?
