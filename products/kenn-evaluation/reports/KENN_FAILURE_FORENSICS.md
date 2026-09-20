# Failure Forensics

| Finding | Class | Evidence | Priority |
|---|---|---|---|
| Healthy-control false positives | threshold/calibration | 50/50 flagged | P0 |
| LRA over-compression flag | metric/context | 240/240 emitted | P0 |
| Resonance flag duplication | metric/aggregation | 789 emitted flags over 240 files | P0 |
| Informational THD clipping claim | confidence/language | emitted on controls; source labels metric unreliable on complex mixes | P0 |
| L/R imbalance miss | threshold/feature | 0/15 detection | P1 |
| Headroom miss | threshold/ground truth mapping | 0/15 detection | P1 |
| Clipping weak recall | detector/threshold | 5/15 detection | P1 |

Do not tune these thresholds blindly. First define metric validity domains,
deduplicate events by causal measurement, and test a calibrated decision gate.
