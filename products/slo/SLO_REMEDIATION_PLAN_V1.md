# SLO remediation plan

**Date:** 2026-09-14  
**Status:** execution plan; current product remains review-only

## Outcome

Move SLO from an engineering-complete internal prototype to a defensible
private beta, while improving the classifier without pretending that every
audio file has one objectively correct name. The safe contract is:

`evidence -> suggestion -> explicit approval -> narrowly gated action`

Unknown, mixed, novel, or out-of-ontology audio must remain searchable and
explainable, but must not be forced into a rename class.

## Priority order

### 0. Freeze the current baseline

Do this before any model or policy change:

- preserve the current receipts, manifests, packet hashes, model versions and
  taxonomy version;
- run the existing native qualification cache and Python suite;
- keep the current policy in `review-only` and do not promote the 120-row
  recalibration result;
- record the current honest baseline: 62.9% full-evidence / 30.2% audio-only
  on the 620-file cross-vendor report, plus the 225-row fused review result.

**Exit gate:** clean test receipt, `git diff --check`, and a reproducible
readiness snapshot with no automatic actions enabled.

### 1. Unblock release-critical owner work (P0)

These are not engineering tasks that can be safely guessed around:

1. Apple Developer ID enrollment, signing identity, notarization credentials.
2. Production licensing endpoint and real credentials over HTTPS.
3. A clean physical/VM Mac for install, launch, upgrade, uninstall and data
   preservation checks.

Engineering prepares scripts and manifests; the owner supplies credentials and
the machine. No release claim is made until all three have receipts.

**Exit gate:** signed/notarized artifact, installer manifest, clean-machine
acceptance receipt, and a production licensing smoke receipt with secrets
excluded from logs.

### 2. Finish the safety/host validation lane (P1)

- Run the Ableton Live VST3 matrix: scan, load, state restore, audio render,
  drag-out, reopen, cancellation and rescan.
- Complete the protected AL-002 blind review through the approved owner path;
  do not recreate or infer its labels.
- Keep sort operations previewable, journalled, cancellable and undoable;
  retain the existing copy/move tests as release gates.

**Exit gate:** host matrix and blind-review receipts, with every failed case
either fixed and retested or explicitly listed as a release limitation.

### 3. Calibrate the action boundary (highest-leverage classifier work)

1. Collect owner decisions for the 72 path-disjoint rows in
   `class_conditional_gate_validation_manifest_v2.json`.
2. Merge only verified, hash-bound labels; keep out-of-scope labels in the
   denominator rather than silently dropping them.
3. Add a larger sealed holdout spanning more vendors, collections and classes.
4. Fit class/domain thresholds with collection-held-out folds and report
   Wilson lower bounds, coverage, false-known OOD and boundary-pair errors.
5. Reopen the spec-frozen OOD threshold only with explicit owner approval.

The 120-row result is a research audit, not production policy: it has only
three candidate classes and is too small to support a universal auto tier.

**Exit gate for Suggest:** calibrated class/domain precision and useful
coverage on unseen collections.  
**Exit gate for Auto:** one-sided 95% precision lower bound at or above the
agreed product promise (initial proposal: 99.5%), hard OOD/rejection gate,
zero unresolved collisions, and a rollback receipt.

### 4. Close the known accuracy gaps

- Expand Vocal Loop evaluation beyond the current narrow 2/2 tempo-marker
  slice; include cross-vendor names, renamed files and acoustic-only cases.
- Measure and reduce cross-vendor false-known OOD; compare the existing
  embedding novelty signal with a logit-energy/rejection signal in the full
  end-to-end path before choosing a replacement.
- Improve temporal aggregation only if it beats the frozen file-level baseline
  on a sealed, collection-held-out test; current windows are localization
  evidence, not an accuracy win.
- Do not run more generic encoder bakeoffs unless a pre-registered +2-point
  improvement and rejection/class gates are defined first.

**Exit gate:** a new receipt reports audio-only, filename-only, fused,
collection-held-out and vendor-held-out results separately, with confidence
intervals and no leakage.

### 5. Add producer-facing breadth selectively (P2)

Choose the first two or three subtypes with the highest beta value, then build
each as an independent, evidence-gated head. Recommended order:

1. acoustic snare vs rimshot;
2. kick length (short/medium/long);
3. clean vs saturated/distorted low-end (after the THD DSP research pass).

Every new head needs a definition card, leakage-free labels, collection-held-
out validation, confidence bands and an explicit `unknown` outcome. Do not
expand the flat taxonomy merely to increase class count.

