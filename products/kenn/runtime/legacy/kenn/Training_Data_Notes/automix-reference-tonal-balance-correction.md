# AutoMix Reference-Track Tonal Balance Correction

Type: AutoMix engine behavior
Tags: automix, reference track, tonal balance, low shelf, bass, low mids, EQ, spectral comparison, blind listening
Status: Approved
Source: scripts/eval/reference_track_comparison.py (tonal balance scoring), studio/audio_analysis/audio_analysis/mixdown/mix_renderer.py (master bus EQ application), scripts/automix_local.py (run_local_automix's extra_bus_eq_bands/apply_mono_compat_correction parameters)
Reviewed: 2026-07-17

Short answer:
AutoMix's default output measures systematically thin in bass and low-mids compared to commercial reference masters — confirmed across three different test songs, not a one-off. A single low-shelf boost (300 Hz corner, +4.0 dB, nothing else touched) closes most of that gap and was the only correction this session that a human listener confirmed sounded better in blind A/B testing, across two rounds of refinement.

Try this:
1. Render the mix normally, then compare it against a level-matched commercial reference in the same genre using `scripts/eval/reference_track_comparison.py <mix.wav> <reference.wav>`. It reports a 0-100 tonal-balance score plus per-band (sub/bass/low_mids/mids/presence/sibilance/air) energy-share deltas.
2. Expect the bass band to measure roughly 3.5-4.5 dB low and low_mids roughly 1-2 dB low versus a well-mastered reference — this was true on all three real songs tested (stranger, dream_of_you, reggueton_pop), each against a different baseline severity (scores 31.6, 17.2, and 41.0 out of 100 respectively before correction).
3. Apply a single low-shelf EQ band at 300 Hz, +4.0 dB, Q 0.707 on the master bus — via `run_local_automix(..., extra_bus_eq_bands=[{"type": "lowshelf", "frequency": 300.0, "gain_db": 4.0, "q": 0.707}])`. This is diagnostic-only plumbing (not a production default yet); it reuses the same mechanism as the existing verbal-feedback EQ correction path in `mix_decision_engine.py`.
4. Re-measure with the same comparison tool — expect the tonal-balance score to improve by roughly 15-20 points and the low_mids band to land within about 0.1 of the reference's share.
5. Do not chase the score past this point by cutting mids/presence/air to close the remaining gap — a 7-band correction that did exactly that (cutting all four upper bands to match the reference more closely) scored better numerically (55.2 vs 49.5) but was rejected in blind listening; the listener preferred the uncorrected mix even though it still measured further from the reference. A single-shelf boost, engaging only when there's genuine headroom to add, has been the only pattern that has actually won a blind comparison so far.

Why it matters:
A high tonal-balance score is not the same thing as a mix that sounds better — this was proven directly this session, not assumed. The one correction that has passed a real blind listen boosts a deficient region and touches nothing else; every correction that tried to close the remaining gap by cutting an already-present region has either been rejected outright or measured a regression on the very target it was meant to improve (a targeted body-boost at 900 Hz, aimed at filling a perceived mid-range gap, actually made the tonal-balance score worse because that frequency falls inside a band that was already overrepresented, not underrepresented).

Common mistakes:
- Treating the tonal-balance score as a promotion gate on its own — it is a calibration signal for scripts/listening_benchmark_*.py's blind A/B infrastructure to test, not a substitute for it. See docs/PROJECT_ACTION_PLAN_2026-07-14.md §10.2/§10.10 for the actual promotion gate (>=20 rated projects, >=2 raters, Wilson 95% lower bound above chance).
- Assuming a spectral gap that shows up as "excess" in one region is actually excess there — a mix that reads 5 dB hot at 2-2.5 kHz relative to a reference, when both are normalized to their own 1 kHz level, can be caused by the reference simply having a bigger 1 kHz peak that rolls off steeply after, not by the mix having too much energy at 2-2.5 kHz in absolute terms. Check absolute per-band levels before assuming which direction to correct in, not just the normalized shape comparison.
- Widening a mix's low end to match a reference's wider low-end side-channel content — a mix with a mono/narrow low end in the side channel (correct mono-compatibility practice) should not be widened just because a reference master happens to be wider down there; that is a mastering-style choice, not a correctness gap.

When this does not apply:
- This correction is still diagnostic, not a production default (`apply_mono_compat_correction` and the `extra_bus_eq_bands` mechanism both default off). It has passed a directional blind listen on one song (`stranger`, across two refinement rounds) and is pending listening validation on the two generalization test songs (`dream_of_you`, `reggueton_pop`) before it should be treated as ready for a genre-agnostic default.
- Only tested against one reference track (Stromae/Pomme, "Ma Meilleure Ennemie") so far — the magnitude of the correction (+4.0 dB at 300 Hz) may need to vary by genre or reference set; it has not been validated against a second reference track yet.

Related questions:
- Why does my AutoMix render sound thin or lacking in bass compared to a commercial reference?
- Is AutoMix's default bass level too low?
- Should I cut the highs or boost the lows to match a reference track's tonal balance?
- Why did a numerically-better EQ correction sound worse in a blind listening test?
