# AutoMix Compression Ratios Per Instrument

Type: AutoMix decision logic
Tags: automix, compression, ratio, threshold, attack, release, dynamics, mix rules, kick, snare, vocal, bass
Status: Approved
Source: studio/audio_analysis/audio_analysis/mixdown/mix_rules.py, mix_decision_engine.py (Audio Too codebase)
Reviewed: 2026-07-09

Short answer:
AutoMix's `INSTRUMENT_RULES` table in `mix_rules.py` gives every instrument category a default compressor ratio/attack/release/threshold, which `generate_mix_plan()` then adjusts per-stem based on the stem's *measured* crest factor before committing it to the MixPlan.

Try this — the default ratios by instrument (before genre modifiers):
1. Kick: 4:1, attack 20ms, release 150ms, threshold -16 dBFS.
2. Snare: 3.5:1, attack 15ms, release 120ms, threshold -12 dBFS.
3. Sub bass: 4:1, attack 10ms, release 200ms, threshold -18 dBFS.
4. Bass: 4:1, attack 15ms, release 180ms, threshold -15 dBFS.
5. Vocal: 3.5:1, attack 10ms, release 80ms, threshold -16 dBFS.
6. Backing vocal: 4:1, attack 8ms, release 100ms, threshold -18 dBFS.
7. Percussion: 2.5:1, attack 10ms, release 80ms, threshold -15 dBFS.
8. Synth lead: 3:1, attack 12ms, release 120ms, threshold -14 dBFS.
9. Guitar: 2.5:1, attack 20ms, release 150ms, threshold -12 dBFS.
10. Keys: 2:1, attack 25ms, release 180ms, threshold -10 dBFS.
11. Full drum bus: 2.5:1, attack 30ms, release 100ms, threshold -14 dBFS.
12. Hihat, synth pad, strings, fx, ambient, other: compression is `None` by default (left uncompressed) unless a genre modifier turns it on.

Genre modifiers change these defaults, e.g.: hip-hop kick becomes 5.0:1 (attack 25ms); hip-hop sub bass becomes 4.5:1 at threshold -20 dBFS; hip-hop vocal becomes 4.0:1 at threshold -18 dBFS; rock snare becomes 4.0:1 (attack 12ms); acoustic vocal becomes 2.0:1 at threshold -10 dBFS; jazz vocal becomes 1.5:1 at threshold -6 dBFS; podcast vocal (mono voice) becomes 4.0:1 at threshold -22 dBFS, attack 5ms, release 60ms.

After the genre-adjusted rule is looked up, `generate_mix_plan()` further adjusts the *threshold* (not the ratio) based on the stem's actual measured crest factor: if crest factor < 10.0 dB (signal already pre-compressed), the threshold is raised by +6.0 dB relative to the rule; if crest factor > 18.0 dB (highly dynamic signal), the threshold is lowered by -3.0 dB to catch transients sooner. The ratio itself is not modulated by crest factor — only threshold is.

Why it matters:
The ratio table encodes how aggressively each instrument role is meant to be controlled (kick/bass/vocal get firmer 3.5–4:1+ control for consistency; keys/guitar get gentler 2–2.5:1 to preserve dynamics), while the crest-factor-based threshold adjustment prevents AutoMix from over-squashing a stem that arrives already compressed, or under-catching a stem with unusually wide dynamic range.

Common mistakes:
- Assuming the compression ratio shown for a stem is genre-independent — always check the genre modifier table, since e.g. kick ratio jumps from 4:1 (pop default) to 5:1 (hip-hop) to 6:1 (EDM).
- Confusing the crest-factor adjustment (which only changes threshold_db) with a ratio change — AutoMix never dynamically changes ratio, attack, or release from the measured signal, only threshold.

When this does not apply:
- Instruments whose rule sets `compression: None` (hihat, synth_pad, strings, fx, ambient, other by default) get no compressor block in the MixPlan at all — there is no ratio to explain because none was applied.

Related questions:
- Why does the kick compression ratio change between hip-hop and pop?
- How does AutoMix adjust compressor threshold based on crest factor?
- Which instruments does AutoMix leave uncompressed by default?
