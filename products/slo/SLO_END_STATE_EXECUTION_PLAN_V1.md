# SLO end-state execution plan — high-end audio classification and safe auto-renaming

Date: 2026-09-11

## End state

SLO should turn an unseen audio library into a reviewable, reversible rename
plan. It must use both filename evidence and physical audio evidence, know when
the taxonomy does not fit, and refuse to act when confidence or domain support
is insufficient.

The product is not "a classifier that always names a file". The product is a
calibrated decision system with four outcomes:

1. auto-rename only when the class and domain gate are passed;
2. suggest a name when evidence is useful but not safe enough;
3. reject/leave unchanged when the sound is outside the supported taxonomy;
4. request a human label when the filename and waveform disagree.

## Current measured position

- Collection-held-out v3 full-taxonomy accuracy: 57.01%; macro-F1: 49.37%.
- v3 model: 25 eligible classes, 1,325 rows, 79 collections, frozen centroid
  inference. It remains the review incumbent.
- The v4 supplement has 1,510 rows and 27 eligible classes. Its flat model
  scores 56.49% accuracy / 47.55 macro-F1: more labels, but no promotion.
- The escape-recovered v4b corpus has 1,553 rows and 27 eligible classes. It
  scores 55.71% accuracy / 47.73 macro-F1 and coverage@95 of 13.4%; retain the
  labels, but keep v3 as the model incumbent.
- The first hard family-to-class cascade scored 45.59% / 37.54 macro-F1 across
  eight grouped seeds and is closed. A future factorised model must be soft-
  gated or multi-task; a lossy family bottleneck is not acceptable.
- Multi-window encoder views are also closed on current evidence: the best
  six-view fusion reached 69.10% versus 69.51% for the early-window control;
  attack, tail, and spread views degraded their targeted classes. The DSP
  multi-window arm only moved coverage@90 from 44.4% to 45.6% while lowering
  accuracy, so it is not a rename-policy improvement.
- A soft family/form prototype scorer improved v3 by only 0.44pp and v4b by
  0.54pp, both below the +2pp promotion gate. Factorised fields remain useful
  for explanation and future multi-task training, not as a replacement model.
- Multiple prototypes per exact class made the incumbent worse: k=2 was
  -1.48pp and k=3 was -2.33pp on v3. Negative-silhouette classes need taxonomy
  repair and breadth, not more centroid variants.
- Testing library audit: 7,315 files, 2,048-D embeddings, zero extraction errors.
- The v3 model accepts 527/7,315 at its calibrated 95% gate; all remain
  review-only because no class has yet passed the new-domain auto gate.
- The v3 name/audio policy emits 386 class-qualified suggestions (Crash,
  Percussion Loop, Hi-Hat Loop, Bass Loop); none is auto-approved.
- The granularity/escape-hatch integration now provides 1,282 canonical human
  labels across 80 collections. It applied 61 explicit `Other/none` ->
  supported-class corrections, with 22 taxonomy-gap rows held and 71 rows
  dropped as unrecoverable. The fixed-row, same-fold vendor-held-out result
  improved by **+2.25pp (8/8 seeds)** without changing embeddings.
- A separate 27-class model frozen from those corrected labels scores 57.99%
  OOF accuracy / 49.39 macro-F1 and is research-only. On the 7,315-file
  testing cache it changes 1,071 predictions, so it must not replace v3 until
  the changed rows have a review receipt and a new approval gate.
- An independent v4b OOF audit of 221 eligible new-label rows across 36
  collections gives 53.79% audio accuracy, 56.96% filename/audio accuracy,
  and 73.71% trusted-name override precision. No class is currently qualified
  for automatic action on this harder population.
- A new pair-boundary queue now contains 400 files across 177 explicit
  audio-vs-filename class pairs and 23 collections. It is the next labelling
  queue; it supersedes token-frequency selection for boundary work.
