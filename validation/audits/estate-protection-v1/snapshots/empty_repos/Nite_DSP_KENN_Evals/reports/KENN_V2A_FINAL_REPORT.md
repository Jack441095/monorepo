# KENN V2-A Final Report

## Status

**FAIL for production recommendation qualification.** No product code was modified.

`KENN_GOLDEN_BENCHMARK_V1` executed 240 deterministic, synthetic WAV cases
through the current Mix Review full-report entry point.  It completed without
analysis exceptions, but every one of 50 healthy/control cases received at
least one recommendation-driving flag (healthy false-positive rate: **100%**).

| Area | Result |
|---|---:|
| Total / healthy / single / multi | 240 / 50 / 160 / 30 |
| Mean runtime | 1.130 s per 0.75 s render (RTF 1.51) |
| Multi-fault label recall | 83.33% |
| DC / bass / resonance / mud / harshness / anti-phase / wide-bass recall | 100% each |
| Clipping / HF excess / transient peaks recall | 33.33% / 53.33% / 60% |
| Headroom / L-R imbalance recall | 0% / 0% |
| Abstention quality | 0% on healthy controls |

The most serious failure is recommendation safety, not raw feature coverage:
the current product flags healthy material as over-compressed, resonant,
low-mid-heavy, and over-widened. The existing source comment also records that
the THD estimate is unreliable on polyphonic material, yet its informational
flag still appears widely. This cannot qualify as autonomous advice.

## Next precise action

Implement a recommendation gate that suppresses non-objective flag-driven
advice unless the evidence is calibrated against healthy controls, then rerun
this frozen benchmark before any DAW-action integration.
