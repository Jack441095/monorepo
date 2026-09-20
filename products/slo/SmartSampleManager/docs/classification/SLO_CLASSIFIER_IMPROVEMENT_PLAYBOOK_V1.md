# SLO Classifier Improvement Playbook V1

**Status:** research and data-collection guidance; no production model change
**Product:** SLO
**Package:** `SLO-L05-CLASSIFIER-IMPROVEMENT-V1`
**Date:** 2026-09-01

## The simple mental model

SLO does not learn from a scan. A scan runs the current classifier and records
what it did. Improvement needs a closed loop:

```text
representative audio
  -> reviewed labels and provenance
  -> leakage-safe train/holdout split
  -> train or recalibrate one candidate
  -> compare against the frozen baseline
  -> independent review and owner decision
  -> only then consider a production change
```

Adding unlabelled audio, rescanning the same vendor, or changing a threshold
without a holdout can make the number look better without making SLO better.

## What the current evidence says

- The corrected cross-fitted known-set result is approximately 80.5% accuracy
  with macro F1 approximately 0.70. These are exploratory measurements, not a
  release claim, because the corpus labels are folder-derived rather than
  independently reviewed.
- Known rejection is material: approximately 32.3% at the default 0.75
  acceptance threshold in the corrected exploratory scorecard.
- The independent cross-vendor OOD fixture contains 168 judgment-based
  negatives. The direct native result is 121/168 false-known (72.0%). This is
  adverse evidence, not a reason to silently loosen the gate.
- The acoustic ML head currently covers 16 classes while the product taxonomy
  has 17. `Atmosphere` is heuristic-only until it has a real trained,
  leakage-controlled and reviewed dataset.
- `Vocal Loop` is explicitly claim-suppressed after its cross-vendor recall
  failed to generalise. It needs its own label and naming-convention work.

## The data packet to collect

For each clip, retain a manifest row rather than copying private audio into
product Git. The row should contain:

| Field | Requirement |
| --- | --- |
| `source_path` and `source_sha256` | Exact source identity; audio remains outside product Git |
| `vendor_id`, `pack_id`, `source_family` | Provenance and leakage boundary |
| `expected_subcategory` | One frozen SLO class, or `OOD` |
| `label_authority` | Folder mapping, vendor metadata, or independent review |
| `reviewer_id` / `review_status` | Required before qualification; disagreement is retained |
| `ambiguity_reason` | Required when the correct result is abstain/unknown |
| `audio_format` / `duration` | Coverage and unsupported-input analysis |

Prioritise clips from the observed failure slices:

1. OOD that resembles `Percussion`, `Foley`, `FX`, `Riser`, `Music Loop`, or
   `Vocal Phrase`.
2. Genuine known examples currently rejected as unknown, especially `Foley`,
   `Atmosphere`, `Bass One-Shot`, and `Percussion`.
3. `Vocal Loop` examples from several vendors whose naming conventions differ.
4. A balanced `Atmosphere` set if Atmosphere is intended to become an ML
   class; otherwise keep it explicitly heuristic and do not count it as ML
   accuracy.
5. Clean OOD from more than two unrelated sources, including non-musical
   recordings, guitar/instruments with no taxonomy slot, speech, and other
   plausible near-neighbours. Each OOD family must be reviewed so legitimate
   `Vocal Phrase` material is not mislabeled as OOD.

The useful target is coverage across vendors and source families, not a magic
file count. As a planning starting point, collect at least 100 reviewed clips
per weak known class across three or more unrelated vendors/packs, then expand
the class until the holdout confidence interval is useful. Do not treat this
starting target as a qualification threshold.

## How the improvement run works

1. Freeze the current baseline: source SHA, runtime head, thresholds, manifest
   hash, and current scorecard.
2. Remove duplicates and keep source families intact when splitting. A vendor
   or pack that appears in training must not be the only evidence for its
   holdout result.
3. Have two reviewers label the evaluation subset independently. Resolve
   disagreements in a recorded adjudication file; never edit labels silently.
4. Train or recalibrate one candidate at a time. Keep the production head and
   OOD gate unchanged while measuring candidates.
5. Report known accuracy, macro/per-class F1, false-unknown rate, confidence
   calibration, OOD false-known rate, OOD rejection, abstention, and the
   confusion matrix. Report results by vendor/source family as well as overall.