The low-end-heavy physical descriptor has now been audited for redundancy but
is intentionally not shipped: 709/1,850 rows cross a 0.60 low-band threshold,
and only 46.7% of those also fall in the existing Dark band. This confirms it
is not merely a duplicate display of Bright/Dark, but it does not establish
which sounds a producer would call “low-end heavy”; that still needs owner
labels.

**Exit gate:** each shipped tag has a report, minimum sample count, lower-bound
precision and a review-only fallback when evidence is thin.

### 6. Product polish after the gates are stable

Prioritize workflow value after safety and calibration are no longer moving:

- prominent per-row Find Similar action;
- external drag-out into a DAW;
- waveform scrubbing and pitch audition;
- custom naming templates and folder exclusions;
- universal macOS binary and repeatable installer pipeline.

These features must consume the same structured evidence and approval state;
they must not create a second, less-safe rename path.

## Operating rules

- Keep all imported AI evidence read-only and hash-bound.
- Treat captions, retrieval, clusters and filename tokens as evidence, never as
  ground truth.
- Preserve every rejection/unknown state and every human correction as an
  auditable event.
- Any policy change gets a new receipt, version and rollback path.
- If a gate fails, downgrade to review-only; never widen action by intuition.

## Immediate next action

### Naming and tempo correction — 2026-09-14

Producer naming now treats a tonal one-shot as a single note: a stored key
such as `B Major` is rendered as `B` for one-shot names, while loop names keep
the full mode (`BMajor` in the compact suffix format). The stored key value is
not altered, so search/filter metadata remains backwards-compatible.

Tempo is now form-gated. BPM is retained for loop subcategories only; a
one-shot, FX, atmosphere, or other non-loop sample is assigned no BPM in the
runtime naming/metadata path. This also clears legacy cached 120-BPM fallback
values in memory and prevents a stale value from appearing in a rename
preview. The acoustic estimator remains available for files with at least two
seconds of real content, but low-confidence results stay at unknown rather
than being replaced by 120. Its candidate selection now uses a stable onset
spacing prior to reject half/double-time harmonics; a synthetic 120-BPM click
loop is recovered as 120 BPM rather than 60 BPM.

Regression coverage is in `Source/test_audio_features_main.cpp`; the arm64
`TestAudioFeatures` binary passes the one-shot key, loop-key, and non-loop
tempo naming checks.

A 40-file production-path audit over copied samples from the real sample-pack
corpus is recorded at
`products/slo/_artifacts/slo_tempo_real_corpus_audit_v1.json`. It contains 40
scanned rows, zero exact-120 BPM values, and zero non-loop rows with a nonzero
BPM after the final acoustic gate. Twenty-seven rows correctly remain
tempo-unknown; the remaining BPM values are attached to loop-labelled rows.
This is a behavior/safety audit, not a claim of universal tempo accuracy.

The estimator now also uses a multi-band onset envelope (broadband,
low-frequency pulse and air-band cues). This protects kick/bass periodicity
from being overwhelmed by regular hi-hat subdivisions. Native fixtures cover
layered 90, 120 and 174 BPM material; the updated production-path rescan is
recorded at `products/slo/_artifacts/slo_tempo_real_corpus_audit_v2.json`
(40 rows, zero exact-120 BPM values and zero non-loop BPM leaks). The
notated-versus-felt half-time ambiguity remains an explicit reason to abstain
or require metadata rather than silently claim certainty.

The production parser now recognizes the common loop-plus-key convention
(`Loop_110_Fm`, `Loop_01_160_C#`) when no literal `BPM` marker is present. It
requires both an explicit loop token and a nearby key token, so bare variation
numbers remain unknown. Long files also receive a separate tempo view of up
to 20 seconds, fused with the 5-second view: only agreement within 2 BPM is
accepted acoustically. This improves evidence quality without changing the
5-second embedding contract. The updated 40-row receipt is
`products/slo/_artifacts/slo_tempo_real_corpus_audit_v4.json`; its single 120
BPM row is an explicit `Loop_..._120_A#` filename value, not a fallback.

The next executable step is owner review of the strict filename/folder-blind
72-row bundle at
`products/slo/_artifacts/slo_strict_blind_class_gate_v2/review_queue.csv`.
Its evaluator-only mapping is kept separately under the bundle's `evaluator/`
directory. The original candidate manifest remains the evaluator-side source
of truth; the reviewer CSV contains no candidate class/confidence/similarity,
no original path, and blank human-label fields. Embedded audio metadata is not
stripped, so this is filename/folder-blind rather than a cryptographic or
metadata-scrubbed blind test.

