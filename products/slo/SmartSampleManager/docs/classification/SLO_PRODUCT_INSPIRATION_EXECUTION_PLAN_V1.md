# SLO product-inspired execution plan v1

Date: 2026-09-12

## What existing products teach us

### Sononym: retrieval by independent aspects

Sononym exposes similarity as separate overall, spectrum, timbre, pitch, and
amplitude aspects, each with its own rating. It also keeps projects and
alternative names separate from the original source file, with export rather
than destructive mutation as the normal workflow.

### Soundly: language, synonyms, and metadata

Soundly combines natural-language search, related searches, autocomplete,
thesauri, translation, collections, spectrograms, and embedded/UCS metadata.
The lesson is that filenames are one search surface, not the definition of
the sound.

### Ableton Live: background analysis and user labels

Live analyses user audio in the background, assigns best-match tags, and lets
users add custom tags and save filtered results as labels. This suggests that
analysis status, retryable failures, and user corrections should be first-class
state in SLO.

### Waves COSMOS and Loopcloud: automatic organisation, not automatic truth

Both products foreground AI categorisation/tagging and fast filtering. The
useful pattern is instant discovery; SLO should retain provenance and
confidence rather than presenting a prediction as ground truth.

## Next implementation order

1. **Evidence index and aspect retrieval.** Keep one content-addressed index
   containing name evidence, physical measurements, embeddings, duplicate
   groups, and model versions. Expose independent spectrum/timbre/pitch/
   amplitude weights for similarity search.
2. **Search surfaces.** Add synonym-aware text search, family/form filters,
   and aspect similarity. Search results should show the evidence that caused
   a match, not just a class name.
3. **Correction workflow.** Store user corrections as explicit claims with
   provenance. Distinguish `not_in_list`, `not_enough_info`, and `taxonomy_gap`;
   never collapse them into an unlabeled skip.
4. **Policy gates.** Recalibrate class-conditional automatic-action gates on
   the current collection-held-out corpus. Until a class passes its gate,
   route it to suggest/review. Keep rename execution journalled and separate.
5. **Only then train.** Use corrections for a pre-registered taxonomy or
   mechanism experiment. Do not spend labels on another generic encoder or
   waveform fusion bake-off unless a new hypothesis is written first.

## Current execution status

- The versioned evidence schema and C++ shadow adapter are in place.
- `build_unified_evidence_index.py` now joins the verified content-addressed
  embedding index with physical measurements, model suggestions, aliases, and
  duplicate groups into one read-only JSONL evidence index. It stores
  provenance and model row references without copying vectors, changing audio,
  or authorising rename actions.
- `search_unified_evidence_index.py` now provides deterministic local discovery
  over that index: controlled synonyms, family/form and prediction filters,
  physical measurement bounds, and duplicate inspection. Search output keeps
  the full evidence record and cannot create labels or rename actions.
- Factorised head, generic waveform fusion, mechanism-specific fusion, MERT,
  and AST have all failed the +2pp promotion gate.
- The first aspect-weighted similarity-search prototype is implemented in
  `tools/classification_benchmark/aspect_similarity_search.py` and is
  read-only.
- The production C++ engine now exposes the same aspect scores through
 `findSimilarByAspects()`. The in-app Find Similar overlay shows overall,
  embedding, spectrum, timbre, pitch, and amplitude ratings, with independent
  non-destructive weights for each aspect.
- Map and table search now share a conservative synonym lexicon for common
  producer terms such as `bd`/kick, `hh`/hi-hat, `tamb`/shaker, and
  ambience/atmosphere; multi-word queries remain literal.
- The taxonomy editor now requires a note for `not_in_list`,
  `not_enough_info`, and `taxonomy_gap`, and appends the explicit correction
  type to the pending JSONL correction log before applying the user override.
- `ingest_cpp_correction_log.py` now validates those append-only records and
  emits a non-overwriting owner-review CSV/JSON packet. It is fail-closed and
  never promotes a correction into training data automatically.
- A 50-file dry run over the real testing library produced 20 `never_act`, 28
  `review`, 2 `suggest`, and 0 `auto_rename` rows; the apply validator selected
  zero files and changed nothing.
- The lightweight planner is now fail-closed as well: it cannot emit a
  product `auto_rename` row unless `--enable-auto` and an explicit
  owner-qualified class policy are supplied. A 500-file real-library run
  produced 41 `never_act`, 338 `review`, 121 `suggest`, and 0 `auto_rename`
  rows; independent duplicate and approval gates selected zero files.
- The apply validator now requires a matching approval-gate receipt in
  addition to the duplicate guard before any automatic action can run. A
  missing approval receipt is refused before filesystem validation or mutation.
