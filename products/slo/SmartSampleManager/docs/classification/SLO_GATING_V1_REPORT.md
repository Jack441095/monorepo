# SLO Confidence Gating — V1

_Collection-held-out, nearest-centroid incumbent v2, 764 files, 70 collections._

## Why this matters

The renamer only acts above a confidence threshold, so **coverage at a precision
target is the product**. The incumbent reaches 18.8% coverage at 95% precision.
Per-class behaviour is very uneven — Clap recall 91.8% and Kick 85.9% against
Percussion 17.9% — so a single global gate makes the reliable classes pay for
the unreliable ones. Per-class gates should therefore help.

## Headline: per-class gating is REJECTED

At first glance it looks like a large win:

| target | global coverage | per-class coverage | delta |
|---|---|---|---|
| 0.90 | 42.2% | 49.8% | +7.60 |
| 0.95 | 25.4% | 40.1% | +14.70 |
| 0.98 | 14.2% | 35.6% | **+21.46** |

**All three "gains" are bought by accepting more mistakes.** The precision
actually delivered on unseen collections:

| calibration target | global precision | per-class precision |
|---|---|---|
| 0.900 | 88.8% (**−1.2pp**) | 79.8% (**−10.2pp**) |
| 0.950 | 93.1% (**−1.9pp**) | 82.9% (**−12.1pp**) |
| 0.980 | 95.8% (**−2.2pp**) | 85.3% (**−12.7pp**) |
| 0.990 | 96.8% (−2.2pp) | 85.3% (−13.7pp) |
| 0.995 | 96.8% (−2.7pp) | 85.3% (−14.2pp) |

A gate promising 95% precision that delivers 82.9% is not a gate. **Rejected.**

The cause is sample size: each per-class threshold is fitted on that class's
slice of the calibration set — often a few dozen files — so it overfits the
calibration collections badly. The global threshold uses every calibration
point and transfers far better.

## The finding that matters more

**No threshold fully keeps its promise on an unseen collection.** Even the
global gate undershoots by 1.2–2.7pp, and the shortfall grows as the target
rises. A threshold calibrated on collections you have seen is systematically
optimistic on collections you have not.

This is a product-safety issue independent of gating strategy: the shipped
"95% precision" promise would be ~93% in the field.

**It is correctable.** The shortfall is stable and roughly 2–3pp, so calibrating
at a higher target delivers the intended precision:

| to actually deliver | calibrate at | measured precision | coverage |
|---|---|---|---|
| 90% | 0.95 | 93.1% | 25.2% |
| **95%** | **0.98** | **95.8%** | **14.8%** |
| 96.8% | 0.99 | 96.8% | 12.2% |

The honest cost: a genuine 95% guarantee on unseen collections costs coverage —
14.8%, not the 18.8% the naive calibration claims.

## Recommendation

1. **Keep the global gate.** Per-class gating is rejected on precision grounds.
2. **Calibrate ~3pp above the intended target** to absorb the domain-shift
   shortfall, and re-measure this offset whenever the corpus changes.
3. **Quote coverage honestly**: 14.8% at a real 95%, not 18.8%.
4. The route to better coverage is a better model on the weak classes — which
   the coherence work says is a taxonomy problem, not a threshold problem.

## Reproduction

```
cd SmartSampleManager/tools/classification_benchmark
python3 per_class_gating.py --seeds 8
```
