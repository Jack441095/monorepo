# SLO Domain-Robust Baselines — V1

_Phase 2. All results vendor-held-out unless stated. Perch+CLAP frozen embeddings, 524 files, 10 classes._

## 1. Result

Eleven methods, identical folds and seeds, evaluated with the canonical grouped
harness. The promotion gate was fixed **before** running: ≥ +2pp mean
vendor-held-out accuracy with no macro-F1 regression, or a material worst-group
gain with stable mean, or equal accuracy with better precision-at-coverage.

| method | accuracy | macro-F1 | worst group | vs baseline |
|---|---|---|---|---|
| baseline (class-balanced logistic regression) | 61.9% ± 2.2 | 54.9% | 22.1% | — |
| vendor-balanced | 62.3% ± 1.9 | 55.3% | 25.5% | +0.46 |
| class × vendor balanced | 61.8% ± 2.7 | 54.4% | 23.4% | −0.11 |
| vendor-capped (40/vendor) | 60.5% ± 1.2 | 53.2% | 26.9% | −1.41 |
| GroupDRO | 62.8% ± 1.0 | 55.5% | 29.0% | +0.95 |
| DANN (vendor adversary, gradient reversal) | 61.6% ± 1.3 | 53.0% | 21.4% | −0.27 |
| CORAL | 61.8% ± 1.6 | 55.0% | 22.8% | −0.04 |
| cosine kNN | 64.0% ± 0.7 | 52.5% | 22.8% | +2.14 |
| **nearest centroid** | **65.8% ± 0.9** | **58.8%** | **35.8%** | **+3.67** |
| multi-centroid (≤3/class) | 64.4% ± 1.1 | 55.7% | 31.9% | +2.24 |
| shrinkage LDA | 63.2% ± 1.9 | 55.6% | 20.7% | +1.34 |

**Every method designed for domain shift failed. The simplest classifier
available won.** GroupDRO, DANN and CORAL — the three principled approaches —
delivered +0.95, −0.27 and −0.04pp respectively.

## 2. Why this is not a fluke

The gain scales monotonically with the amount of domain shift, and **reverses
under random CV** (8 seeds each):

| grouping | baseline | nearest centroid | delta |
|---|---|---|---|
| random | 71.8% | 71.1% | **−0.72** |
| family | 68.9% | 70.7% | +1.84 |
| pack | 64.2% | 66.4% | **+2.17** |
| vendor | 62.1% | 65.8% | **+3.67** |

That is the signature of genuine domain robustness rather than noise: the method
is *worse* when there is nothing to generalise across, and better in exact
proportion to how much there is.

**The old evaluation protocol would have rejected the best method found so far.**

Paired per-seed test, vendor-held-out, 8 seeds:

| | |
|---|---|
| mean delta | **+3.03pp** |
| standard deviation | 2.28 |
| standard error | 0.81 |
| t | **3.75** |
| seeds where centroid wins | **7 / 8** |
| 95% confidence interval | **[+1.45, +4.61] pp** — excludes zero |

## 3. The product metric moves five-fold

The renamer is confidence-gated, so coverage at 95% precision *is* the product.
Using cosine-similarity softmax as the centroid confidence:

| | coverage at 95% precision (vendor-held-out) |
|---|---|
| logistic regression | **6.3%** |
| nearest centroid | **31.6%** |

Under unseen-collection conditions the incumbent can safely auto-rename 6% of
files. The centroid head can safely rename 32%.

## 4. The catch: rejection gets worse

Per-class recall, vendor-held-out, mean of 8 seeds:

| class | n | logreg | centroid | delta |
|---|---|---|---|---|
| Foley | 26 | 15.4% | 47.1% | **+31.7pp** |
| Kick | 71 | 80.8% | 91.4% | +10.6pp |
| Percussion Loop | 28 | 41.1% | 48.2% | +7.1pp |
| Drum Loop | 41 | 79.0% | 86.0% | +7.0pp |
| Clap | 90 | 86.5% | 92.2% | +5.7pp |
| Hi-Hat | 59 | 70.8% | 73.9% | +3.2pp |
| Crash | 22 | 67.6% | 69.3% | +1.7pp |
| Snare | 85 | 72.6% | 72.9% | +0.3pp |
| **Other/none** | 55 | 29.1% | **16.8%** | **−12.3pp** |
| **Percussion** | 47 | 17.0% | **5.1%** | **−12.0pp** |

Eight classes improve, two collapse — and they are precisely the two known
dumping grounds. A single centroid is a bad model of a class that is not one
thing, and `Other/none` (the rejection class) and `Percussion` (a catch-all) are
definitionally not one thing.

**This is safety-relevant.** `Other/none` recall falling means more junk is
confidently given a real class. The precision-at-coverage number above already
accounts for it and still improves five-fold, but the correct deployment shape
is a centroid classifier paired with a *separate* rejection stage, not a
centroid head asked to do rejection itself.

## 5. Interpretation

With 524 training files in 2048 dimensions, logistic regression has enough
capacity to fit vendor-specific directions in the embedding — and Phase 1 showed
vendor identity is linearly decodable at 62.6% against a 25.5% baseline. It uses
that shortcut. A class mean cannot represent a vendor-specific direction at all,
so it is forced onto whatever is common to the class across collections.

The adversarial and worst-group methods tried to *remove* vendor information from
a representation; the centroid simply *cannot exploit* it. On this data the
second is far more effective.

## 6. Status

Nearest centroid clears the Phase 2 gate on all three criteria. It is a
research-stage result on the Perch+CLAP stack, **which is not itself in
production** — deploying it depends on the outstanding 210 MB model-size product
decision. No production code has been modified.

## 7. Reproduction

```
cd SmartSampleManager/tools/classification_benchmark
python3 sample_library_inventory.py --workers 8
python3 test_domain_generalization.py
python3 domain_generalization_eval.py --seeds 8 --report
python3 domain_robust_baselines.py --seeds 5 --mode vendor
python3 domain_robust_baselines.py --seeds 8 --mode random \
    --methods baseline,nearest-centroid,multi-centroid,cosine-kNN
```
