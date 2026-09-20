# R&D-C — KENN Intelligence Qualification Report

## Benchmark

`KENN_MIX_EVAL_0.1`, deterministic synthetic fixtures, seed `20260822`. Five cases cover healthy reference, 3.2 kHz harshness, sub excess, hard clipping, and stereo mono-cancellation. Results are in `kenn_eval/results.json` and `kenn_eval/results.csv`.

## Results

| Dimension | Result |
|---|---:|
| Problem detection | 100% on 4 injected problems |
| Evidence accuracy | 100% |
| Diagnosis accuracy | 100% |
| Severity MAE | 0.0 on this fixture set |
| Recommendation safety | 100% |
| Unnecessary processing rate | 0% |
| Unsupported claim rate | 0% |
| False-positive mix problem rate | 0% on one healthy case |

## Interpretation

**Observed:** the detector identifies controlled conditions and abstains on the healthy fixture. Recommendations are deliberately conservative and include evidence strings.

**Not established:** real-mix generalisation, subjective recommendation quality, translation across genres, or KENN production behavior. The benchmark is a qualification harness, not a replacement for the live KENN engine.

## Taxonomy

Initial permanent golden-case taxonomy should include spectral imbalance, low-mid buildup, harshness, masking, kick/bass conflict, vocal masking, over/undercompression, clipping/limiting, transient loss, stereo/phase, mono incompatibility, DC, noise, headroom, resonance, sibilance, mud, boxiness, brightness, and translation risk. Each case must separate measurable evidence from artistic preference.

## Biggest weakness

Coverage and realism. One fixture per condition cannot establish behavior. The next benchmark should add parameter sweeps, healthy mixes across genres, mixed conditions, near misses, and human-reviewed acceptable interpretations.

## Next improvement

Build a versioned golden-case manifest with expected evidence ranges, severity intervals, dangerous recommendations, and abstention requirements. Score the decision separately from prose similarity.
