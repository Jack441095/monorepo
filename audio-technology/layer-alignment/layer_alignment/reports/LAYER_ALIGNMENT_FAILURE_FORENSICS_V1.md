# LAYER ALIGNMENT FAILURE FORENSICS V1 (REAL-AUDIO CORPUS RUN)
### Frozen engine on 387 owner-authorised pairs — failures and refusals examined, nothing patched

## F-R1. Natural-material actionable coverage 1.8% (the big finding)

107/109 natural production pairs abstain. Taxonomy:

| abstention class | n | mechanism |
|---|---|---|
| non-overlapping spectra guard | 63 | **metric limitation**: bin-level spectral overlap under-measures sparse-harmonic musical overlap (a kick's few partials barely intersect a bass line's dense harmonics bin-by-bin even when musically allied) |
| periodic ambiguity override | 25 | legitimate: 10 s musical windows contain multiple near-equal lags; refusing to guess is correct |
| weak relationship score | 19 | mixed: some genuinely unrelated complements, some over-conservative |

→ V2-B7: replace bin-overlap with band-level overlap; consider
onset-gated/transient-window analysis mode for rhythmic pairs.

## F-R2. Distorted one-shots refuse rather than err

17/102 controlled cases abstained — dominated by tanh-distorted variants.
On real material, hard waveshaping degrades correlation structure more than
synthetic fixtures suggested; the engine converts uncertainty into refusal.
Safe direction, coverage cost. → V2-B9: distortion-robust weighting
(e.g., magnitude-domain correlation) if listening shows real demand.

## F-R3. Six unjustified corrections on constructed dispersive pairs

correction-FPR 6/176 = 3.41% (gate ≤5% holds). All six are LR4-crossover
recombinations of real one-shots where the suggested global delay raised
low-band summation enough to clear the benefit gate while degrading upper
bands unpenalised. The synthetic programme measured negative delay-only
recovery on LR4 broadband stems; the real-corpus variant (narrower
crossovers, one-shot material) passed the frozen gates. → V2-B12: add an
explicit no-other-band-degrades condition to the recommendation objective.

## F-R4. The two natural ALIGNs are textbook cases

kick-in/out (+39.5 samples, +2.46 dB predicted low-band gain) and snare
top/bottom with polarity inversion (−112.75 samples). The engine's domain
instinct matches the canonical commercial use case exactly.

## F-R5. Harness-side defects fixed during this run (engine untouched)

- `pick_diverse`/`_domain_pool` kwarg mismatches (build tooling)
- evidence slice edge case for very short files
- float32-format WAVs rejected by stdlib wave → afconvert-derived PCM24
  fallback cache added (originals untouched)
- pack-stage audio materialisation for trap entries
- bench RSS unit handling on macOS

## F-R6. Bench environment

Host load 46–88 throughout; bench correctly refuses uncontested
certification. p50 ≈657 ms contested on ~1 s stem windows. Uncontested
<250 ms gate remains unverified until a quiet window or native C++
integration exists (V2-B3 stands).