- A complete-hash identity manifest now covers the 28,330-file testing root
  (26,766 unique contents; 1,564 exact aliases), and the duplicate guard can
  consume that receipt directly. The 459 review/suggestion rows are exported
  through a blind label-manifest bridge so human labels can be collected
  without exposing the model's prediction.
- A 2,000-file read-only qualification expanded the queue to 277 suggestions,
  1,665 reviews, and 58 never-act rows, with zero automatic rows and zero
  approval-ready rows. A durable 1,942-item blind manifest is available for
  the next human pass.
- The complete 28,330-file testing-library qualification is now recorded: 4,071
  suggestions, 19,949 reviews, 4,310 never-act, and zero automatic rows. The
  full exact identity guard is applied; the acoustic near-duplicate inventory
  is explicitly marked partial because embeddings cover only the prior 7,315
  file subset. A durable 24,020-item blind manifest is available.
- The separate 120-file Kick/Clap/Snare gate-validation session is now
  complete and integrity-clean. It measured 39/40 Clap, 40/40 Kick, and 40/40
  Snare, but no class cleared the Wilson-supported 95% gate; the promotion
  packet remains review-only and no policy changed.
- `promote_correction_review.py` now records explicit owner accept/reject/defer
  decisions as a promotion-candidate manifest. Accepted rows remain
  `owner_approved_pending_rebuild`; no dataset, model, or policy changes occur
  in this step.
- `build_breadth_target_corpus.py` now provides the controlled 300-label
  checkpoint: it requires an exact usable-label count, lets newer human labels
  override older overlapping rows, records every correction, and refuses to
  build if any labelled file lacks an embedding. The output remains a
  research-only corpus with no audio, validation, production-model, or rename
  mutations.
- The completed breadth session reached 311 usable labels (315 decisions,
  four skips, four `Misc/Review` rows). The resulting 1,850-row corpus was
  evaluated on 81 vendor-held-out collections: nearest centroid reached
  55.13% versus 53.53% for the balanced logistic incumbent (+1.59pp, with
  better macro-F1 and worst-vendor accuracy), below the pre-registered +2pp
  promotion gate. It remains a research candidate only.
- The follow-up taxonomy/policy audit on the same corpus leaves 28 classes in
  the primary grouped set and finds only Clap, Kick, and Snare robust enough
  to be policy candidates at 95% precision with 20 accepted rows in every
  repeated seed. They remain audit-only pending owner approval and a separate
  new-domain gate. The dominant confusions are concentrated in the
  Percussion/Percussion Loop, Foley, and loop/form boundaries, so the next
  data decision is taxonomy review rather than another generic encoder.
- The current broad audio-only policy reaches only 87.4% precision on this
  harder corpus. A research-only candidate restricted to the three robust
  classes and their conservative thresholds reaches 95.77% minimum precision
  across eight seeds at 7.31% mean coverage. It is not promoted: owner
  approval and a new-domain qualification remain explicit gates before any
  automatic rename action.
- Physical definition cards have now been extracted for all 311 usable labels.
  Duration, onset density, periodicity, spectrum, and pitch summaries support
  the family/form split (loops versus one-shots) and are retained as evidence
  features, not semantic ground truth. This gives the next factorised taxonomy
  pass a measurable definition layer without another model bake-off.
- A fail-closed review packet records the candidate Clap/Kick/Snare tier,
  thresholds, independent validation result, evidence hashes, and the exact
  remaining approval/duplicate/dry-run gates. It marks no class auto-approved.
- That candidate tier has now been exercised end-to-end on a deterministic
  500-file real-library dry run: 41 `never_act`, 338 `review`, 121 `suggest`,
  and zero `auto_rename`. The duplicate guard found two acoustic near-
  duplicate suggestions; the approval gate blocked all 121 suggestions and
  the apply validator selected zero rows. This proves the safety boundary
  works without changing the filesystem.
- The rename planner now supports a separately hashed, validated class-
  threshold policy without changing its safe default. The measured candidate
  thresholds were exercised in a second dry run (169 suggestions, 290 reviews,
  zero automatic actions); all suggestions remained approval-blocked.
- A separate breadth-trained full-taxonomy nearest-centroid model has now been
  frozen from the 1,850-row corpus: 28 classes, 55.98% ± 0.76% vendor-held-
  out accuracy, and independently measured 95%-precision confidence/similarity
  gates. Projecting it over the existing 7,315-file cache yielded 583
  Clap/Kick/Snare suggestions, zero auto actions, and all 583 blocked by the
  approval gate after duplicate checks. The artifact is a deployable candidate
  only; the existing model remains untouched.
- The 7,315-row candidate plan is now reshaped into an immutable review
  collection (583 suggestions, 6,728 reviews, 4 never-act, zero auto actions)
  that can be inspected by the UI/manual workflow without transferring labels
  or granting approval.
