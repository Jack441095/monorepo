# R&D-E — Source Reconstruction Sampler Report

## Benchmark

`SAMPLER_RECON_EVAL_0.1`, seed `20260822`, five controlled signals: sine, saw, FM, pluck, and noise-layered bass. The experimental path is a small phase-vocoder prototype; the baseline is polyphase resampling. Results are in `reconstruction_sampler/results.json` and `reconstruction_sampler/results.csv`.

## Measured results

| Method | Mean pitch error | Mean duration error | Mean centroid-drift proxy |
|---|---:|---:|---:|
| Resampling baseline | 18.1 Hz | 0.500 s | 2117.3 Hz |
| Reconstruction PV prototype | 32.3 Hz | 0.000 s | 2115.5 Hz |

## Interpretation

**Observed:** resampling changes duration by 0.5 seconds for this 1.5x shift. The phase-vocoder path restores duration exactly. On this fixture set it worsens dominant-frequency error and does not materially improve the centroid-drift proxy.

**Negative result:** duration preservation alone is not a quality win. This prototype must not be promoted.

## Feasibility verdict

**PROMISING WITH LIMITATIONS.** The problem is real and multi-sample intelligence may be more feasible than universal single-sample reconstruction. The current implementation is not a product-quality algorithm.

## Best approach

Research a hybrid offline representation: transient/body/noise/sub/tail decomposition, harmonic-plus-noise modeling where stable, and source-zone selection when multiple notes are supplied. Heavy analysis belongs offline; real-time playback should consume precomputed representations with predictable CPU and no audio-thread allocation.

## Biggest technical risks

Phase-vocoder transient smearing, modulation-rate artifacts, stereo image instability, aliasing, and the gap between objective proxies and listener preference. Neural approaches should only enter after classical baselines and listening tests establish a clear deficit.

## Product potential

High technical interest, medium commercial confidence. The stronger initial product wedge may be multi-sample root detection, zone mapping, nearest-source selection, and crossfade quality rather than a promise of perfect timbre preservation from one source.
