# AutoMix Master Bus Compression, Saturation, and Limiter Ceiling

Type: AutoMix decision logic
Tags: automix, master bus, glue compressor, saturation, limiter, ceiling, lufs, true peak, mastering, bus compression
Status: Approved
Source: studio/audio_analysis/audio_analysis/mixdown/mix_decision_engine.py (generate_mix_plan, section 4), mix_rules.py (GENRE_MODIFIERS master_bus), studio/audio_analysis/audio_analysis/analysis_core/target_config.py (GOAL_TARGETS)
Reviewed: 2026-07-09

Short answer:
After every stem is configured, `generate_mix_plan()` builds a separate `BusMixConfig` for the master bus: optional tape-style saturation, an optional "glue" compressor with fixed attack/release/threshold but a genre-controlled ratio, and a brickwall limiter whose ceiling is the *strictest* of the genre's configured ceiling and the mix goal's canonical target (never just one or the other).

Try this:
1. Saturation: if the genre's `master_bus.saturation_db` is > 0, AutoMix sets `saturation_drive_db` to that value and always mixes it in at a fixed 40% wet ("moderate mix for master bus glue"). Defaults: pop 0.5 dB, rock 0.8 dB, hip-hop 1.5 dB, EDM 2.0 dB (the highest default), acoustic/jazz/podcast 0.0 dB (no saturation).
2. Glue compressor: if `master_bus.compression_ratio` > 1.0, AutoMix adds a bus compressor with a fixed attack of 30 ms (slow enough to let transients pass), fixed release of 150 ms, and a fixed threshold of -12 dBFS — only the *ratio* varies by genre. Defaults: jazz 1.0:1 (effectively off, preserving dynamics), acoustic 1.2:1, cinematic 1.3:1, rock 1.5:1, pop 2.5:1, hip-hop 2.0:1, podcast 3.0:1, EDM 3.0:1 (tied with podcast for the highest default ratio).
3. Limiter ceiling: `_target_ceiling_for_goal()` scans the mix goal's `GOAL_TARGETS[...]['checks']` for any `peak_dbfs`/`true_peak_dbfs` check with a `max`, and takes the *minimum* (strictest) of those maxes as the ceiling. Only if the mix goal defines no such checks at all does it fall back to the genre's own `limit_ceiling_db` (default -1.0 dBFS; EDM explicitly sets -0.5 dBFS). In practice this means the canonical mix-goal's true-peak/peak checks are the primary source of truth for the ceiling, and the genre value is a fallback rather than a competing floor.
4. The limiter's threshold starts at 0.0 dBFS in the plan and is adjusted later by the renderer/validator loop to hit the target integrated LUFS — the decision engine only sets the ceiling, not the final gain-to-target step.
5. If a reference track was supplied, AutoMix additionally computes a weighted (by each stem's linear RMS) average frequency-band profile across all stems, compares it to the reference's band profile, and adds up to +/-5 dB of peaking EQ per band (sub/bass/low_mids/mids/presence/sibilance/air) to the bus EQ to match the reference's tonal balance — each such move is logged with its exact dB figure.

Why it matters:
Separating "how much glue/color" (saturation + compressor ratio, genre-driven) from "how loud can it get" (limiter ceiling, mix-goal-driven and always the stricter of the two candidates) means a genre's aesthetic preference for a hotter, more saturated master can never accidentally violate the technical delivery target (e.g. true-peak compliance for a streaming platform) — the ceiling logic is a hard technical floor underneath the creative defaults.

Common mistakes:
- Assuming the master bus compressor's attack/release are genre-tunable — they are not; only the ratio changes per genre, attack and release are hardcoded at 30 ms / 150 ms in the decision engine.
- Assuming the limiter ceiling always equals the genre's `limit_ceiling_db` — it is actually `min()` of that value and the mix goal's own peak/true-peak check maximums, so the effective ceiling can be tighter than the genre default implies.

When this does not apply:
- Genres with `compression_ratio <= 1.0` in their `master_bus` modifier get no `bus_compressor` block at all (none currently do by default, but a ratio of 1.0 like jazz is functionally near-transparent).
- If no reference track is supplied, no reference-matching EQ bands are added to the bus at all.

Related questions:
- Why is the EDM master bus limiter ceiling -0.5 dBFS instead of -1.0 dBFS?
- Why does jazz get almost no glue compression on the master bus?
- How does AutoMix decide how much reference-matching EQ to apply to the master bus?
- Does AutoMix's master bus compressor attack time change per genre?
