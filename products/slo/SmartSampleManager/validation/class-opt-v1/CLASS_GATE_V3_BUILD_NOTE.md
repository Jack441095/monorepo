# Class-Gate Validation V3 — Build Note (2026-09-18, branch slo/class-opt-v1)

## What was built
- `class_conditional_gate_validation_manifest_v3.json`: **40 rows, all Kick**, 7 vendors,
  round-robin, exact + near-duplicate excluded.
- Exclusions: combined v1 (120) + v2 (72) = 192 unique paths (`/tmp/combined_excluded.json`
  pattern; rebuild with both manifests to reproduce).
- Command:
  `build_class_conditional_gate_validation_manifest.py --exclude-manifest <combined v1+v2>
  --per-class 40 --out validation/class-opt-v1/class_conditional_gate_validation_manifest_v3.json`
- Receipt: `class_conditional_gate_validation_manifest_v3_receipt.json`
  (n_queue_rows 408, n_eligible 157, n_selected 40, n_excluded_previous 192).

## What the queue cannot give
- Source queue (`class_conditional_gate_testing_review_v1.csv`) contains **only 3 of 16
  classes**: Kick 280 / Snare 81 / Clap 47 rows (eligible: 253 / 74 / 46).
- After v1+v2+v3: Clap fully exhausted (46/46 used), Snare remainder unselectable under
  current duplicate rules (8 nominally left, 0 selected — near-duplicate exclusion),
  Kick now 40+40+40 across batches (verify overlap = 0 before labelling).
- **13/16 classes have no gate queue at all**: Hi-Hat, Percussion, Foley, Bass Loop,
  Bass One-Shot, FX, Impact, Music Loop, Riser, Synth, Synth Loop, Vocal Loop,
  Vocal Phrase. No manifest can be built for them until a queue exists.

## Statistical bar (unchanged — no promotion in this pass)
- v1 validation: Clap/Kick/Snare precision 97.5–100% descriptive, but
  **statistically_supported_95 = none** (Wilson lower 0.87–0.91).
- Promotion rule (unchanged): sealed-set re-validation with Wilson-95 lower ≥ 0.95
  per class before any `BetaDecisionPolicy` threshold change. V3 rows are
  **pending owner by-ear labels**; nothing is promoted by building a manifest.

## Next sourcing (needs Jack)
1. Label v3 (40 Kick) + adjudicate with the same blind protocol as v1.
2. Build new queues for the next 3 classes by confusion priority: **Hi-Hat /
   Percussion / Foley** (largest residual confusions per encoder decision memo:
   Foley→Percussion 309 cases, Perc/Hi-Hat cross-confusion).
3. Re-run `audit_class_conditional_gates.py` once v3 labels land; promote only on
   the statistical bar above.
4. Kill criterion: if v3-labelled Kick precision (Wilson lower) < 0.95, do NOT
   promote Kick — expand n instead of lowering the bar.
