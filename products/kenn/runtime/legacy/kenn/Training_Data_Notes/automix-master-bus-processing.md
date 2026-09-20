# AutoMix Master Bus Processing (Glue Compression, Multiband, Limiter)

Type: AutoMix decision logic
Tags: automix, master bus, glue compressor, multiband compression, true peak, limiter, dither, saturation
Status: Approved
Source: studio/audio_analysis/audio_analysis/mixdown/mix_decision_engine.py, mix_renderer.py, dsp_engine/dither.py (Audio Too codebase)
Reviewed: 2026-07-09

Short answer:
After every stem is summed, AutoMix's master bus chain runs (in order): an internal 3-band multiband compressor with fixed per-band settings, an optional genre-driven "glue" compressor, tape-style saturation, a true-peak stereo limiter whose ceiling comes from the mix goal's target profile, and finally noise-shaped triangular dither at the output bit depth.

Try this — the fixed multiband compressor bands (`_apply_multiband_compressor` in `mix_renderer.py`, not genre-adjustable):
1. Low band (below 200 Hz, 4th-order Butterworth crossover): ratio 2.5:1, attack 50ms, release 200ms, threshold -18 dBFS.
2. Mid band (200 Hz–5000 Hz): ratio 1.8:1, attack 30ms, release 150ms, threshold -15 dBFS.
3. High band (above 5000 Hz): ratio 1.5:1, attack 20ms, release 100ms, threshold -12 dBFS.

The genre-driven "glue" compressor (`BusMixConfig.bus_compressor`, set in `generate_mix_plan()`) is separate from the multiband stage and uses a fixed attack (30ms) and release (150ms) with threshold -12 dBFS, but its ratio comes from `GENRE_MODIFIERS[genre]["master_bus"]["compression_ratio"]`: pop 2.5:1, rock 1.5:1, hip-hop 2.0:1, EDM 3.0:1, acoustic 1.2:1, jazz 1.0:1 (effectively no gain reduction, preserving natural dynamics), cinematic 1.3:1, podcast 3.0:1.

Master bus saturation drive also comes from the genre's `master_bus.saturation_db`: pop 0.5 dB, rock 0.8 dB, hip-hop 1.5 dB, EDM 2.0 dB (the most aggressive), acoustic and jazz 0.0 dB (no saturation, for a clean/transparent master), cinematic 0.2 dB, podcast 0.0 dB. When saturation is enabled the mix is always applied at a fixed 40% wet/dry blend.

The limiter ceiling is not simply the genre's raw `limit_ceiling_db` — `_target_ceiling_for_goal()` looks at the mix goal's canonical target profile (from `analysis_core.target_config.GOAL_TARGETS`) and takes the *strictest* (lowest) peak/true-peak ceiling declared there, falling back to the genre value only if the goal has none. The limiter itself (`_apply_stereo_limiter`) runs in true-peak mode (`true_peak=True`) and is stereo-linked — both channels share the same detected gain-reduction envelope so the stereo image isn't skewed by limiting.

Immediately before final bit-depth conversion, `apply_noise_shaped_dither()` (in `dsp_engine/dither.py`) applies triangular, noise-shaped dither at the requested output bit depth — this happens after limiting, as the very last step in the chain.

Why it matters:
The multiband stage tames frequency-specific dynamics issues (e.g. a boomy low end or harsh high end) before the glue compressor adds genre-appropriate overall cohesion, saturation adds genre-appropriate harmonic density/warmth, and the true-peak limiter enforces the loudness/ceiling target from the mix goal rather than a fixed number — so a "premaster" goal and a "club" goal will land on different ceilings even within the same genre.

Common mistakes:
- Assuming the master bus compression ratio quoted in the decision log is the multiband compressor's ratio — the multiband bands are fixed and not logged with the same "Glue compressor on master bus" wording; the logged ratio is specifically the genre-driven glue compressor.
- Assuming saturation is always on — acoustic and jazz genre defaults set `saturation_db: 0.0`, so no saturation line appears in the decision log for those genres.

When this does not apply:
- If `bus_comp_ratio <= 1.0` for a genre, no glue compressor block is added to the MixPlan at all (only ratios strictly greater than 1.0 produce a `bus_compressor` entry).

Related questions:
- Why is the EDM master bus saturation higher than pop's?
- What's the difference between the multiband compressor and the glue compressor on AutoMix's master bus?
- Why does the limiter ceiling differ between mix goals in the same genre?
