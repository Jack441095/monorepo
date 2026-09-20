# SLO class-conditional gate audit — V1

Date: 2026-09-11

## Result

On the corrected 1,553-row corpus, three classes had a conservative per-class
confidence threshold with at least 20 accepted examples in every one of eight
vendor-held-out seeds while maintaining measured precision at or above 95%:

| class | conservative confidence threshold | minimum accepted rows/seed |
|---|---:|---:|
| Clap | 0.750 | 50 |
| Kick | 0.798 | 47 |
| Snare | 0.660 | 47 |

This is stronger evidence than a single global gate, but it is still training-
corpus evidence and is not new-domain qualification.

## Review-only projection

Applying those thresholds to the 7,315-file testing embedding cache produced
408 review candidates after also requiring the research model's similarity gate:

| projected class | review candidates |
|---|---:|
| Kick | 280 |
| Snare | 81 |
| Clap | 47 |

Of those candidates, 35 are in exact-content duplicate groups and 51 are in
acoustic near-duplicate groups. Every row is explicitly
`review_candidate_only`; no auto action or rename plan was created.
Exact-duplicate, acoustic-near-duplicate, filename-conflict, and new-domain
review remain mandatory before any policy change.

## Human validation manifest

To validate the promising subset without spending labels on repeated content, a
separate 120-file manifest was built: 40 Clap, 40 Kick, and 40 Snare files,
selected round-robin across vendors after excluding both exact and acoustic
near-duplicate groups. It is inert until opened in a labeller; no server was
started or restarted for this build.

- Manifest: `SmartSampleManager/tools/classification_benchmark/class_conditional_gate_validation_manifest_v1.json`
- Selection receipt: `SmartSampleManager/tools/classification_benchmark/class_conditional_gate_validation_manifest_v1_receipt.json`

The dedicated validation labeller is available at `http://127.0.0.1:8771`.
It has now completed all 120 items. The integrity and evaluation receipts show
Clap 39/40, Kick 40/40, and Snare 40/40; all three are descriptive candidates
but none has a Wilson-supported 95% lower bound, so no class is promoted.
The separate health receipt is
`SmartSampleManager/tools/classification_benchmark/results_class_conditional_gate_labeller_audit_v1.json`.
The fail-closed evaluator is ready at
`SmartSampleManager/tools/classification_benchmark/evaluate_class_conditional_gate_validation.py`; it refuses to produce a qualification receipt until every manifest row has a usable human label.

The localhost review workspace is currently serving this queue at
`http://127.0.0.1:8765` with `/api/class-gate`; a live smoke test returned the
summary and filtered Kick candidates. The workspace remains read-only and
does not serve source audio or expose an apply operation.

## Receipts

- Gate audit: `SmartSampleManager/tools/classification_benchmark/results_class_conditional_gates_granularity_v1.json`
- Testing projection: `SmartSampleManager/tools/classification_benchmark/results_class_conditional_gate_testing_review_v1.json`
- Review CSV: `SmartSampleManager/tools/classification_benchmark/class_conditional_gate_testing_review_v1.csv`
- Physical cards: `SmartSampleManager/tools/classification_benchmark/results_class_conditional_gate_testing_cards_v1.json`
- Runner: `SmartSampleManager/tools/classification_benchmark/audit_class_conditional_gates.py` and `project_class_conditional_gate_review.py`