- The canonical candidate-embedding projection now handles both historical
  and current old-model receipt schemas; the regenerated breadth receipt
  reports 3,444 real model disagreements instead of a false zero. This closes
  a provenance blind spot before any future model comparison.
- The action planner now supports the independently calibrated similarity
  gate. Applying the 0.731 floor reduced the full-library candidate queue from
  583 to 388 suggestions; all remain approval-blocked, with zero automatic
  actions and zero apply selections. This is the current safest review tier.
- All 388 current suggestions now have joined review evidence: physical
  definition cards, nearest labelled references, aspect similarity, filename
  evidence, and explicit human-approval state. The collection remains
  immutable and review-only; no label transfer or action promotion occurs.
- A fresh factorised identity/family/form head was probed on the breadth
  corpus and lost to the centroid control (54.53% vs 55.82%, lower macro-F1).
  That route is closed for this checkpoint; the physical evidence layer is
  retained for explanations and taxonomy review rather than another generic
  head.
- A controlled physical-feature fusion benchmark over the full breadth corpus
  was also neutral: the best acoustic weight changed accuracy by only +0.03pp
  and did not materially improve macro-F1. Physical measurements stay in the
  evidence/search layer; they are not promoted as a classifier input.
- `build_owner_approved_training_manifest.py` now blocks accepted rows unless
  their path and complete-file SHA-256 match the canonical collection-aware
  manifest and are outside sealed validation/duplicate-alias sets.
- Current policy audits show no safe broad automatic-renaming tier on unseen
  collections. Production policy remains unchanged.
- The end-state readiness snapshot now cross-checks the validation labeller
  service audit against the completed-label CSV-integrity receipt. If those
  receipts disagree, readiness fails closed instead of treating either source
  as authoritative. A fresh read-only audit now reconciles the current
  120-file batch at 120/120 complete; the result is recorded separately as a
  live receipt. This clears the validation-completeness gate only; model,
  policy, owner-approval, duplicate, and rename gates remain unchanged.
- The 388 similarity-gated suggestions now also have a flattened owner-review
  CSV with confidence, similarity, nearest labelled reference, physical
  definition facets, and duplicate flags, plus a SHA-256 receipt. It is a
  sortable review handoff only; it cannot promote a suggestion or execute a
  rename.
- The apply validator now enforces the independent approval receipt for
  selected suggestions as well as automatic actions. A current-plan check
  confirms all 388 suggestions remain blocked until explicit approval; passing
  `--include-suggest` cannot bypass that gate.
- An explicit approval-receipt bridge now accepts only owner decisions made
  against the immutable review CSV. It rechecks plan hashes, paths,
  destinations, source signatures, and duplicate flags before emitting a
  receipt. The initial template is 388/388 blocked with no decisions, ready
  for a human review pass but not for application.
- A separate blind-label manifest for the 388 suggestions is now exported,
  balanced across 14 collections and with all model hints hidden. It is the
  independent by-ear validation route for confirming or rejecting suggestions;
  it creates no labels until a human completes the labeller workflow.
- The approval bridge now also rejects edits to displayed confidence,
  similarity, filename evidence, or duplicate flags, not just paths and
  predicted classes. The blank approval template remains 388/388 blocked.
- `import_blind_labels_to_owner_decisions.py` now joins future label-tool CSVs
  by exact manifest ID and path: agreement is an approval candidate,
  disagreement is a rejection, and skips are deferred. It fails closed on
  partial or mismatched manifests and still requires the independent approval
  receipt before any action.
- The current queue summary is recorded separately: 257 Kick, 90 Snare, and
  41 Clap suggestions; 360/388 agree with an exact filename class; 82 carry a
  duplicate flag. These are review triage statistics only, not new accuracy
  claims or approvals.
- The complete label-to-approval handoff is documented in
  `SLO_CANDIDATE_REVIEW_RUNBOOK_V1.md`, including the live port, identity
  checks, blind-label import, approval receipt, and dry-run-only validation.
- A label-free physical-analysis pass now covers 7,314 of 7,315 requested
  testing-library files. It emits duration, form hints, onset density,
  periodicity, spectrum, pitch, spatial, clipping, and provisional technical
  tags in a separate receipt; one missing MP3 is recorded as an error. These
  are searchable evidence, not semantic labels or rename authority.
- `audio_definition_card.py` now supports process workers for this analysis;
  a 100-file benchmark completed in 9.2 seconds with four workers versus
  19.3 seconds single-process, with zero analysis errors.
- Those cards are now also converted into a 7,314-row technical-tag plan for
  search and future non-semantic naming. Every row explicitly carries a null
  semantic label and the receipt marks the tags as provisional evidence only.
- A read-only physical-tag search CLI now filters that plan by technical tag,
  temporal form, duration, low-band energy, spectral centroid, and path. A
  sample `possibly_loop` query is recorded as a search receipt; its results
  remain provisional and cannot create a rename action.
