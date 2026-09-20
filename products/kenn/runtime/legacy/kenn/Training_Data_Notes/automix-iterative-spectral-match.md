# AutoMix Iterative Reference Spectral Matching (Multi-Band Cascade)

Type: AutoMix engine behavior
Tags: automix, reference track, spectral matching, tonal balance, iterative EQ, genre reference, master bus EQ, parametric EQ, cascade
Status: Approved
Source: studio/audio_analysis/audio_analysis/mixdown/spectral_match.py (compute_reference_match_bands, reference_target_40band), business/app/automix_worker.py (worker/UI wiring), scripts/eval/match_track.py and scripts/automix_local.py --match-reference (CLI wiring), docs/audits/2026-07-23-render-speed-and-bass-findings.md
Reviewed: 2026-07-29

Short answer:
This is the engine actually running today when a mix is matched to a reference — it supersedes the earlier single-band diagnostic correction described in "AutoMix Reference-Track Tonal Balance Correction". It measures the rendered mix and a reference (a single track, or the median of a genre folder of several) on the same perceptually-correct log-spaced 40-band spectrum, then iteratively builds a cascade of narrow parametric bells (10 bands by default, Q 1.4) on the master bus until the tonal-balance score stops improving. It is boost-biased (cuts are scaled to half strength and clamped tighter than boosts) so low-end corrections carry the match while treble cuts stay gentle — the same "boost, don't cut" lesson the single-band note already established, generalized to many bands instead of one.

Try this:
1. Curate or point at a genre reference: either one file, or a directory of same-genre, fully-mastered tracks (`reference_tracks/<genre>/`, e.g. `pop`, `hiphop_rnb`, `electronic`, `acoustic`, `cinematic`) — a directory computes a robust median target across every file in it, which rejects outlier tracks (references disagree most in sub/low_mids; averaging naively would blur the target).
2. Run it end-to-end with `python scripts/eval/match_track.py <stems_dir> --reference reference_tracks/<genre> --genre <genre> --output out/<track>` — this renders a baseline, renders a matched version (`run_local_automix(..., reference_track=ref, match_reference=True)`), and writes a before/after/target evidence report (`match_report.html`) with the score movement, per-band table, safety figures, and (as of 2026-07-29) grounded KENN explanations for each applied band and for the reference's own measured profile.
3. In the web worker/UI path (`business/app/automix_worker.py`), the same mechanism runs as a two-pass probe: render once, `compute_reference_match_bands(probe_wav, ref_path)` measures the gap and returns the band cascade, those bands are appended to `plan.bus.bus_eq_bands`, then the mix re-renders with them applied.
4. Each applied band carries its own reason string, e.g. `"Ref match 300Hz +4.0 dB (iterative 10-band spectral match)."` — this is what grounds KENN's per-band explanation in the evidence report and in `mixdown/mix_delivery.py`'s delivered report (Stage 9.6, `annotate_bus_eq_bands_with_kenn`).
5. Iteration is bounded (`max_iterations=4`) with an adaptive stop: it keeps the best-scoring cascade seen, not the last one, and stops early after 2 iterations without a score improvement > 0.1 — a fixed iteration count over-corrects past the peak.

Why it matters:
Validated on real multitrack renders by maximizing the same tonal-balance score the single-band note uses (0-100, log-band comparison against the reference) — stranger vs Stromae/pop went 30 -> 76 in the original validation (2026-07-23) and 53.7 -> 82.3 in a later real end-to-end run against a 5-track pop genre folder, both clip-safe with LUFS on target. Denser banding (10 narrow bells) reaches a higher score than the older coarse 7-band approach ceilinged around, because it can place a boost precisely where the gap is instead of averaging it across a wide band. The cascade structure (accumulate bands across iterations, don't collapse to per-band sums) matters mechanically: collapsing adjacent narrow bells to their summed gain lets them compound at the clamp and score worse, even though the math looks equivalent on paper.

Common mistakes:
- Confusing this with the older single low-shelf correction (300 Hz, +4.0 dB) — that was a diagnostic, still-off-by-default mechanism validated by ear on one song. This multi-band cascade is the one actually wired into the live worker/UI and CLI `--match-reference` path today; if a mix plan's bus EQ bands carry a reason mentioning "iterative N-band spectral match", this note describes the mechanism that produced them, not the single-shelf one.
- Mixing genres in one reference folder — measured CoV (coefficient of variation) across an inconsistent folder was 0.71-0.72 on sub/low_mids alone; a folder that mixes styles produces a median target that resembles neither. `reference_tracks/README.md` documents the curation rule: one consistent style, 5-8 tracks, full commercially-mastered mixes only (not vocal-only or instrument-only stems).
- Expecting this to fix dynamics/density — this mechanism is EQ-only. A separate, distinct function (`compute_reference_dynamics_comp`) exists for crest-factor/density matching via bus-compressor settings, and measured density gains are structurally capped by the render's final LUFS normalization (see the deeper mechanism note in the single-band correction's history) — don't expect a spectral match alone to make a mix "denser."

When this does not apply:
- Score gains past roughly 76-80 diminish sharply and were found not worth chasing with more bands (16 bands needed 45 bells to reach 76.3 vs 10 bands' 10-17 bells reaching ~75) — past that point further tuning fits the metric, not the music.
- The genre reference libraries are only as good as their curation; an uncurated or single-track "genre" target should be treated as provisional, not a stable production target.
- Stereo width is handled by a companion, deliberately gentler mechanism (`compute_reference_width_factor`) — a 35%-weighted nudge toward the reference's own width, capped at +-15%, not a hard match — because aggressive M/S width correction risks phase/mono-compatibility problems. Don't expect this note's mechanism to also correct stereo width; it doesn't touch it.

Related questions:
- Why does AutoMix have a peaking master bus EQ band at [frequency] Hz with a reason mentioning "iterative N-band spectral match"?
- How does AutoMix's reference matching pick which frequencies to boost or cut?
- What is the difference between AutoMix's single low-shelf reference correction and its multi-band spectral match?
- Why does a genre reference folder need multiple tracks of the same style?
- Does reference spectral matching also fix a mix's density or dynamics?