- The queue is now enriched with physical-waveform explanations (transient,
  decay, sub energy, pitch glide, beating, harmonicity, and stereo cues) for
  394/400 files; six explicitly report unreadable waveform evidence. The
  enriched labeller is available on local port 8754, and the same evidence is
  exported in `full_taxonomy_pair_boundary_queue_v2.csv` for audit/review.
- 3,580/7,315 disagree with the old drum-centric audio classifier.
- The existing testing-library rename plan contains 3,245 auto candidates,
  4,070 suggestions, 4,310 never-act rows, and 16,705 review rows. None has
  been applied.
- Occupied remote GPU 1 is out of scope. Do not restart, reboot, kill, or
  disturb the remote host or its running service.

## Phase 0 — protect and repair the ground truth

- Keep verified labels backed up in at least two locations and record a checksum.
- The fixed `Not in list`/`Taxonomy gap` note prompt has been applied to the 51
  recovery rows; never silently convert the remainder into training labels.
  This pass recovered 9 labels and normalized 278 usable rows; 22 remain held
  for owner decisions and 71 remain intentionally dropped. The resulting
  ground truth is archived and checksum-verified.
- Preserve a permanently sealed collection-held-out evaluation set.
- Deduplicate by content hash before every split and ensure no collection leaks
  between train, calibration, and test.
- Track label provenance: human-by-ear, filename hint, model suggestion, and
  correction. Only human-by-ear labels may enter the gold evaluation set.

## Phase 1 — finish the taxonomy before chasing models

Use a factorised schema rather than an ever-growing flat list. Do not use a
hard family cascade: the first such cascade scored 45.59% and is closed. Any
replacement must be soft-gated or multi-task and must beat the flat incumbent.

The future environmental/animal branch is specified separately in
`SLO_REAL_WORLD_TAXONOMY_SCAFFOLD_V1.md` and
`SmartSampleManager/tools/classification_benchmark/real_world_taxonomy_v1.json`.
It is deliberately dormant: no external taxonomy is imported into production,
and no real-world class may enter the rename policy before it has human labels,
collection-held-out evaluation, and an explicit owner decision.

- family: kick, snare, hat, bass, synth, vocal, foley, impact, percussion,
  ambience, etc.;
- form: one-shot, loop, fill, sustained, texture, atmosphere;
- modifiers: acoustic/electronic, pitched/noise, dry/processed, tonal/noisy;
- role: primary sound, layer, transition, utility, unknown;
- rejection facts: `other/none`, `not_in_list`, `not_enough_info`, `taxonomy_gap`.

Split or retire classes with negative silhouette or persistent confusion:
Percussion, Foley, Percussion Loop, Bass Hit, SFX, and Synth Loop. Use the
evidence-backed percussion subtypes, and do not invent labels for Sub Bass or
Atmosphere until a breadth-first sample proves they are present.

The 22 held taxonomy-gap rows now have a read-only owner packet with physical
definition cards and preserved notes. They remain outside training and rename
policy until an explicit taxonomy decision is made.

## Phase 2 — label by domain breadth

- Continue breadth-first collection coverage; an unseen collection is worth more
  than another near-duplicate from a familiar pack.
- For every batch, reserve a collection-held-out test slice before training.
- Select boundary queues by model disagreement between two named classes, not by
  filename token abundance.
- Add the 527 full-taxonomy high-confidence files to a human validation queue,
  plus a matched sample of low-confidence and disagreement files.
- Measure per-class precision, rejection precision, and coverage at 85/90/95%
  precision. Do not promote a class from review to auto-action on aggregate
  accuracy alone.

## Phase 3 — build the evidence stack

Keep the current Perch+CLAP embedding baseline, but add evidence in layers:

1. multi-window audio embeddings (attack, sustain, and full clip);
2. explicit waveform/acoustic features for explanation: onset, duration,
   pitch, spectral centroid/rolloff, transientness, periodicity, loudness,
   zero-crossing rate, and low/high-band energy;
