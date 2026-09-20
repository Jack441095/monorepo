# SLO granularity-label integration — V1

Date: 2026-09-11

## Result

The completed granularity and escape-hatch labels have been integrated into a
new archived ground-truth build. The source audio was read-only throughout.

- 320 granularity rows plus 51 recovery rows were normalized.
- 278 usable unique labels entered the normalized source.
- 22 taxonomy-gap rows remain held for an owner decision.
- 71 rows remain dropped because they contain no recoverable sound identity.
- 9 labels were recovered from notes attached to an escape hatch.
- 61 old `Other/none` labels were explicitly corrected to supported classes.
- Canonical ground truth is now 1,282 files across 80 collections.
- The previous ground-truth build was archived to `~/slo_label_backups/` before
  writing the new one.

The ground-truth verifier passed all checks: checksums, unique paths,
taxonomy/subtype conformance, collection-isolated folds, sealed collections,
source-file existence, and off-drive backup.

## Same-row, same-fold measurement

To isolate the effect of the labels, the old and new labels were evaluated on
the identical 1,553 v4b paths and identical frozen 2,048-D Perch+CLAP
embeddings. Eight seeds of five-fold vendor-held-out nearest-centroid
evaluation were used, with exactly the same fold assignments for both label
versions.

| label version | accuracy | macro-F1 | coverage @90 / @95 precision |
|---|---:|---:|---:|
| v4b labels | 55.71% ± 0.65 | 47.73 | 23.3% / 13.4% |
| corrected granularity labels | 58.07% ± 0.42 | — | — |

The strict same-fold accuracy change was **+2.25 percentage points ± 0.44**,
positive on **8/8 seeds**. The independently generated full evaluation receipt
for the relabelled corpus reports 57.99% ± 0.42, macro-F1 49.39, and coverage
26.7% / 15.5%; its fold stratification is allowed to respond to the corrected
labels, so the strict same-fold receipt is the promotion comparison.

This clears the project’s +2pp research gate, but it is a **ground-truth
correction**, not a new encoder improvement. The frozen production model has
not been replaced.

## Research model and safety boundary

A separate 27-class research centroid model was frozen from the corrected
corpus. Its OOF accuracy is 57.99%; its 95% confidence gate covers 15.2% of
the corrected evaluation rows. A review-only audit on the 7,315-file testing
embedding cache found 1,071 prediction changes and 641 accepted-at-95 rows,
versus 527 for the old v3 model. Because the new model adds eligible `Impact`
and `Top Loop` classes and shifts many boundaries, this is not safe to swap
into production without a new candidate review and approval pass.

No rename plan was regenerated or applied. Remote GPU 1 was not contacted,
restarted, killed, or modified.

## Candidate-change review queue

The 1,071 changed predictions now have a deterministic review queue. It ranks
gate transitions first, then rejection boundaries, one-shot/loop boundaries,
low-frequency family boundaries, and exact/acoustic duplicate groups. The queue
is review-only: it creates no rename plan and cannot apply a rename.

- 1,071 changed rows were ranked.
- 8 are newly accepted at the 95% gate; none of the changed rows loses an old
  95% acceptance.
- 300 highest-priority rows have read-only physical waveform definition cards
  attached (300 cards, 0 analysis errors).
- The most frequent boundary is `Kick -> Bass Hit` (210 rows), followed by
  `Crash -> Impact` (52), `Chord Loop -> SFX` (42), and
  `Hi-Hat Loop -> Top Loop` (41). These are review priorities, not validated
  relabellings.

The first tranche deliberately concentrates on the places where a taxonomy
decision and a waveform decision can disagree. Human review should approve a
class only after checking the audio card and, where present, its duplicate
group; the research model remains separate until that review is complete.

## Receipts and tools

- Ground-truth builder: `SmartSampleManager/tools/classification_benchmark/build_ground_truth.py`
- Relabelled research corpus: `SmartSampleManager/tools/classification_benchmark/corpus_granularity_relabelled_v1.npz`
- Strict comparison: `SmartSampleManager/tools/classification_benchmark/results_granularity_label_effect_v1.json`
- Research model: `SmartSampleManager/tools/classification_benchmark/full_taxonomy_model_granularity_v1.npz`
- Candidate audit: `SmartSampleManager/tools/classification_benchmark/results_granularity_model_candidate_effect_v1.json`
- Change queue: `SmartSampleManager/tools/classification_benchmark/granularity_change_review_queue_v1.csv`
- Change queue receipt and waveform cards: `SmartSampleManager/tools/classification_benchmark/results_granularity_change_review_queue_v1.json` and `SmartSampleManager/tools/classification_benchmark/results_granularity_change_definition_cards_v1.json`