Once the CSV is completed, run
`tools/classification_benchmark/import_strict_blind_class_gate_labels.py`.
It verifies staged and source hashes, restores evaluator paths, rejects
incomplete labels by default, and emits the existing evaluator-compatible
`id,label,path,note` schema. A pending-label smoke import currently produces
zero usable labels, as expected.
While that is pending, engineering should prepare the sealed-holdout schema
and the end-to-end OOD logit-energy experiment, without changing production
thresholds or rename behavior. A read-only preflight is now available at
`tools/classification_benchmark/preflight_research_inputs.py`; it reports
cache/schema/identity coverage and metadata deficits before model fitting.
The verified ground-truth cache now matches **795/795** manifest rows (731
known, 64 explicit OOD) with zero embedding or hash failures. The energy
experiment remains correctly blocked by the metadata gate: five frozen-head
classes are absent, Atmosphere/Bass Loop have thin family support, and three
source families carry mixed labels. These must be resolved in the sealed data
packet; they cannot be repaired by threshold tuning.

A refreshed coverage plan at
`products/slo/_artifacts/slo_taxonomy_gap_coverage_plan_merged_v2_20260914.json`
confirms that the current 624-row owner queue is sufficient in principle: all
five missing classes have a feasible assignment of the required five new source
families, and the thin Atmosphere/Bass Loop gaps are also coverable. This is a
planning result only—**0/624 owner decisions are complete**, so no labels have
been promoted and the research gate remains closed.

The native acoustic head now records a finite research-only logit-energy
diagnostic (`-logsumexp` of its scaled logits) alongside margin, entropy, and
centroid similarity. It is intentionally not wired into the production OOD
decision; the sealed metadata gate and a collection-held-out calibration run
must precede any threshold change.

For practical review, an exclusion-aware third master batch is available at
`products/slo/_artifacts/slo_taxonomy_gap_review_batch_master_03_20260914.csv`.
It contains 120 previously unissued rows across 37 collections (0 owner labels
changed); its receipt records zero content-hash overlap with master batches 01
and 02. This reduces the remaining queue to 384 unissued rows without weakening
the approval gate.

The existing research runner already contains a numerically stable
`-T*logsumexp(logits/T)` implementation. Its manifest join now also supports a
declared SHA-256 identity fallback when the native cache uses an absolute path
but the manifest uses a fixture-relative or privacy-preserving path; duplicate
hashes remain a hard error. A current receipt still cannot be claimed: the
default fixture cache contains only 38 rows and does not cover the 1,607-row
research manifest, so the runner correctly fails closed on manifest/cache
coverage. The experiment must use a paired, leakage-controlled known/OOD
manifest and matching cache before its result is used in a gate decision.

Engineering has now assembled a **795-row reviewed-label candidate manifest**
from `ground_truth/SLO_GT_V1/labels.csv` at
`_artifacts/slo_ground_truth_research_manifest_v1.json`. It preserves exact
frozen-head labels, records explicitly reviewed `Other/none` rows as OOD, and
excludes fine-grained labels that cannot be mapped honestly. Its preflight
receipt shows the remaining truth clearly: 731 known / 64 OOD rows with broad
collection diversity, but five frozen classes still absent (Bass One-Shot, FX,
Music Loop, Synth and Vocal Phrase), thin support for Atmosphere/Bass Loop,
and three mixed source families. This is a valid data-collection starting
point, not a qualification scorecard.

That manifest now has a matching disposable research cache at
`_artifacts/slo_ground_truth_research_cache_v1.sqlite3`: all **795/795** rows
pass embedding-shape, path and SHA-256 checks (731 known, 64 OOD). The runner
was exercised against it and stopped at the intended metadata gate before
fitting or writing a scorecard. This confirms the cache/manifest plumbing is
fixed; the remaining work is genuinely label/taxonomy coverage, not an input
join failure.

To close the remaining class gaps without inventing crosswalks, engineering
also generated a **487-row taxonomy-gap adjudication queue** at
`_artifacts/slo_taxonomy_gap_adjudication_queue_v1.csv`. It covers the
fine-grained reviewed labels currently excluded from the frozen head (for
example Synth One-Shot, SFX, Vocal One-Shot, Bass Hit/Reese and loop variants).
Each row offers candidate parent options, but the owner label, note and
reviewer fields are blank and the receipt explicitly marks the queue as
pending. Once adjudicated, only those owner decisions can be merged into a
new manifest version.