3. filename evidence with a versioned token risk table and collection-aware
   ambiguity handling;
4. a factorised head or calibrated nearest-centroid model per field;
5. a fusion policy that can abstain when name and audio disagree.

The read-only implementation of the physical description layer is
`SmartSampleManager/tools/classification_benchmark/audio_definition_card.py`.
It emits a versioned definition card (including form, pitch, periodicity,
spectral, envelope, clipping, and stereo evidence) but deliberately does not
emit a semantic class or rename action. The card is an evidence input for later
calibration, not a substitute for human labels.

The physical-feature fusion arm has now been measured on the corrected corpus:
22 card measurements fused with the embedding at weights 0.25, 0.5, and 1.0
changed accuracy by only +0.01, 0.00, and +0.03pp respectively under eight
seeds of five vendor-held-out folds. This is below the +2pp gate, so physical
features remain an explanation/review layer rather than a promoted classifier
arm. Receipt: `SmartSampleManager/docs/classification/SLO_PHYSICAL_FEATURE_FUSION_V1.md`.

The companion `aspect_similarity.py` tool compares two cards by spectrum,
timbre, pitch, amplitude, temporal structure, and spatial character. It is a
search/explanation aid modelled on aspect-weighted sample browsers; its scores
are not probabilities and require human similarity calibration before they can
influence a product decision.

The read-only `query_by_example.py` tool now provides the first product-facing
search primitive: a query file is matched against the cached 7,315-file
embedding index, with the top results optionally enriched by definition cards
and aspect-specific similarity. It is deliberately a similarity browser, not
a classifier: it excludes the query from its own results, reports the index
and method versions, and never creates labels, rename actions, or mutations.
The sample receipt is `results_query_by_example_sample_v1.json`.

The read-only `canonical_duplicate_groups.py` tool now resolves exact byte
identity before any acoustic similarity or rename decision. On the testing
library it found 235 exact duplicate groups and 335 alias paths across 7,315
indexed files. Each group keeps a deterministic canonical path and all aliases;
the receipt is review-only and explicitly cannot be interpreted as a delete,
move, or rename instruction.

The read-only `build_review_collections.py` tool now materializes the current
plan as explicit product queues. The testing-library receipt contains 386
suggestions, 6,890 review rows, 39 never-act rows, and zero auto-renames; all
386 suggestions join to their physical evidence packets. The queues preserve
the original decision, model provenance, approval state, and evidence facets.

The append-only `review_feedback_events.py` ledger now gives those queues a
safe feedback contract. `not_in_list` requires a note, corrections require a
replacement class, duplicate decisions require a distinct canonical path, and
every event remains `promoted_to_gold: false` until a later explicit curation
step. This repairs the earlier escape-hatch failure mode without inventing
labels.

The read-only `filter_definition_cards.py` tool exposes structured evidence
facets over either definition-card caches or review collections. Numeric
filters fail closed on missing values; a sample suggestion query over the
7,315-file review collection matched 345 transient-dense rows under 12 seconds.

The read-only `context_preview_plan.py` tool now calculates reversible tempo
preview parameters from the stored BPM evidence. A 100-row suggestion sample
planned target-128-BPM transforms with no source changes; key alignment remains
unavailable rather than being guessed from median pitch. Actual rendering is a
separate opt-in step and is not part of rename or classification policy.

The read-only `build_similarity_space.py` tool now exports a deterministic 2-D
PCA map for all 7,315 testing embeddings (2,048 dimensions). The first two
components explain 13.28% and 7.42% of variance. The map is an exploration
surface only: it does not assign clusters, labels, or rename actions.

The read-only `describe_sound_query.py` tool now provides controlled local
natural-language discovery. In a real query for "dark transient percussion
loop spaceship", it resolved the first four terms against existing evidence
and returned 28 rows while preserving `spaceship` as unsupported. Text cannot
create a class, override waveform evidence, or trigger a rename.

