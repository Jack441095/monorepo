# SLO mechanism-specific pairwise benchmark v1

Date: 2026-09-12

## Decision

The physical descriptors do not clear the +2pp gate even on the known difficult boundaries. They may still be retained as explanation evidence, but there is not yet enough evidence to promote a mechanism-specific classifier or rule.

## Results

All results use five collection-held-out seeds and five grouped folds. The delta is fused embedding + waveform evidence versus embedding-only.

| boundary | embedding | fused | delta |
| --- | ---: | ---: | ---: |
| Bass Hit / Bass Reese | 97.95% | 97.95% | +0.00pp |
| Percussion / Percussion Loop | 92.40% | 92.71% | +0.31pp |
| Hi-Hat / Hi-Hat Loop | 93.95% | 93.95% | +0.00pp |
| Synth Loop / Synth One-Shot | 87.44% | 88.72% | +1.28pp |
| Vocal Loop / Vocal One-Shot | 73.16% | 73.16% | +0.00pp |
| Foley / Impact | 84.06% | 84.20% | +0.14pp |

The largest result is the Synth form boundary at +1.28pp, still below the promotion gate and not stable enough to alter global policy. Waveform-only performance was consistently weaker than the frozen embedding; the useful signal is at most a small conditional tie-breaker.

## Product implication

Keep physical measurements in the evidence record and definition card. Do not let them override the incumbent classifier. A future targeted experiment should focus on form-aware temporal features for sustained-vs-one-shot synth material, with an independently sealed review set, rather than broad labelling or generic waveform fusion.