The corresponding importer is
`tools/classification_benchmark/import_taxonomy_gap_adjudication.py`. It
requires an explicit owner label/status/reviewer/note, accepts only an offered
option (or UNKNOWN/OOD), rechecks the source SHA-256, and emits a new manifest
with `OWNER_ADJUDICATION` provenance. A pending smoke import skipped all 487
rows, confirming that an incomplete queue cannot silently become training or
qualification data.

After decisions are imported, merge them with the existing research packet via
`tools/classification_benchmark/merge_taxonomy_gap_adjudication_manifest.py`.
The merger assigns fresh IDs, rechecks source hashes, blocks duplicate-content
aliases, and emits a separate receipt; the pending smoke path currently merges
zero new rows and leaves the 795-row packet unchanged.

Batch 01 is a deterministic 120-row review slice at
`_artifacts/slo_taxonomy_gap_review_batch_01_v1.csv`. It contains at least one
row from each of the 13 candidate option groups, so the first review pass has
broad taxonomy coverage. No owner decisions have been imported yet; the
production taxonomy and policy are unchanged.

The prospective family-coverage report is
`_artifacts/slo_taxonomy_gap_coverage_plan_v1.json`. It shows that the queue
contains enough distinct candidate families to clear every current class-family
deficit under a jointly feasible one-row/one-label assignment; this is a
capacity check, not a label assignment or a qualification result.

The same process was run over five existing by-ear review CSVs. The resulting
supplemental queue is
`_artifacts/slo_taxonomy_gap_adjudication_queue_supplement_v1.csv` (387 unique
candidate rows). It adds 392 previously unseen content candidates after
deduplication; five contradictory duplicate-content hashes were blocked rather
than resolved automatically. Its matching coverage plan is
`_artifacts/slo_taxonomy_gap_coverage_plan_supplement_v1.json` and is also
jointly feasible. These observations remain candidates until an owner confirms
the frozen-head parent class.

Supplement batch 02 is available at
`_artifacts/slo_taxonomy_gap_review_batch_02_supplement_v1.csv` (120 rows,
12 represented option groups, 62 collections). It is independent of batch 01
and can be reviewed in the same localhost UI; its receipt records the source
queue hash and deterministic selection.

For a single canonical handoff, the two queues are also consolidated at
`_artifacts/slo_taxonomy_gap_adjudication_queue_merged_v1.csv`: 874 input rows
become 624 unique content hashes, with 250 aliases collapsed and no conflicts.
The recommended master batch is
`_artifacts/slo_taxonomy_gap_review_batch_master_01_v1.csv` (120 rows, all 13
option groups). Its merged-queue coverage plan remains jointly feasible.
The full merged queue also has an exclusion-aware batch selector; master batch
02 at `_artifacts/slo_taxonomy_gap_review_batch_master_02_v1.csv` contains 120
new content hashes with no overlap with batch 01.

The full merged queue has an option-filtered CLAP advisory receipt at
`_artifacts/slo_taxonomy_gap_clap_option_filtered_merged_v1.json` (624/624
rows joined, 610 advisory candidates). Suggestions are uncalibrated evidence
only and remain behind the owner-review gate.

To review it in the local audio UI, run
`tools/classification_benchmark/taxonomy_gap_review_tool.py` with the batch CSV,
an output CSV, and a reviewer ID. The UI is localhost-only, plays the source
audio read-only, restricts each row to its offered options plus OOD, and
requires a written note. The master batch also has a separate CLAP advisory
receipt at `_artifacts/slo_taxonomy_gap_clap_option_filtered_master_01_v1.json`;
pass it with `--evidence` to display only option-filtered, explicitly
non-binding suggestions. The filter receipt is hash-joined, atomic, and refuses
to alias its queue or source receipt. For a partially completed batch, import with
`--allow-incomplete`; pending rows are skipped and completed rows are still
hash-verified. The reviewer also fails closed on malformed resume rows instead
of silently treating them as complete. Then merge the resulting decision
manifest with the base packet using the duplicate-safe merger described above.
The CLI refuses an output path equal to the source queue, enforcing the
non-destructive review contract.

The current 795-row manifest/cache preflight was rerun on 2026-09-14 and is
recorded at `_artifacts/research_input_preflight_v2_20260914.json`. Identity
and embedding coverage are now complete (795/795, with zero cache failures),
but the research runner remains correctly blocked by metadata: five frozen
classes are absent, Atmosphere and Bass Loop are thin, and three source
families carry mixed labels. No model, threshold, or production policy was
changed by this run.
