# SLO current class-gate recalibration v1

Date: 2026-09-12

## Decision

Nested collection-held-out calibration does not recover a safe broad automatic-
rename tier. The confidence thresholds must not be promoted into production.

## Results

Gates were fitted inside three-fold grouped calibration splits within each
outer test fold, with at least 20 calibration predictions per class.

| target calibration precision | held-out auto share | held-out precision |
| ---: | ---: | ---: |
| 90% | 18.97% | 84.63% |
| 95% | 10.22% | 86.39% |

At the 90% target, only Bass Reese exceeded 90% on the aggregate held-out
rows (90.91%); the other classes remained below target. At the 95% target,
Bass Reese reached 93.13%, while no other class reached 90%. These are audit
results, not an approval to auto-rename Bass Reese: the result needs an
independent, sealed product validation set and a taxonomy decision first.

## Dedicated human validation result

The 120-file validation set is complete and its CSV passed the read-only
integrity audit.

| candidate class | labelled | correct | precision | Wilson lower 95% |
| --- | ---: | ---: | ---: | ---: |
| Clap | 40 | 39 | 97.5% | 87.12% |
| Kick | 40 | 40 | 100.0% | 91.24% |
| Snare | 40 | 40 | 100.0% | 91.24% |

All three are descriptively above 95%, but none has the required Wilson-
supported 95% lower bound. The one disagreement is a Clap candidate labelled
`Vocal One-Shot`. The fail-closed promotion packet therefore marks all three
classes for separate explicit review, with zero automatic approval.

Receipts:

- `results_class_conditional_gate_validation_v1.json`
- `results_class_conditional_gate_validation_label_integrity_v1.json`
- `results_class_gate_promotion_review_packet_v1.json`

No policy, model, rename plan, or source file was changed.
