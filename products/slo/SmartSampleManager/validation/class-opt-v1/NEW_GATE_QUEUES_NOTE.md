# New Gate Queues — Hi-Hat Sourced, Percussion/Foley Blocked (2026-09-18, slo/class-opt-v1)

## Shipped: Hi-Hat candidates
- `hihat_gate_candidates_v1.json`: **64 Hi-Hat rows, 8 vendors**
  (Organic Drum Kit 32, KSHMR Vol.3 18, + 6 more), confidence 0.827–0.938,
  sourced from `tools/classification_benchmark/full_taxonomy_high_confidence_review_v1.csv`.
- Schema matches the blind-exporter input (`id, path, candidate_class,
  candidate_confidence, vendor`).

## To run (on the machine with the sample library mounted — NOT this one)
The `testing-for-NITE-DSP` corpus is absent here (0/64 paths resolve), and the
blind exporter hashes file bytes, so export must run where the library lives:
1. Rebase paths if the mount differs, verify ≥40 resolve.
2. `build_blind_class_gate_review_queue.py` → candidate-hidden review CSV.
3. Owner labels 40 blind → import → `audit_class_conditional_gates.py`.
4. Promote only on Wilson-95 lower ≥ 0.95 (same bar as QC-02).

## Blocked: Percussion / Foley queues
- No existing review CSV contains Percussion/Foley candidates in usable volume
  (`owner_review_queue.csv` has 3 Percussion; high-confidence review has 0).
- Next: mine candidates from corpus predictions on the mounted machine
  (needs sklearn/soundfile env — absent here, see baseline receipt), targeting the
  known worst confusion first: **Foley→Percussion (309 cases)** per the encoder memo.
- Kill criterion: if blind-labelled precision (Wilson lower) < 0.95, expand n
  instead of lowering the bar; if Foley/ hide under filename evidence, fix fusion
  weights (QC-01 follow-up) before re-queueing.
