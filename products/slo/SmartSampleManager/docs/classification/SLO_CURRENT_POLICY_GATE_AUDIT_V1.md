# SLO current policy gate audit v1

Date: 2026-09-12

## Safety finding

The older decision-policy receipt is not sufficient evidence for the current
corpus. On the current duplicate-collapsed, collection-held-out evaluation,
the existing `auto_rename` tier achieved **83.77% precision** at the fixed 0.5
confidence gate. That is below the product's intended automatic-action bar.

This is an audit only. No policy, model, rename plan, approval, or source file
was changed.

## Results

| policy arm | auto-rename share | auto-rename precision | suggest share | suggest precision |
| --- | ---: | ---: | ---: | ---: |
| audio only | 13.35% | 83.77% | 14.37% | 82.31% |
| filename override below 0.40 | 15.38% | 81.91% | 23.36% | 83.05% |
| filename override below 0.50 | 16.40% | 81.97% | 26.06% | 83.57% |
| filename override below 0.60 | 16.45% | 82.11% | 26.23% | 84.45% |

All arms used five collection-held-out seeds and five grouped folds over 1,495
rows, 27 eligible classes, and 80 collections. Filename overrides increase
coverage, but they do not make automatic action safer.

The audio-only auto tier was composed of Clap (86.81%), Kick (84.24%), and
Drum Loop (77.46%). None met a conservative 90% automatic-action bar on this
unseen-collection audit; Drum Loop is especially unsafe despite its older
receipt.

## Required next gate

Before any automatic rename can be enabled, regenerate class-conditional gates
from the current collection-held-out protocol and require each eligible class
to meet the action precision target on unseen collections. Until then, the
safe operating point is review/suggest only; this audit does not itself mutate
the existing policy because that is a product-owner decision.