The read-only `near_duplicate_candidates.py` tool now adds an acoustic review
layer after exact hashing. At a conservative cosine threshold of 0.995 it
found 213 candidate groups covering 510 files in the testing cache; the largest
group has 16 members. These are similarity cues only, never proof of byte
identity and never deletion or rename instructions.

The independent `audit_rename_duplicate_guard.py` preflight now joins both
inventories to the 7,315-row rename plan. It flags 235 exact canonical paths,
335 exact aliases, and 510 acoustic candidates; there are no auto rows in the
current plan and no plan mutation. This guard must run immediately before any
future approval workflow.

The localhost-only `review_workspace_server.py` now exposes the derived review
collections, controlled sound-description search, and typed feedback endpoint
through a small browser/API surface. A live smoke test returned 200 from
health, summary, collection, and search endpoints; it serves no source audio
and writes feedback only to the explicit append-only ledger path.

The same workspace can now optionally load the class-conditional gate review
receipt through `/api/class-gate`, with class filtering and an explicit
review-only safety response. It does not expose an apply or auto-approval
operation.

The workspace also supports the fused class-gate packet through
`/api/class-gate-fusion`, with class and fusion-state filters. This keeps the
385 audio/name agreements, 3 conflicts, 18 audio-only rows, and 2
family/risk-only rows in a first-class review queue while preserving the same
no-audio-serving, no-label, no-rename safety contract.

The same workspace now exposes `/api/approval-gate`, including the separate
duplicate-blocked and duplicate-unflagged suggestion counts. This is a review
filter only; it does not grant approval or expose an apply operation.
It also supports `exclude_reason` so reviewers can inspect the 356
duplicate-unflagged suggestions without losing their unapproved status.

The workspace can now load the content-addressed embedding index, duplicate
guard, and approval-gate receipts together. In the integrated smoke test the
summary reported 6,980 content IDs, 335 aliases, 772 flagged plan paths, and
386 blocked suggestions; returned items carried identity, guard, and gate
status fields.

With the embeddings cache supplied, `/api/similar` now exposes the same
content-aware query-by-example search through the workspace. A live exact-copy
query returned 17 neighbours, excluded every alias of the query, and returned
HTTP 200 without serving source audio.

The local browser page now exposes both controlled description search and
file-based similarity search; the page remains a review surface only and does
not contain an apply/rename control.

The read-only `build_end_state_readiness_snapshot.py` now cross-checks the
plan, collections, content identity/index, duplicate guard, and approval gate.
The current receipt is internally consistent: 7,315 files, 6,980 content IDs,
386 suggestions, 6,890 review rows, 39 never-act rows, zero auto rows, and
`ready_to_apply: false`.

The read-only `audit_local_labellers.py` confirms all four existing local
labellers are reachable, with 1,600 queued files and zero completed labels.
Their processes were not restarted; the receipt is the handoff for the next
human labelling session.

The current read-only audit covers the five main queues (ports 8751--8754 and
8770): all are reachable, with 1,651 queued files and 53 completed labels.
Those completions are reflected only in the audit receipt; they have not been
silently promoted into training or qualification data.

The new read-only `audit_completed_labelling_csvs.py` checks completed rows
against their manifests before integration. The current 53-row audit finds 52
usable labels and one explicit skip, with no duplicate IDs, path mismatches,
missing labels, or empty required escape hatches. One queue is intentionally
partial, so coverage is incomplete even though row integrity passes.

The readiness snapshot now includes that labeller receipt: the handoff is
ready (`4/4` servers reachable), while qualification remains pending (`0`
completed labels).

The same snapshot now also records the class-gate review queue (408 candidates,
35 exact-duplicate and 51 acoustic-near-duplicate candidates) and the separate
120-item validation labeller. The current readiness state is explicit:
`validation_labels_complete: false`, `ready_to_apply: false`.