6. Compare every candidate to the frozen baseline on the same holdout. A
   candidate that improves average accuracy but harms a weak class, unseen
   vendor, or OOD safety is not an automatic win.
7. Only after the evidence passes independent review may an owner approve a
   new model version, thresholds, or taxonomy change. That approval must be
   bound to the exact manifest, source SHA, and receipt.

## What is already implemented

- Runtime rejects invalid embeddings before classification and downstream
  indexing/similarity use.
- Cache entries version the acoustic classifier head separately, so a future
  head change can refresh the label while preserving the compatible embedding.
- The research runner enforces frozen taxonomy coverage, source-family group
  splits, path-identified cache matching, complete manifest coverage, and
  current 512-dimensional finite embeddings.
- `tools/classification_benchmark/preflight_research_inputs.py` checks those
  contracts before model fitting and reports declared-manifest deficits
  separately from cache coverage. Its SHA-256 identity fallback handles
  fixture-relative paths without weakening ambiguity checks.
- `tools/classification_benchmark/build_ground_truth_research_manifest.py`
  assembles a candidate manifest from reviewed ground-truth labels while
  excluding unmapped fine-grained labels and preserving explicit rejection/OOD
  rows. It is a data-packet builder, not a qualification or promotion step.
- A research-only Energy OOD score is instrumented beside MSP, entropy, and
  margin. It has not been promoted to production and must not be described as
  an improvement until a complete, reviewed run exists.
- `tools/classification_benchmark/build_l05_review_packet.py` turns the
  existing known-error queue and OOD error database into a review packet. It
  writes a label-free reviewer view, a separate provenance/key view, and a
  blank results template. It refuses ambiguous identities and existing output
  files, and it never copies or modifies audio.
- `tools/classification_benchmark/apply_l05_review_results.py` validates the
  completed template: two named reviewer labels, explicit UNKNOWN/OOD reasons,
  disagreement adjudication, and source-SHA/path identity. It emits separate
  reviewed annotations and an intake receipt marked `NOT_QUALIFIED`; it never
  rewrites the source manifest or promotes training data.

## How to use the review packet

Run this against a generated research output directory, writing to a new
disposable or owner-approved review directory:

```bash
python3 tools/classification_benchmark/build_l05_review_packet.py \
  --manifest tools/classification_benchmark/dataset_manifest.json \
  --owner-review-queue tools/classification_benchmark/owner_review_queue.csv \
  --error-database tools/classification_benchmark/error_database.csv \
  --output-dir /path/to/new/slo-l05-review-packet
```

Give reviewers `blind_review_packet.csv` and retain
`review_packet_key.csv` with the adjudicator. Reviewers fill
`review_results_template.csv` with one or two independent labels per row,
including `UNKNOWN` where the clip has no defensible taxonomy class. Do not
replace `expected_subcategory` in the key or manifest by hand. Record the
reviewer IDs, disagreements, adjudication, rights/owner authorisation, and
the final receipt separately. After review, validate the completed template
with `apply_l05_review_results.py`; its output is still annotation evidence,
not a training set or release qualification. The packet is an
evidence-collection aid; it does not train the model or qualify a release by
itself.

## Current decision and next action

Do not change production weights, centroids, thresholds, or taxonomy from the
current exploratory evidence. The next engineering action is to obtain the
reviewed data packet above, complete the full-corpus scorecard, and run one
candidate comparison. The current external scan is disposable and paused at
21,432 rows; it is not a qualification receipt. The review-packet builder has
been verified against the current candidate output: it resolved 213 unique
candidates (50 known-set queue rows and 163 OOD failures) without touching
audio. This count is a property of that evidence snapshot, not a required
dataset size.

## Exit criteria

This playbook is complete only when a future package has:

- an independently reviewed, rights-authorised manifest;
- explicit known/OOD and vendor/source-family holdouts;
- all intended ML classes represented and reviewed;
- before/after metrics for the frozen baseline and candidate;
- per-class, unseen-vendor, and OOD results;
- source SHA, manifest hash, environment, and reproducible commands;
- an explicit owner decision; and
- a rollback path for any promoted runtime change.

Until those conditions exist, SLO remains honest and safe by retaining the
current classifier while exposing uncertainty/Unknown where the evidence is
weak.
