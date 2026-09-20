# Research Problem Inventory & Weighted Ranking

55 problems inventoried across domains A-T.

| Rank | ID | Domain | Problem | Score | Portfolio |
|---:|---|---|---|---:|---|
| 1 | P01 | layer_alignment | Multi-layer transient timing alignment (kick/snare/clap stacks) | 8.07 | YES |
| 2 | P02 | layer_alignment | Polarity decision per layer | 7.77 | YES |
| 3 | P09 | low_end | Kick/bass fundamental collision detection | 7.48 | YES |
| 4 | P10 | low_end | Low-frequency partial cancellation detection | 7.46 | YES |
| 5 | P04 | layer_alignment | Snare/clap stack alignment | 7.34 |  |
| 6 | P05 | phase | Parallel processing path latency compensation | 7.23 |  |
| 7 | P26 | stereo | Mono-collapse risk quantification with band localisation | 7.1 | YES |
| 8 | P15 | gain | Headroom inefficiency from low-end summation | 7.05 | YES |
| 9 | P17 | masking | Time-frequency critical-band overlap vs static spectrum overlap | 6.98 | YES |
| 10 | P27 | stereo | Side-heavy bass detection | 6.82 | YES |
| 11 | P13 | stereo | Sub-bass mono compatibility (club systems) | 6.74 |  |
| 12 | P19 | masking | Discriminate benign/musical overlap from problematic masking | 6.72 | YES |
| 13 | P22 | dynamics | Over-compression / punch-loss detection | 6.72 | YES |
| 14 | P06 | layer_alignment | Sample-replacement timing to original performance | 6.68 |  |
| 15 | P23 | transients | Layered percussion reinforcement vs cancellation | 6.66 | YES |
| 16 | P41 | sample_context | Sample-in-context compatibility scoring ('fits THIS track') | 6.62 |  |
| 17 | P11 | low_end | Bass decay masking next kick transient | 6.61 | YES |
| 18 | P54 | sampling | Multi-zone sampling vs single-root extreme transposition | 6.59 | YES |
| 19 | P31 | resonance | Stable resonance vs musical harmonic discrimination | 6.5 | YES |
| 20 | P16 | masking | Vocal vs lead synth masking | 6.39 |  |
| 21 | P03 | phase | Frequency-dependent (all-pass) misalignment detection | 6.34 | YES |
| 22 | P52 | distortion | Clipping diagnosis (hard clip vs intentional saturation) | 6.28 |  |
| 23 | P40 | translation | Streaming loudness normalisation mismatch prediction | 6.26 |  |
| 24 | P47 | gain | Delivery loudness target deviation early warning | 6.26 |  |
| 25 | P48 | gain | Bus overload / intersample peak risk | 6.26 |  |
| 26 | P29 | stereo | False-positive-safe width assessment (Haas/decorrelated reverb is lega | 6.24 | YES |
| 27 | P12 | low_end | Sidechain necessity detection | 6.2 |  |
| 28 | P35 | resonance | Temporary spectral peak vs persistent resonance | 6.13 | YES |
| 29 | P43 | sample_context | Sample key/fundamental clash detection | 6.13 |  |
| 30 | P42 | timbre | Timbre matching for layering suggestions | 6.11 |  |
| 31 | P37 | translation | Mono translation loss prediction | 6.09 |  |
| 32 | P53 | distortion | Intersample peak clipping risk on consumer DACs | 6.06 |  |
| 33 | P21 | dynamics | Transient smearing detection after limiting | 6.05 |  |
| 34 | P55 | sampling | Root-note/fundamental detection accuracy for sampled notes | 6.01 |  |
| 35 | P07 | phase | Multi-mic drum phase alignment (OH vs close) | 5.98 |  |
| 36 | P33 | resonance | Sibilance energy profiling for de-ess guidance | 5.97 |  |
| 37 | P28 | stereo | Asymmetric stereo / image shift | 5.88 |  |
| 38 | P14 | low_end | Kick tuning vs track key relation | 5.87 |  |
| 39 | P46 | gain | Gain-staging inconsistency across stems | 5.86 |  |
| 40 | P44 | sample_context | One-shot class/transient matching for replacement | 5.67 |  |
| 41 | P36 | translation | Phone-speaker robustness indicators | 5.61 |  |
| 42 | P20 | arrangement | Frequency hoarding across arrangement density | 5.59 |  |
| 43 | P45 | sample_context | Library OOD detection (sample unlike anything in library) | 5.56 |  |
| 44 | P32 | resonance | Harshness detection in 2-5 kHz region | 5.52 |  |
| 45 | P08 | layer_alignment | Abstention: double-tracks/loose performances must NOT be tightened | 5.51 | YES |
| 46 | P24 | transients | Attack-slope conflict between stacked layers | 5.36 |  |
| 47 | P34 | resonance | Low-mid build-up diagnosis | 5.36 |  |
| 48 | P49 | reverb | Reverb tail masking following transients | 5.32 |  |
| 49 | P30 | stereo | Reverb-return correlation problems | 5.26 |  |
| 50 | P18 | masking | Harmonic density masking in dense arrangements | 5.22 |  |
| 51 | P38 | translation | Small-speaker LF rolloff audibility check | 5.16 |  |
| 52 | P25 | transients | Transient-density overload in busy sections | 4.71 |  |
| 53 | P39 | translation | Club/car LF-emphasis robustness | 4.58 |  |
| 54 | P50 | reverb | Pre-delay/early-reflection clutter diagnosis | 4.34 |  |
| 55 | P51 | reverb | Ambience balance judged in context of arrangement density | 4.29 |  |

## Selected research portfolio (18 problem IDs -> 6 experiment tracks + shared lib)

- Track A (deterministic DSP, priority): P01, P02, P03, P04-family, P08 abstention, P23
- Track B (contextual DSP): P09, P10, P11, P15
- Track C (contextual analysis + ML-assisted classifier): P17, P19 (+P16 fixtures)
- Track E (deterministic DSP + controls): P26, P27, P28, P29
- Track F (deterministic DSP near-miss discipline): P31, P35
- Track J (DSP/ML-assisted falsification): P54, P55
- Workflow/product problem covered by Track A (alignment = Product #2 candidate under falsification)