The fail-closed `audit_rename_approval_gate.py` now checks the current plan
before any future approval. All 386 candidate rows are blocked today because
they are suggestions requiring explicit approval; 13 also touch exact
canonical groups, 16 touch exact aliases, and 11 touch acoustic near-duplicate
groups. No approval was granted and no plan field was changed.

The existing `apply_rename_plan.py` executor is now hardened at its mutation
boundary: any `--apply` invocation must provide a duplicate-guard receipt whose
plan hash matches the plan being applied, and any flagged source is refused.
The current plan still passes only the read-only dry run (0 selected rows); an
apply attempt without the guard exits with `REFUSED`.

The read-only `build_content_identity_manifest.py` now hashes every testing
file by complete bytes. The 7,315-file receipt contains 6,980 unique content
IDs and 335 exact aliases, so future embedding caches can key on audio content
rather than mutable paths.

The companion `rekey_embeddings_by_content.py` now joins the 2,048-D testing
embeddings to that manifest: 7,315 embedding rows resolve to 6,980 stable
content IDs while retaining all 335 path aliases. The model version and both
input hashes are recorded; embedding values are not rewritten.

`query_by_example.py` now accepts that content-addressed index and includes the
stable SHA-256, canonical path, and aliases in the query and result records. A
real 20-neighbour run returned 20 results, 10 physical-evidence rows, and zero
errors with the content index attached.

It also supports explicit content deduplication. On an exact-copy query, the
deduped run returned 17 distinct neighbours from a requested 20, excluded all
aliases of the query itself, and retained alias metadata on two other results.

When a content index is supplied, query-by-example now hashes the live query
file before searching and refuses stale embeddings if the bytes have changed.
The verified sample receipt records `query_content_verified: true`.

Evaluate each layer against the same grouped protocol. Waveform features are
currently useful for explanation/fusion, not a replacement for embeddings.

The local PANNs parity check confirms a separate deployment validity risk:
training embeddings use a 10-second window while the C++ path uses 5 seconds.
Across 12 files, production-vs-training cosine averaged 0.9365 (minimum
0.8684); the resampler difference alone averaged 0.9995. This does not change
the current Perch+CLAP incumbent, but it closes the door on promoting an old
PANNs-trained route until its embeddings are re-extracted through the actual
production window or the product window is deliberately widened and
re-qualified. Receipt: `SLO_PANNS_TRAIN_SERVE_SKEW_CURRENT_V1.md`.

## Phase 4 — model improvements worth testing

Test only pre-registered candidates against the best incumbent:

- supervised metric learning or prototype loss on the factorised fields;
- class-conditional calibration and conformal/quantile abstention;
- hard-negative mining from collection-held-out confusions;
- carefully controlled self-supervised or audio-language teacher embeddings;
- collection-balanced sampling only when the held-out metric improves.

Do not repeat closed routes without new evidence: LoRA, Dasheng-base, generic
pack-mastering augmentation, GroupDRO, DANN, CORAL, and multi-window have
already failed the product gate. Every experiment needs a control arm, fixed
folds, seed repeats,
and a receipt with the exact model hash.

The explicit physical-feature fusion route is also closed for promotion: its
best corrected-corpus delta was +0.03pp. Keep its cards for evidence and
calibration, but do not retry the same block fusion without a new hypothesis.

The pre-registered hard-negative pairwise route is now measured as well. A
binary correction model was allowed to arbitrate only within 16 known
boundaries after the incumbent chose the top two classes. It changed accuracy
by +0.11pp and macro-F1 by +0.07pp across eight vendor-held-out seeds, below
the +2pp gate. Keep the receipt for audit, but do not promote or silently
stack this correction into production.

The public-backbone route is now measured rather than hypothetical. The
BEATs AudioSet-pretrained bake-off (`beats_bakeoff.py`) was run on 523
collection-held-out rows across eight seeds. BEATs alone scored 47.30% versus
64.90% for Perch+CLAP; concatenating it scored 63.33% (−1.57pp paired).
It is rejected for SLO classification and rename policy. The receipt and
methodology are in `docs/classification/SLO_BEATS_BAKEOFF_V1.md`.

