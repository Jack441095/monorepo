# SLO Improvement Evaluation Report V1

_Collection-held-out, 8 seeds, gates fitted on training collections only._

## Operating points

| target | best arm meeting it | coverage | precision |
|---|---|---|---|
| 85% | mw-fusion | **68.8%** | 87.6% |
| 90% | multi-window audio | **32.5%** | 91.0% |
| 95% | audio-only | 14.8% | 95.1% ⚠ marginal |

Unchanged by the policy layer — the policy does not change the classifier, it
changes what SLO *does* with it.

## Decision policy (calibrated at 0.93)

| action | share | precision |
|---|---|---|
| auto_rename | 15.1% | **90.8%** |
| suggest | 9.3% | 84.5% |
| review | 72.3% | — |
| never_act | 3.3% | — |

## Success criteria

| criterion | result |
|---|---|
| auto_rename beats raw classifier | **PASS** 89.7% vs 88.0%, +1.7pp |
| Percussion excluded from auto_rename | **PASS** 0 occurrences |
| impulse responses excluded | **PASS** 0 occurrences |
| 90% precision real, not seed noise | **PASS at cal 0.93** (90.8% over 8 seeds) |
| user sample files untouched | **PASS** 1,139 verified unmodified |
| labels safer than before | **PASS** 4 CSVs moved out of gitignore, 12 tests |

## Calibration honesty

| calibrate at | auto-rename precision | verdict |
|---|---|---|
| 0.90 | 89.7% | **undershoots** |
| **0.93** | **90.8%** | recommended |
| 0.95 | 92.9% | conservative mode |

Calibrating *at* the target undershoots by ~1pp because a threshold fitted on
seen collections is optimistic on unseen ones. Per-seed range at 0.93 is
87.1–95.2%, so the honest phrasing is **"around 90%"**, never "at least 90%".

## Is 95% supported? No.

95.1% against a 95.0% requirement is a 0.1pp margin, inside seed noise. Do not
advertise it. `family+form` clears more comfortably (95.4%) at 5.3% coverage if
a conservative mode is ever wanted.

## Rejection boundary

19.3% of junk still gets a confident real-class label; ~27% of all errors involve
the rejection boundary. Multi-window improved this by 0.9pp. **This is the
largest remaining source of user-visible harm and it needs labels, not methods.**
