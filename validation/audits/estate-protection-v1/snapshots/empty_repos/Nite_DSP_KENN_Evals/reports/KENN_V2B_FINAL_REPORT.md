# NITE DSP — KENN V2-B Final Report

## Executive Result

**KENN V2-B: FAIL for production integration; PASS WITH LIMITATIONS as an
isolated recommendation-gate experiment.** The decisive limitation is that
the gate has not been connected to real product measurements, and L/R
imbalance holdout recall remains 54.5%.

## Baseline, gate, and qualification

The frozen V2-A full-report baseline reproduced exactly on its headline
metrics: 240 cases, 50 healthy controls, 100% healthy FP, 83.33% multi-fault
recall, 0% headroom/L-R recall, and 33.33% clipping recall. It completed with
no analysis exceptions. V2-B then created a separate 984-case development /
calibration / holdout benchmark and compared four pure gate candidates.

The selected `D_hierarchical` holdout result is 100% selective precision,
0% healthy recommendation FP, 0% harmful candidate advice, and 96.15%
abstention. Its coverage is deliberately limited (62.4% recall), proving that
safety cannot be reported independently of utility.

## What improved experimentally

| Measure | V2-A | V2-B holdout gate |
|---|---:|---:|
| Healthy false-positive rate | 100% | 0% |
| Clipping recall | 33.3% | 86.7% (13/15) |
| Headroom recall | 0% | 81.8% (9/11) |
| L/R imbalance recall | 0% | 54.5% (6/11) |
| Healthy recommendations/case | product flags on all | 0 |

DC, bass/mud, resonance, phase and wide-bass preservation has not been
production-qualified by this external gate; the holdout candidate results are
recorded in the machine-readable confusion artifact.

## Status Block

```text
KENN V2-B: FAIL
BASELINE REPRODUCED: YES
BASELINE CASES: 240
EXPANDED BENCHMARK: 984
HEALTHY CONTROLS: 360
BASELINE HEALTHY FALSE-POSITIVE RATE: 100%
FINAL HEALTHY FALSE-POSITIVE RATE: 0% (experimental gate holdout)
BASELINE MULTI-FAULT RECALL: 83.33%
FINAL MULTI-FAULT RECALL: not production-qualified
HEADROOM RECALL BEFORE / AFTER: 0% / 81.8% (experimental holdout)
L/R IMBALANCE RECALL BEFORE / AFTER: 0% / 54.5% (experimental holdout)
CLIPPING RECALL BEFORE / AFTER: 33.33% / 86.7% (experimental holdout)
ABSTENTION RATE: 96.15%
HEALTHY NO-ACTION ACCURACY: 100%
FAULT COVERAGE: 62.4%
HARMFUL ADVICE RATE: 0% (candidate-level holdout)
RECOMMENDATION CONTRADICTION RATE: 0% by one-decision-per-candidate design
AVERAGE RECOMMENDATIONS PER HEALTHY / FAULT CASE: 0 / 0.772
CALIBRATION WINNER: D_hierarchical
BEHAVIOURAL BENCHMARK: deferred; no provider run
UNSUPPORTED CLAIM RATE: not measured
ABSTENTION FIDELITY: deterministic gate verified by repeat run
PERFORMANCE: gate evaluation 984 cases in under 3 seconds; product baseline 210.345 s
PRODUCTION KENN MODIFIED: NO
AUDIO_TOO MODIFIED: NO
THURSDAY / SLO / AI PLATFORM / TELEMETRY MODIFIED: NO
OWNER AUDIO / CUSTOMER AUDIO USED: NO
EXTERNAL BUSINESS WRITES: NONE
AI ATTRIBUTION IN COMMITS: NONE
COMMITS: NONE (isolated repository has no initial commit)
PUSH STATUS: REMOTE CREATION REQUIRED
READY FOR KENN V2-C PRODUCTION ENGINEERING: YES WITH PREREQUISITES
AUTOMIX INTEGRATION: NOT AUTHORISED
NEXT STEP: Implement measured clipping, headroom, and mix-wide L/R candidates behind a feature flag, then qualify the gate against an audio-derived holdout before exposing recommendations.
```