The previously untouched self-supervised/audio-transformer route is now also
measured correctly. On 1,523 eligible files across 80 collections, MERT was
−24.41pp, AST was −9.73pp, and Perch+CLAP+AST was only +0.13pp. None clears
the +2pp gate, so this route is closed for promotion. Receipt:
`SmartSampleManager/docs/classification/SLO_ENCODER_BAKEOFF_COLLECTION_HELDOUT_V1.md`.

## Phase 5 — turn predictions into decisions

For every file, write an immutable record containing source path, source hash,
model hash, filename evidence, audio evidence, predicted fields, confidence,
similarity, collection support, decision, and reason. The policy is:

- auto: class precision gate passed on unseen collections, confidence gate
  passed, no high-risk token conflict, no collision;
- suggest: useful evidence but class/domain gate not passed;
- review: unresolved disagreement, sparse class, or taxonomy boundary;
- never-act: rejection, unsupported class, duplicate, malformed, or unsafe path.

The class-conditional gate audit found three internally coherent research
classes (Clap, Kick, and Snare) and projected 408 review-only candidates on the
unseen testing cache. These remain candidates,
not auto rows: the thresholds were calibrated on the corrected corpus and need
new-domain human validation, duplicate checks, and explicit approval before
they can affect rename policy. Receipt:
`SmartSampleManager/docs/classification/SLO_CLASS_CONDITIONAL_GATE_AUDIT_V1.md`.

A dedicated 120-item validation labeller is now available on local port 8771;
it uses a separate CSV and does not restart or share state with the existing
labellers. Its initial receipt records 120 queued and zero completed labels.
The companion evaluator fails closed until all 120 rows have usable human
labels, then reports class precision and Wilson uncertainty bounds without
promoting any class automatically.

The follow-on `build_class_gate_promotion_packet.py` is now ready for the
post-validation handoff. It fails closed on missing or incomplete validation,
joins per-class precision to the 408 candidates, and can only mark classes for
separate explicit review; it cannot auto-approve or rename anything.

The class-gate queue is also fused with measured filename evidence and
physical definition-card fields in
`SmartSampleManager/docs/classification/SLO_CLASS_GATE_FUSION_REVIEW_V1.md`.
It contains 408 review-only candidates: 385 audio/name agreements, 3
conflicts, 18 audio-only rows, and 2 family/risk-only rows. Filename evidence
is corroborative only and never overrides the audio gate; duplicate and
near-duplicate flags remain blocking until human validation and approval pass.

## Phase 6 — safe rename implementation

Keep the existing immutable plan/apply/undo architecture:

- dry-run plan first;
- source edge signatures and content hashes validated immediately before apply;
- preserve original extensions and metadata;
- deterministic collision handling; never overwrite;
- path containment checks;
- durable journal written before mutation with PLANNED/COMMITTED/FAILED rows;
- explicit approval required for auto rows and a separate approval for
  suggestions;
- undo reads only the journal and is itself dry-run first.

The current testing-library plan must remain unapplied until the full-taxonomy
classes have qualified. The current high-confidence CSV is a review queue, not
an approval list.

The latest read-only apply validation inspected all 386 suggestion rows and
found 30 duplicate-guard blockers (13 exact canonicals, 16 exact aliases, and
11 acoustic near-duplicates). The remaining 356 rows still require explicit
approval; none is auto-approved. Receipt:
`SmartSampleManager/docs/classification/SLO_RENAME_PLAN_DRY_RUN_CURRENT_V1.md`.

## Phase 7 — product qualification

Qualify on a new library, not the training corpus:

