# SLO breadth-label checkpoint: 311 usable labels

## Scope

This is a research-only checkpoint after the breadth-first labelling session.
The stable label audit recorded 315 completed decisions, four explicit skips,
and four `Misc/Review` rows; 311 rows were usable for corpus construction.

The corpus was built from `corpus_v4b_escape_recovered.npz` with the new human
labels overriding overlapping older labels. Four such corrections are listed
in the JSON receipt. Missing embeddings were extracted into a separate derived
cache and merged without touching source audio.

## Corpus and safety

| item | value |
|---|---:|
| output rows | 1,850 |
| appended human-labelled rows | 297 |
| overlapping human corrections | 4 |
| evaluated classes (minimum 5 examples) | 31 |
| vendors/collections | 81 |

Receipts:

- `tools/classification_benchmark/receipt_corpus_breadth_final_v1.json`
- `tools/classification_benchmark/results_breadth_final_vendor_eval_v1.json`

The receipt asserts research-only operation: source audio was not modified or
renamed, the production model and sealed validation were unchanged, and no
rename actions were emitted.

## Vendor-held-out result

Eight seeds and five grouped folds were used. The split unit was vendor/
collection, so files from a held-out collection never appeared in training.

| method | accuracy | macro-F1 | worst-vendor accuracy |
|---|---:|---:|---:|
| balanced logistic incumbent | 53.53% ± 0.80 | 40.32 | 13.32 |
| nearest centroid | **55.13% ± 0.61** | **43.53** | **18.65** |
| change | **+1.59pp** | **+3.21** | **+5.33** |

Nearest centroid is therefore retained as a research candidate, but it does
not clear the pre-registered +2pp promotion gate. No production classifier or
automatic-renaming policy changes from this result alone.

## Next decision

The next high-value work is taxonomy and policy review: inspect the 31-class
confusions and class-conditional precision on held-out collections, then decide
whether to merge/split incoherent labels before spending more labels. A further
generic model bake-off is not justified by this checkpoint.

## Taxonomy and policy audit

The current primary grouped set contains 28 classes (the three classes below
the five-collection minimum remain recorded but are not scored as promotion
evidence). The class-conditional 95%-precision audit found only **Clap, Kick,
and Snare** robust enough to be policy candidates with at least 20 accepted
items in every repeated seed. This is an audit result, not an approval: those
three still require explicit owner approval and a separate new-domain gate
before any automatic rename action.

The largest repeated confusion families are `Percussion Loop -> Hi-Hat Loop`,
`Percussion -> Kick/Hi-Hat`, `Foley -> Rimshot/Clap`, and `Snare -> Clap`.
These are evidence that the broad Percussion/Foley boundaries and loop/form
labels need taxonomy review; they are not a reason to lower confidence gates.

Detailed outputs:

- `tools/classification_benchmark/results_breadth_final_taxonomy_eval_v1.json`
- `tools/classification_benchmark/results_breadth_final_class_gates_v1.json`
- `tools/classification_benchmark/results_breadth_final_confusions_v1.json`

The current broad policy was also audited on this corpus: its audio-only
auto-action bucket was only 87.4% precise, so it is not a 95%-precision policy
on this harder domain. A conservative research candidate using only the three
class-conditional thresholds above achieved 95.77% minimum precision across
eight seeds (97.03% mean) at 7.31% mean coverage. This is promising for a
small, high-confidence rename tier, but remains audit-only until owner approval
and a genuinely new-domain qualification are completed.

Candidate-policy output:

- `tools/classification_benchmark/results_breadth_final_policy_audit_v1.json`
- `tools/classification_benchmark/results_breadth_final_candidate_policy_v1.json`

On the separate 120-file class-gate validation set (with 18 overlapping files
excluded from training), the same candidate policy accepted 105 files at
99.05% precision and 87.5% coverage. This is strong evidence for a narrowly
scoped first automatic tier, but it is still not an automatic approval: the
result covers only the validation queue's drum-heavy distribution and requires
an explicit owner decision before wiring it to rename execution.

New-domain output:

- `tools/classification_benchmark/results_breadth_final_new_domain_policy_v1.json`
- `tools/classification_benchmark/review_packet_breadth_candidate_policy_v1.json`

Finally, physical waveform cards were extracted for all 311 usable labelled
files. The measurable form signal is clear enough to guide taxonomy work:
loop labels have materially longer duration, higher onset density, and stronger
periodicity than the corresponding one-shot labels (for example Drum Loop and
Percussion Loop), while Hi-Hat one-shots are high-frequency and low in
low-band energy. These are evidence features for explanations and future
factorised heads, not semantic ground truth by themselves.

Physical audit output:

- `tools/classification_benchmark/results_breadth_final_physical_waveform_audit_v1.json`
