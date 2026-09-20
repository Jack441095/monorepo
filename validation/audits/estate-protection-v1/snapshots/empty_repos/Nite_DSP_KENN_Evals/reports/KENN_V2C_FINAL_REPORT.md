# NITE DSP — KENN V2-C Final Report

## Executive Result

**PASS WITH LIMITATIONS for isolated audio-derived qualification. Production
integration is not started.** V2-C replaces V2-B's abstract candidate inputs
with real decoded-PCM measurements for clipping, sample-peak headroom, and
mix-wide persistent L/R imbalance while preserving a safe abstention boundary.

## Result

`KENN_AUDIO_HOLDOUT_V1` runs 440 deterministic synthetic cases through WAV
creation, decode, measurement, candidate construction, and gate. The frozen
V2-B gate reports 0% healthy FP but abstains on derived headroom. The
separately versioned `scope_context.v2c.1` gate reaches the results below on
the frozen audio holdout; this is not a claim of generalised production
performance.

| Detector | Recall | Precision | Key boundary |
|---|---:|---:|---|
| Clipping | 20/20 (100%) | 100% | plateau/event density, not peak alone |
| Headroom | 12/12 (100%) | 100% | only mix-in-progress scope recommends |
| Mix-wide L/R | 20/20 (100%) | 100% | persistence; alternating pan abstains |

## Status Block

```text
KENN V2-C: PASS WITH LIMITATIONS
V2-B BASELINE REPRODUCED: YES
AUDIO-DERIVED HOLDOUT: KENN_AUDIO_HOLDOUT_V1
AUDIO HOLDOUT CASES: 440 (264 development / 88 calibration / 88 holdout)
HEALTHY CASES: 120
CLIPPING CASES: 80
HEADROOM CASES: 80 (20 mastered-like controls)
L/R IMBALANCE CASES: 100 (20 alternating-pan controls)
MULTI-FAULT CASES: 40
CLIPPING RECALL / PRECISION: 100% / 100%
CLIPPING SATURATION CONFUSION RATE: 0% on supplied holdout controls
HEADROOM RECALL / PRECISION: 100% / 100%
L/R IMBALANCE RECALL / PRECISION: 100% / 100%
HEALTHY FALSE-POSITIVE RATE: 0%
FAULT COVERAGE: 100% for the three V2-C target families
ABSTENTION RATE: 80.30%
HARMFUL ADVICE RATE: 0% on holdout
NO-ACTION ACCURACY: 100% (32 holdout healthy/acceptable cases)
MULTI-FAULT RECALL: target-family coverage retained; broader issue hierarchy not qualified
DC / BASS-MUD / RESONANCE / PHASE-WIDE-BASS REGRESSION: not production-qualified
FROZEN V2-B GATE: 76.92% recall, 0% healthy FP, 84.85% abstention
V2-C GATE: scope_context.v2c.1; separately versioned
ANALYSIS LATENCY P50 / P95: 23.2 ms / 66.8 ms per 0.8 s render
FEATURE FLAG: NOT CREATED (production not authorised)
AUDIO_TOO INTEGRATION: NOT STARTED
PRODUCTION KENN MODIFIED: NO
THURSDAY / SLO / AI PLATFORM / TELEMETRY / AUTOMIX MODIFIED: NO
DAW WRITES: NONE
OWNER AUDIO / CUSTOMER AUDIO USED: NO
AI ATTRIBUTION IN COMMITS: NONE
COMMITS: NONE (isolated repository has no initial commit)
PUSH STATUS: REMOTE CREATION REQUIRED
BIGGEST IMPROVEMENT: audio-derived target candidates retain 0% healthy FP while reducing abstention
BIGGEST REMAINING FAILURE: synthetic-only evidence; source-vs-master L/R context and true-peak remain unqualified
READY FOR PRODUCTION KENN INTEGRATION: YES WITH PREREQUISITES
READY FOR AUTOMIX INTEGRATION: NO
NEXT STEP: obtain a free dedicated KENN integration worktree, add KENN_MEASURED_GATE_V2C default-off, and qualify this exact pipeline against product regressions and blinded engineer review.
```