- target a high precision operating point first (95% for auto-action);
- require per-class precision floors and a rejection floor;
- report coverage, abstention, collision rate, rollback success, and latency;
- manually audit every auto-action class during the first pilot;
- canary on a copy or a small opt-in folder;
- only then enable batch auto-renaming, with a visible undo path.

The mutation boundary now has a synthetic canary test covering journaled apply,
read-only undo validation, and explicit undo execution on temporary files. The
test passes without touching the sample library; a real canary remains gated on
qualified classes and explicit owner approval.

## Phase 8 — production hardening

- cache embeddings by content hash and model version;
- make inference deterministic and resumable;
- keep all source audio local unless the user explicitly opts into a service;
- expose audit logs and an exportable review queue;
- monitor drift by collection/vendor and automatically lower coverage when drift
  or rejection errors rise;
- version taxonomy, model, calibration, token rules, and rename templates
  independently.

The read-only readiness check is
`SmartSampleManager/tools/classification_benchmark/audit_taxonomy_readiness.py`.
It reports candidate labels without scanning audio, creating labels, changing
the production taxonomy, or applying a rename plan.

`SmartSampleManager/tools/classification_benchmark/audit_real_world_filename_hints.py`
provides a second, metadata-only inventory of possible environmental, animal,
human, mechanical, and material sounds. Its matches are discovery hints only;
they are never converted into labels or rename actions without audio review.

## Immediate next actions

1. Finish the validation manifest in the running local labeller; its CSV is
   still absent, so no new labels have been counted yet.
2. Review the 22 held taxonomy-gap rows (808, Sub Bass, sustained synth bass,
   Piano, Guitar, String) as an owner decision; do not force them into existing
   classes.
3. Human-check the 386 v3 provisional suggestions on a disposable copy; do
   not apply them to the source library. The v4b audit explicitly keeps them
   review-only.
4. Label the enriched pair-boundary manifest on local port 8753, the matched
   audio-vs-name class-pair queue across new collections; do not substitute
   filename-token frequency for boundary evidence.
5. Refit per-class calibration and promote only classes that pass the 95%
   collection-held-out precision gate. Keep auto-renaming disabled until this
   produces at least one qualified class.
6. Review the relabelled model's 1,071 candidate changes on a disposable copy;
   keep the research model separate until class-level precision and duplicate
   guards are requalified.
7. Test only a genuinely multi-task factorised model and hard-negative mining
   against v3. Do not reopen centroid variants or the closed LoRA, Dasheng-base,
   generic mastering-augmentation, GroupDRO, DANN, CORAL, multi-window, or
   hard-cascade
   routes without a new pre-registered hypothesis.
8. Run the first canary on a disposable copy; do not touch the source library.
9. Use query-by-example as a safe discovery and review workflow. Compare its
   nearest neighbours with the existing class suggestions, and later add typed
   human feedback (useful/not useful, same sound family, duplicate) before any
   similarity score can affect classification or rename policy.
10. Feed the exact duplicate receipt into the review/never-act queues, keeping
   every alias visible. Only after an explicit owner decision should a future
   rename plan choose a canonical path; never delete duplicates automatically.
11. Present the review collections as the product's first-class queues. Add
    append-only typed feedback events (accept, correct, reject, not-in-list,
    duplicate) before using any reviewer action as training data.

The grouped fusion receipt already identifies a promising intermediate route:
use high-precision filename evidence to improve low-confidence audio
predictions, but keep it in `suggest`/`review` until its per-class precision
also clears the 95% auto-action gate.

The current v3 new-domain receipt has been implemented as a suggestion-only
policy for Bass Loop, Crash, Hi-Hat Loop, and Percussion Loop, with
class-specific confidence floors. It generated 386 reviewable suggestions in
the testing library; none is auto-approved.

`full_taxonomy_review_evidence_packet_v1.jsonl` now attaches a physical
definition card, aspect-specific similarity, and a nearest labelled reference
to each of those 386 suggestions. The packet remains review-only and excludes
the candidate itself from nearest-reference search to avoid circular evidence.
