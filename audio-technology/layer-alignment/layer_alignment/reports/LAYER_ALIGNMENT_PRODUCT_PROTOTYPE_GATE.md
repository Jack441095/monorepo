# LAYER ALIGNMENT PRODUCT PROTOTYPE GATE (V1 — AUTHORISED CORPUS RUN)
### Decision: AWAITING HUMAN REVIEW — perceptual gates pending; safety/accuracy gates closed

## Frozen gate thresholds (unchanged; §29-§30)

| gate | threshold | result |
|---|---|---|
| real-material healthy correction-FPR | ≤5% | **PASS — 3.41% (6/176, all on deliberately dispersive LR4 constructions; multi-objective gap logged V2-B12)** |
| suggestions useful by ear | ≥80% | AWAITING REVIEW (52-judgement pack ready) |
| harmful suggestions | ≤5% | AWAITING REVIEW (zero harmful events observed mechanically) |
| analysis latency uncontested | <250 ms/pair | NOT CERTIFIED — host load 46–88; contested p50 ≈657 ms; native C++ path expected to clear once measured fairly |
| C++ parity (real audio) | PASS | **PASS** (10/10 pairs) |
| failure isolation | PASS | **PASS** (9/9 typed-safe) |

Disclosed detail: the six corrections were ALIGN suggestions on
constructed dispersive pairs where low-band summation genuinely improved;
upper-band degradation was unpenalised by the frozen objective. Gate passes
within threshold but the hardening requirement is recorded.

## Coverage disclosure

Natural-material actionable coverage = 2/109 (1.8%). Safety-first but
commercially thin. Multimic/transient domain shows the strong signal
(both natural ALIGNs are multimic drum pairs with high confidence and
positive predicted benefit). Domain-limited promotion is available
immediately after a successful review of the ready pack.

## Pre-registered decision rule (unchanged)

All gates pass → PROMOTE TO PRODUCT PROTOTYPE · transient domain passes,
tonal fails → PROMOTE WITH DOMAIN LIMITATION · fixable weakness → CONTINUE
R&D · frequent harm/FPR → PARK.
