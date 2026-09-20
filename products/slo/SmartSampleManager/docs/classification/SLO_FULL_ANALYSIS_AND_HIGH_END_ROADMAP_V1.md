# SLO audio intelligence: full analysis and high-end roadmap

The concrete end-goal execution contract is maintained in
[`SLO_END_GOAL_EXECUTION_PLAN_V1.md`](SLO_END_GOAL_EXECUTION_PLAN_V1.md).

## Executive verdict

SLO is already more rigorous than a typical prototype, but it is not yet a
high-end general audio classifier. It has a real local product, a working scan
and cache pipeline, useful audio similarity infrastructure, unusually strong
file-safety controls, and a serious grouped-evaluation discipline. Its core
weakness is not a missing fashionable neural network. It is insufficiently
broad, independently labelled data combined with a taxonomy that still asks one
flat label to represent several different questions.

The current evidence supports three different claims, which must not be mixed:

1. On the earlier, narrow nine-class by-ear set, the best research cascade
   reached **86.1%** under ordinary five-fold cross-validation.
2. On the broader collection-held-out task, the current 28-class candidate
   reaches **55.98% ± 0.76%**. A closely related 31-class checkpoint reaches
   **55.13% ± 0.61%**, with **43.53 macro-F1** across 81 collections.
3. A narrow Clap/Kick/Snare action policy reaches **97.03% mean precision**
   and **95.77% minimum precision** across grouped seeds, but covers only
   **7.31%** of examples and is not yet approved for automatic renaming.

Those numbers are not contradictory. They describe different class breadth,
split difficulty, and action coverage. The second is the honest measure of
generalisation; the third shows that high precision is possible when the
product abstains aggressively.

The recommended product is a **local-first, evidence-backed audio librarian**:

- first-class search by text, example, timbre, pitch, envelope, rhythm and
  measurable attributes;
- factorised, editable descriptions rather than one forced category;
- explicit `unknown`, `taxonomy_gap`, and `not_enough_information` states;
- collection-held-out evaluation and class-specific calibration;
- deterministic, previewed, journalled and reversible file actions;
- continuous learning from verified corrections, never from filenames or
  model predictions treated as truth.

The shortest route to a product at the level of Sononym, Ableton Live, Soundly,
XO, Atlas, Loopcloud and COSMOS is to make **retrieval and review excellent
before broad automatic classification**. No public evidence shows that those
products have solved universal sample classification. Their visible advantage
is product workflow.

## 1. Audit boundary

This assessment is based on the `products/slo` checkout at commit `f9b502e` on
the `main` branch. The tree contains substantial pre-existing uncommitted work,
so this report does not claim a clean release snapshot and does not modify the
classifier, production policy, model artifacts, labels, or audio.

The evidence hierarchy used here is:

1. by-ear human labels with content identity;
2. whole-collection or vendor-held-out evaluation;
3. duplicate-controlled grouped evaluation;
4. class-specific precision, recall, calibration and coverage;
5. ordinary random cross-validation only as a research diagnostic;
6. folder- or filename-derived labels only as weak coverage evidence.

This intentionally retires the old 96.54% repository benchmark as a product
claim. It was strongly exposed to filename/folder leakage. It also avoids using
public AudioSet or ESC-50 scores to predict SLO performance: the repository's
own BEATs result is a direct warning that public benchmark strength can transfer
poorly to short, processed sample-pack audio.

## 2. Current system assessment

### 2.1 Shipping pipeline

The currently documented production path is:

```text
file discovery
  -> cache/version check
  -> decode and 32 kHz mono resample
  -> metadata + filename/folder + DSP evidence
  -> PANNs CNN10 512-D embedding
  -> frozen 16-class linear acoustic head
  -> entropy/margin diagnostics + nearest-centroid OOD gate
  -> evidence override policy
  -> SQLite cache
  -> UMAP/HNSW similarity index
  -> map/table browser and review UI
```

The deployed acoustic stack is therefore not the same as the strongest
research stack. Production uses PANNs; the best narrow research result uses
Perch plus CLAP. The newer 28-class nearest-centroid candidate is also still a
research artifact. Any product page must state which model and evidence path a
number describes.

### 2.2 What is strong

| Area | Assessment | Evidence |
|---|---|---|
| Ingest and caching | Strong foundation | Incremental cache, version checks, malformed-file handling, format-aware readers and background inference exist. |
| File safety | Differentiating | Read-only analysis, copy-first posture, hash/identity checks, collision checks, approval receipts, dry-run plans and undo/journal work are present. |
| Evaluation honesty | Strong | Collection-held-out evaluation exposed a 9.7-point optimism gap in random CV and replaced the old headline. |
| Similarity infrastructure | Promising | PANNs embeddings, HNSW, UMAP, aspect similarity and explained scores exist in production or shadow form. |
| Human-in-the-loop design | Strong research base | Blind label manifests, typed correction outcomes, immutable review packets and promotion gates exist. |
| Physical analysis | Useful supporting layer | Multi-window duration, onset, periodicity, spectrum, pitch, spatial and clipping evidence is available for search/explanation. |
| Real-time safety | Good narrow evidence | Existing receipts report 0 allocations and 0 deadline misses over 2,000 tracked `processBlock()` calls. |

### 2.3 What is weak

| Area | Current limitation | Consequence |
|---|---|---|
| Broad semantic accuracy | ~56% across 28 classes on unseen collections | A top-1 label cannot be treated as file truth. |
| Tail-class quality | Macro-F1 is materially below accuracy; several classes are sparse or incoherent | Headline accuracy hides weak concepts. |
| Unknown/OOD boundary | Historical cross-vendor false-known was 72%; newer rejection work is better but still research-scoped | Broad auto-tagging remains unsafe. |
| Taxonomy | `Percussion`, `Foley`, `Other/none`, SFX and some loop classes mix source, role and form | These categories become error sinks. |
| Calibration | Confidence is optimistic on unseen collections | A raw score is not a reliable probability. |
| Data breadth | 1,850 rows over 81 collections is good progress but small for 28 classes and vendor diversity | Model capacity is label-limited; generic fine-tuning overfits collection style. |
| Production/research parity | PANNs ships; Perch+CLAP and the breadth candidate do not | Research gains do not yet reach users. |
| Model footprint | The earlier Perch+CLAP option was estimated near 680 MB; delivery is still unresolved | A plugin-only inference architecture may be the wrong deployment shape. |
| Product proof | Retrieval usefulness and time-to-find are not yet measured as primary KPIs | SLO can improve technically without proving user value. |

### 2.4 Evidence reconciliation

| Result | Proper interpretation | Do not interpret as |
|---|---|---|
| 96.54% old benchmark | Historical fused repository benchmark with leakage risk | General-library accuracy |
| 86.1%, nine classes | Best narrow by-ear research cascade under ordinary CV | Unseen-vendor, 28-class product accuracy |
| 62.1%, ten classes | Earlier Perch+CLAP vendor-held-out diagnostic | Current broad production performance |
| 55.98%, 28 classes | Current breadth candidate under vendor/collection holdout | Deployed classifier accuracy |
| 97.03% precision at 7.31% coverage | A conservative three-class candidate policy | A broad classifier or approved auto-rename feature |
| 99.05% on 105 accepted validation items | Strong drum-heavy validation evidence | A population-wide lower-bound guarantee |

The most important management rule is simple: **every reported number must carry
its model version, taxonomy, split unit, evidence inputs, action threshold and
coverage**.

## 3. Competitive benchmark

Commercial products do not expose comparable independent accuracy reports.
Their official documentation supports a workflow comparison, not a fair model
leaderboard.

| Product | High-end behaviour exposed to users | Implication for SLO |
|---|---|---|
| Sononym | Query-by-example with independently weighted Overall, Spectrum, Timbre, Pitch and Amplitude similarity.^1 | Make aspect weighting and match explanations a flagship workflow. |
| Ableton Live 12 | Background analysis, similarity search, editable auto-tags, custom/nested tags, saved browser states and similar-sample swapping; files over 60 seconds are excluded and the first two seconds drive similarity analysis.^2 | Indexing state, editability, instant audition and DAW context matter as much as labels. SLO's multi-window analysis can exceed the two-second boundary. |
| Soundly | Natural-language search, related search, autocomplete, thesaurus/translation, local/cloud libraries, spectrograms, collections, metadata editing and UCS support.^3 | Build a hybrid retrieval engine; do not ask acoustic classification to replace language or metadata. |
| Soundminer | Deep fielded metadata, UCS workflow, batch processing and professional DAW delivery.^4 | Structured metadata and interoperability are product-grade capabilities, not export afterthoughts. |
| Loopcloud | Instrument/genre/key/BPM search plus harmonic, rhythmic and similar matching.^5 | Separate match intent: “sounds alike,” “fits rhythmically,” and “fits harmonically” are not one distance. |
| XLN Audio XO | A deliberately narrow one-shot drum map, nearest-similarity lists, filters, history, favourites, contextual hot-swap and kit variation.^6 | A superb narrow drum mode can be more valuable than a weak universal mode. |
| Algonaut Atlas 2 | AI-arranged local sample maps, category regions, hover audition, multiple maps and kit creation.^7 | Visualisation succeeds when it is tightly connected to audition and creation, not when it is merely a scatter plot. |
| Waves COSMOS | Low-friction aggregation and auto-tagging of one-shots and loops.^8 | Fast setup and immediate organisation set the usability baseline. |
| Splice | Catalogue text search, audio-to-audio Similar Sounds, audio/MIDI Search with Sound and natural-language Describe a Sound.^9 | Retrieval should accept both a reference sound and an intent phrase. |

### 3.1 Where SLO can beat them

SLO should not claim a superior classifier without a shared benchmark. It can
build a defensible advantage around capabilities competitors do not publicly
foreground together:

- local-first indexing with no compulsory upload;
- visible provenance for filename, metadata, DSP, embedding and human evidence;
- duplicate-aware identity before training, retrieval or renaming;
- collection-held-out and new-domain model receipts;
- explicit abstention and taxonomy-gap reporting;
- separate precision/coverage promises for tags, suggestions and mutations;
- deterministic rename plans with approval, collision protection, journal,
  verification and undo;
- an inspectable “why this matched” explanation;
- a learning loop that promotes only verified, identity-safe corrections.

That positioning is stronger than “AI automatically renames everything.” It is
also more credible given the measured accuracy.

## 4. What state-of-the-art research changes—and what it does not

CLAP validates shared audio-language embeddings for zero-shot concepts and
flexible text retrieval.^10 BEATs validates acoustic-token pretraining and reports
strong general audio benchmark results.^11 Perch 2.0 uses prototype learning,
self-distillation and source prediction, and is designed to transfer with small
label sets.^12 These are useful representation sources, not proof of success on
SLO's domain.

The repository has already run the decisive local experiments:

- Perch+CLAP was complementary on the narrow taxonomy.
- BEATs, AST and MERT did not beat the controlled incumbent on the current
  collection-held-out task.
- generic fine-tuning, augmentation, factorised flat heads and physical-feature
  concatenation did not clear the promotion gate.
- nearest centroid frequently generalised better than higher-capacity learned
  heads because the available data is small and collection-biased.

The research implication is not “stop using neural models.” It is:

1. use foundation embeddings as reusable evidence;
2. keep the task head small until label breadth grows;
3. evaluate every candidate on held-out collections;
4. build separate temporal and attribute tasks where the mechanism differs;
5. treat open-set recognition as its own measured system.

Open-set/OOD research also cautions against trusting one conventional benchmark
or one softmax score; method rankings can change under larger and better
disentangled evaluations.^13 SLO should compare energy, feature magnitude,
Mahalanobis/distance, prototype density, conformal sets and explicit negative
heads under the same held-out collection protocol. The winner must reduce
false-known errors without destroying useful known-class coverage.

Public datasets are support material, not product truth. AudioSet contains a
632-node ontology and more than two million human-labelled ten-second web-video
clips,^14 while FSD50K provides over 51,000 distributable Freesound clips across
200 AudioSet-derived classes.^15 They are valuable for vocabulary, broad
negative exposure and a separate real-world/SFX branch. They should never be
blended into a headline SLO metric without domain-specific reporting.

## 5. Target product architecture

```text
immutable audio + content hash + path aliases
                    |
                    v
        ingest, decode and versioned cache
                    |
        +-----------+-----------+
        |           |           |
        v           v           v
   name/metadata  physical    multi-window embeddings
     evidence     evidence     scene + onset + tail
        |           |           |
        +-----------+-----------+
                    |
                    v
         factorised evidence graph
 domain | family/source | form | event/role | attributes
 provenance | uncertainty | alternatives | supporting regions
          /                 |                 \
         v                  v                  v
 retrieval/ranking     editable tags      decision policy
 text/example/facets   and corrections    abstain/review/suggest
         |                  |                 |
         +------------------+-----------------+
                            |
                            v
                 deterministic action engine
            preview -> approve -> journal -> verify -> undo
```

### 5.1 Do not use one label for five questions

Store independent axes, each with its own unknown state:

| Axis | Examples |
|---|---|
| Domain | music sample, sound effect, speech, ambience, unknown |
| Source/family | drum, bass, synth, voice, animal, vehicle, material |
| Form | one-shot, loop, phrase, sustained, texture, recording |
| Event/role | kick, snare, impact, riser, fill, bark, movement |
| Pitch | unpitched, pitched, note, key, stable, gliding |
| Envelope | impulsive, short, decaying, sustained, swelling |
| Spectrum/timbre | bright, dark, noisy, harmonic, low-heavy, metallic |
| Rhythm | onset density, periodicity, BPM, groove signature |
| Spatial/processing | mono, wide, dry, wet, distorted, clipped |

`Foley` should be provenance/source context or a workflow tag, not a universal
acoustic identity. `Other/none` should be a decision state, not a learnable
semantic class. `Percussion` needs either a clear positive definition or a
review-only parent role; otherwise it will remain an absorbing error class.

### 5.2 Use different models for different mechanisms

- **Transient identity:** onset-centred embeddings plus a small prototype or
  metric-learning head.
- **Loop/form:** timestamp embeddings, onset sequence, periodicity, decay and
  full-file band energy.
- **Pitch/harmony:** pitch track, chroma/key confidence and harmonic embedding;
  abstain when confidence is weak.
- **Timbre retrieval:** Perch/CLAP or a compressed successor, independently
  weighted from pitch and envelope.
- **Text retrieval:** CLAP-style audio-language similarity plus controlled
  lexical synonyms and metadata.
- **OOD/rejection:** explicit broad-negative model and calibrated distance or
  set-valued prediction, not just maximum softmax probability.

### 5.3 Use a two-tier runtime

The high-end architecture does not require 680 MB inside every plugin process.

1. A standalone/background librarian performs expensive analysis once, stores
   versioned embeddings and physical evidence, and maintains the search index.
2. AU/VST3 clients read the local catalogue, audition, search and drag results
   without duplicating foundation-model memory.
3. A compact edge model or handcrafted fallback handles newly dropped audio
   until background enrichment finishes.
4. Exported metadata remains usable even when the service is not running.

This design improves memory, scan throughput, model-update independence and DAW
stability while retaining local-first privacy.

## 6. Data programme: the highest-return investment

The measured learning curve says collection breadth is worth more than repeated
labels from familiar packs. Data acquisition should therefore be organised by
**new collection and unresolved mechanism**, not only by class balance.

### 6.1 Minimum next corpus

Build a versioned 6,000–10,000-item by-ear corpus with:

- at least 150–250 examples for each core class;
- at least 20 independent collections per auto-action candidate class;
- a dedicated 2,000+ broad-negative/OOD set from unseen music, SFX, speech,
  ambience, impulse responses, stems and malformed/non-target assets;
- explicit duplicate families and aliases;
- separate development, calibration and final sealed collections;
- two-reviewer adjudication on ambiguous taxonomy boundaries;
- factor labels for source/family, form, role and selected attributes;
- `not_in_list`, `not_enough_information`, `taxonomy_gap` and `reject` as
  first-class outcomes.

Counts are planning guides, not qualification gates. Automatic action requires
the statistical lower bound to clear the promise on new-domain data.

### 6.2 Active-learning queue priorities

Use the following order:

1. new collections far from the labelled embedding distribution;
2. disagreement between name, acoustic, physical and neighbour evidence;
3. high-confidence errors and false-known OOD items;
4. boundary pairs such as Snare/Clap, Percussion/Hi-Hat, loop/one-shot and
   Foley/SFX/Impact;
5. under-supported classes across many collections;
6. random audit samples to prevent active-learning selection bias.

Never promote pseudo-labels, filename-derived labels or exact duplicates as new
ground truth.

## 7. Evaluation and release gates

### 7.1 Model scorecard

Every candidate receipt should report:

- vendor/collection-held-out accuracy and macro-F1;
- per-class precision, recall, support and number of collections;
- worst-collection and lower-decile collection performance;
- top-2/top-3 accuracy for review UX;
- expected calibration error and reliability diagrams;
- OOD AUROC, false-known rate and known false-rejection rate;
- precision–coverage curves for each action tier;
- performance by duration, form, domain, pitch confidence and duplicate status;
- latency, throughput, peak/resident memory, cache size and model footprint.

### 7.2 Product scorecard

Classifier accuracy is insufficient. Measure:

- Recall@5/10 and mean reciprocal rank for query-by-example;
- “useful result in top five” rate from blind producer review;
- median auditions and seconds to find an acceptable sound;
- suggestion acceptance, correction and taxonomy-gap rate;
- scan completion, retry, incremental-rescan and disconnected-drive behaviour;
- percentage of outputs with visible provenance;
- zero unjournalled file mutations;
- apply/verify/undo success on disposable fixtures;
- DAW scan/load/state-save/reopen performance.

### 7.3 Suggested qualification thresholds

| Capability | Entry gate | High-end gate |
|---|---|---|
| Broad tag suggestion | ≥85% delivered precision, ≥60% coverage | ≥90% precision, ≥75% coverage on new collections |
| Conservative suggestion | ≥95% precision, ≥10% coverage | ≥97% precision, ≥25% coverage |
| Automatic metadata/write action | 95% Wilson lower bound above advertised precision for every class; independent new-domain set | Same gate plus live audited drift and instant rollback |
| OOD | <20% false-known at ≥90% known acceptance | <10% false-known at ≥90% known acceptance |
| Retrieval | ≥80% useful top-5 | ≥90% useful top-5 and ≥30% reduction in time-to-find |
| Safety | Zero silent data loss; 100% journal/undo on qualification suite | Same across clean-machine and DAW host matrix |

These are recommended product gates, not achieved results.

## 8. Prioritised roadmap

### Phase 0 — product truth and freeze (1–2 weeks)

- Declare the shipping PANNs classifier, Perch+CLAP research stack and breadth
  centroid candidate as three separate model lines.
- Create one machine-readable model card per line: taxonomy, data hashes,
  split, metrics, calibration, model size and eligible actions.
- Freeze the 1,850-row breadth receipt and the 120-file validation receipt.
- Remove the 96.54% figure from every customer-facing surface.
- Set all automatic file mutations to disabled unless a signed class policy is
  explicitly loaded.

Exit: one unambiguous source of truth and no stale public claims.

### Phase 1 — high-end retrieval beta (4–8 weeks)

- Finish the content-addressed evidence index in the product.
- Ship Find Similar with Overall, Timbre, Spectrum, Pitch, Envelope and Rhythm
  weights plus explained component scores.
- Add synonym-aware text search, physical filters, favourites, saved searches,
  history and instant audition/hot-swap.
- Expose background scan progress, pause/resume, errors and retry.
- Deduplicate exact content and diversify near-duplicate result lists.
- Run a blind 50-query producer study measuring top-five usefulness and
  time-to-find against Finder/manual folders and one competitor.

Exit: retrieval meets ≥80% useful top-five and shows a material time saving.

### Phase 2 — taxonomy and data expansion (6–12 weeks, overlapping)

- Resolve `Percussion`, `Foley`, `Other/none`, SFX and loop boundary definitions.
- Label new collections breadth-first toward 6,000+ items.
- Add broad negatives and sealed calibration/final-test collections.
- Require factor labels for form and domain; add other axes only where the UI
  has a concrete use.
- Continue immutable correction and approval receipts.

Exit: minimum support and collection diversity are met for the core taxonomy;
inter-reviewer disagreements are quantified.

### Phase 3 — controlled model programme (4–8 weeks)

- Rebuild the nearest-centroid incumbent first.
- Test multi-prototype and labelled-neighbour memory.
- Train a dedicated known-vs-unknown/rejection head with broad negatives.
- Test temporal pooling only on loop/form hypotheses.
- Test parallel attribute heads without routing through an unreliable parent.
- Distil or quantise only a model that first wins on the held-out product task.
- Require paired grouped seeds and a pre-registered material-improvement gate.

Exit: ≥2-point macro-F1 or accuracy gain without worse OOD/calibration, or a
material precision–coverage improvement at the intended product tier.

### Phase 4 — suggestion-only organisation beta (4–6 weeks)

- Present editable tag chips by axis with provenance and alternatives.
- Generate deterministic names and metadata previews.
- Support metadata-only and copy/export workflows before physical rename.
- Make every source change owner-confirmed, journalled and reversible.
- Feed corrections into review queues, never directly into training.

Exit: high suggestion acceptance, zero data-loss incidents and 100% undo in the
qualification suite.

### Phase 5 — narrow automatic tier (after sufficient independent evidence)

- Start only with classes that clear their statistical gate; Clap/Kick/Snare
  are current candidates, not approvals.
- Validate on entirely new collections not used for model or threshold choice.
- Prefer embedded metadata or copied exports before source filename mutation.
- Monitor live precision and disable a class immediately on drift.

Exit: per-class lower confidence bounds clear the promise, with signed policy,
clean-machine testing and host qualification.

### Phase 6 — separate SFX/real-world branch (optional)

- Use AudioSet/FSD50K for vocabulary, representation probes and negatives.
- Factor source, event, form and scene; do not force single-label classification
  on multi-source ambience.
- Map applicable output to UCS rather than forcing music-sample labels into an
  SFX standard.
- Maintain separate data, metrics and release policy from the music branch.

Exit: a concrete workflow and independent benchmark justify its model and
support cost.

## 9. What to stop doing

- Stop reporting random-CV or folder-derived accuracy as user-library accuracy.
- Stop adding generic encoders without a mechanism-specific hypothesis.
- Stop treating confidence, similarity and probability as interchangeable.
- Stop using catch-all bins as if they were coherent acoustic classes.
- Stop expanding the taxonomy before enough by-ear examples exist.
- Stop concatenating physical features into embeddings when they add no measured
  classifier value; keep them for retrieval and explanation.
- Stop targeting sub-millisecond foundation-model inference inside the audio
  callback. Library analysis is an offline/background problem.
- Stop tying “high-end” to automatic renaming coverage. A safe, fast and
  inspectable librarian can be high-end while abstaining often.
- Defer the frontier plan's billion-parameter reasoning, latent audio synthesis,
  SHARC deployment and real-time neural wave-equation solver. They are separate
  R&D programmes and do not address the current classification bottleneck.

## 10. Immediate decisions

1. **Positioning:** approve “local audio librarian that shows its work” as the
   product thesis.
2. **Deployment:** choose standalone/background enrichment plus lightweight
   plugin clients over embedding two large encoders in every host instance.
3. **Default promise:** ship suggestions/review, not broad automatic renaming.
4. **Taxonomy:** demote `Other/none` to a state; treat Foley as a source/workflow
   facet; formally review Percussion and loop boundaries.
5. **Data budget:** fund collection-breadth labelling before another general
   encoder bake-off.
6. **North-star metric:** producer time-to-useful-sound, guarded by delivered
   precision, OOD false-known rate and zero data loss.

## 11. Overall scorecard

| Dimension | Current level | High-end requirement |
|---|---:|---:|
| Engineering foundation | 7/10 | Production/research model parity and service-style enrichment |
| Evaluation discipline | 8/10 | Fully sealed new-domain test and uniform model cards |
| Broad classification | 4/10 | Better taxonomy, 6k–10k broad labels, calibrated factor heads |
| Narrow high-precision policy | 7/10 | Independent statistical approval and drift monitoring |
| OOD/unknown handling | 4/10 | Dedicated negative model and <10–20% false-known target |
| Retrieval/search | 6/10 | Productised aspect/text/example search plus blind usefulness study |
| Metadata/interoperability | 5/10 | Embedded/exported metadata and UCS mapping where applicable |
| Workflow/UX | 6/10 | Background status, instant audition, saved state and correction loop |
| File safety | 9/10 | Clean-machine and DAW-host qualification of the full action lifecycle |
| Commercial readiness | 5/10 | Distribution, licensing, clean-machine and Ableton gates remain |

SLO's strongest path is asymmetric: keep its unusually serious evaluation and
safety layer, then close the discovery-workflow gap. That can produce a
high-level product sooner than chasing a universal classifier, and it creates
the clean correction data needed to improve the classifier later.

## 12. Label-free implementation shipped

The first executable slice of this strategy is
`tools/classification_benchmark/label_free_zero_shot.py`. It accepts a single
audio file or recursive library directory, embeds audio with the local CLAP
checkpoint, compares it with a small configurable prompt bank, and writes a
JSONL receipt containing top-k suggestions, margin, entropy and an explicit
`review`/`suggest` state. It never reads ground-truth labels, creates semantic
labels, writes metadata, renames files or modifies source audio. Scores are
marked `uncalibrated_prompt_similarity`; they are evidence for review, not
probabilities.

Example:

```bash
python3 tools/classification_benchmark/label_free_zero_shot.py \
  --input /path/to/library \
  --model tools/classification_benchmark/clap_model_music \
  --out /tmp/slo_label_free_receipt.jsonl \
  --device cpu
```

An interrupted or expanding scan can continue without rescoring successful
rows by adding `--resume`; the runner rejects receipts with a different model
or prompt bank and retries only prior error rows.

The focused regression suite is
`tools/classification_benchmark/test_label_free_zero_shot.py` (4 tests). A
real-file smoke run on `real_kick_a.wav` returned `Kick` as the top suggestion
with `semantic_label: null` and `read_only: true` in the receipt. The next
safe increment is to run this over a user-selected library, inspect score and
margin distributions, then add calibrated thresholds and retrieval/physical
evidence before exposing any automatic action.

### GPU0 corpus run

The CUDA-compatible runner was validated on the remote GPU0 environment. The
latest resumed sample-pack receipt covered 8,622 actual audio files: 5,649
`suggest`, 2,973 `review`, and one decoder error. An earlier pass also showed
4,886 macOS `._` sidecars; discovery now excludes those metadata files. The
runner also reads only the first 10 seconds from the container and rejects
oversized assets before decode, preventing pathological files from stalling a
batch. These counts are workflow triage, not accuracy claims, because the
prompt scores remain uncalibrated and no ear labels were read. The complete
library transfer remains resumable, but this receipt is the current stable
GPU0 result.

### Multi-view consistency arm

The runner now supports `--views 3`, which scores the full, early-half and
late-half waveform views independently, aggregates their prompt scores by
median, and records `view_agreement` and `view_score_std`. A file is only in
the `suggest` tier when its CLAP score/margin gate and the view-agreement gate
both pass; disagreement remains `review`. This is a label-free reliability
signal, not a calibrated probability or a semantic label. The completed GPU0
experiment covered 8,621 files and produced 3,482 `suggest` and 5,139 `review`
rows; the receipt is
`tools/classification_benchmark/receipts/gpu0_sample_pack_multiview_8622_receipt_20260913.jsonl`.
The single-view receipt remains available as the ungated baseline.

The review tier is operationalised by
`tools/classification_benchmark/build_label_free_review_queue.py`, which ranks
the most uncertain rows without inventing labels. Its GPU0 export contains the
top 500 of 5,139 review candidates at
`tools/classification_benchmark/receipts/gpu0_multiview_review_queue_20260913.json`;
human approval remains mandatory for any downstream action.

### Independent-model agreement arm

To test whether a second foundation model can act as a label-free reliability
signal, the same three-view corpus was scored with the generic local CLAP
checkpoint (`clap_model`) on GPU0. It covered 8,622 staged files and produced
4,268 `suggest`, 4,354 `review`, and one decoder-error row. This is not a
ground-truth accuracy result; it is a second, independent prompt-similarity
opinion with the same read-only safety contract.

`tools/classification_benchmark/build_label_free_ensemble_receipt.py` combines
the music-tuned and generic receipts. Its conservative policy keeps
`suggest` only when both models agree on the top label and both source rows
already passed their own score, margin and three-view gates. On the aligned
8,621-file intersection, 1,594 rows (18.5%) survived as agreement suggestions
and 7,027 rows remained review-only; 4,211 rows had the same top label but
failed at least one model's independent gate. The result is
`tools/classification_benchmark/receipts/gpu0_label_free_ensemble_20260913.jsonl`.

The same disagreement signal is exposed through the v2 review-queue builder.
Its top-500 export is
`tools/classification_benchmark/receipts/gpu0_ensemble_review_queue_20260913.json`;
the queue is ordered by cross-model disagreement, gate-status disagreement,
view instability and margin uncertainty.

The same run now exports a normalized 512-D vector index for product-grade
query-by-example retrieval:
`tools/classification_benchmark/receipts/gpu0_music_embeddings_8622_20260913.npz`.
`tools/classification_benchmark/label_free_similarity_search.py` returns
cosine-ranked neighbours with no semantic labels or write actions; the smoke
result is
`tools/classification_benchmark/receipts/gpu0_music_similarity_example_20260913.json`.
This is the local-first analogue of the similarity workflows in Sononym, XO,
Atlas and Ableton, while keeping similarity scores explicitly uncalibrated.

This demonstrates the right product posture for no-ear-label operation:
multiple models and waveform views can reduce unsafe automation, but they do
not create truth. The ensemble is still uncalibrated, and its suggestions
require human approval until a sealed, by-ear calibration set establishes
class- and domain-specific precision bounds.

### Open-world routing and time-localized multi-label evidence

The next no-label extension is implemented in the companion execution plan
and GPU0 receipt. A seven-way domain router dispatches each file toward a
music/sample, speech/voice, environmental/SFX, animal, mechanical, ambience,
or unknown/mixture specialist. The router is deliberately coarse and
uncalibrated; its value is preventing a music model from judging every sound.

For the 500 highest-priority review files, an energy-window manifest produced
2,076 candidate windows. The segment classifier then scored every window with
the music specialist and retained multiple strongest labels per file with
timestamps. The receipt is
`tools/classification_benchmark/receipts/gpu0_segment_classifier_500_20260913.jsonl`:
1,156 windows passed the suggestion gate, 920 remained review, and no window
failed decoding. File-level output was 324 suggest / 176 review. This is a
retrieval and triage capability, not universal classification: labels remain
null, scores are uncalibrated, and approval is required.

The hand-off packet builder
`tools/classification_benchmark/build_label_free_evidence_packet.py` joins the
ensemble, domain route, physical card and segment receipt by logical path.
The resulting GPU0 packet contains 8,621 ensemble rows, with 500 rows carrying
the full physical and time-localized evidence bundle. It is the intended input
for a review UI or query service and retains the same no-mutation contract.
The native bridge in `Source/LabelFreeEvidencePacket.h` parses this contract
without importing it into the taxonomy or write-action paths, and its test has
passed against the real packet.
The standalone Library menu now offers `Import AI Evidence...`, projecting the
packet into the existing results overlay for review and playback selection
while leaving all write paths untouched.
The specialist runner now dispatches the router's domain signal to configurable
prompt banks rather than reusing the music bank for every sound; its first GPU0
pilot covered 500 files across music, SFX, machinery, speech and ambience.
Rescoring those files with the second checkpoint and requiring specialist-label
agreement reduced the retained suggestion tier to 80/500, giving the review UI
a domain-specific reliability signal without manufacturing ground truth.
The accompanying per-domain scorecard reports agreement and coverage for
threshold tuning but explicitly allows no auto action until measured labels
establish precision.

A corpus-wide one-view specialist pass subsequently scored 8,587/8,622 routed
files (35 unknown/abstained; 5,679 suggestion-gated). Its scorecard is retained
as coverage evidence only; the stricter two-model, three-view gate remains the
recommended promotion boundary for any future auto tier.
Structured filename candidates are now an optional packet field validated at
the JUCE boundary and shown as review text; no candidate can become a rename
without an explicit, separately audited approval action.
Both a 500-row physically enriched packet and a corpus-wide named packet are
available for the review UI.
The same uncertainty queue now accepts routed specialists directly, ranking
the 2,943 full-corpus review candidates for active learning without treating
uncalibrated similarity as truth.
The localhost review workspace can load the packet directly and append typed
filename decisions bound to the packet's candidate, creating an auditable
feedback stream without serving or modifying source audio.
Those decisions now feed a Wilson lower-bound calibration report with domain
and corpus slices; it remains advisory until an owner explicitly promotes a
qualified slice.
An evaluation against the existing verified drum CSV found 68.7% suggestion
precision overall (95% lower bound 60.3%) and 80.4% for the music slice (lower
72.0%) on 149 exact supported labels. The result confirms that open-world
routing and specialist prompts need another calibration cycle before any
automatic naming tier.
The evaluator also separates specialist error from routing error: 25 of the
149 scorable rows were routed to a bank that could not express the verified
class, so the next cycle must improve the router before widening prompt banks.

## Sources

### Internal evidence

- A1. NITE DSP. [`SLO_AUDIO_CLASSIFICATION_PLAN_V3_MEASURED.md`](../../../../../SLO_AUDIO_CLASSIFICATION_PLAN_V3_MEASURED.md). 2026.
- A2. NITE DSP. [`SLO_BREADTH_311_LABEL_EVALUATION_V1.md`](SLO_BREADTH_311_LABEL_EVALUATION_V1.md). 2026.
- A3. NITE DSP. [`SLO_BREADTH_MODEL_CANDIDATE_V1.md`](SLO_BREADTH_MODEL_CANDIDATE_V1.md). 2026.
- A4. NITE DSP. [`SLO_DOMAIN_GENERALIZATION_V1_REPORT.md`](SLO_DOMAIN_GENERALIZATION_V1_REPORT.md). 2026.
- A5. NITE DSP. [`SLO_OPERATING_POINT_EVALUATION_V1.md`](SLO_OPERATING_POINT_EVALUATION_V1.md). 2026.
- A6. NITE DSP. [`SLO_CURRENT_POLICY_GATE_AUDIT_V1.md`](SLO_CURRENT_POLICY_GATE_AUDIT_V1.md). 2026.
- A7. NITE DSP. [`SLO_PRODUCT_INSPIRATION_EXECUTION_PLAN_V1.md`](SLO_PRODUCT_INSPIRATION_EXECUTION_PLAN_V1.md). 2026.
- A8. NITE DSP. [`CURRENT_PIPELINE.md`](CURRENT_PIPELINE.md). 2026.

### Products and standards

1. Sononym. “[Similarity Search](https://www.sononym.net/docs/manual/similarity-search/).” Accessed 2026.
2. Ableton. “[Live 12 Release Notes](https://www.ableton.com/en/release-notes/live-12/),” “[Working with the Browser](https://www.ableton.com/en/live-manual/12/working-with-the-browser/),” and “[Sound Similarity Search FAQ](https://help.ableton.com/hc/en-us/articles/11386675465628-Sound-Similarity-Search-FAQ).” Accessed 2026.
3. Soundly. “[The Complete Sound Effects Platform](https://getsoundly.com/).” Accessed 2026.
4. Soundminer. “[Soundminer Product Tiers](https://store.soundminer.com/).” Accessed 2026.
5. Loopcloud. “[Your Guide to Producing with Loopcloud](https://www.loopcloud.com/cloud/blog/5123).” Accessed 2026.
6. XLN Audio. “[XO Interface Overview](https://support.xlnaudio.com/hc/en-us/articles/16920363887645-Interface-Overview).” Accessed 2026.
7. Algonaut. “[Atlas 2: Map](https://algonaut.audio/manuals/atlas/2_0_2/map.html).” Accessed 2026.
8. Waves. “[Introducing COSMOS](https://www.waves.com/introducing-cosmos-sample-finder).” Accessed 2026.
9. Splice. “[Similar Sounds](https://splice.com/blog/introducing-similar-sounds/),” “[Search with Sound](https://support.splice.com/en/articles/9953890-how-to-use-search-with-sound-in-studio-pro),” and “[Describe a Sound](https://support.splice.com/en/articles/13764370-how-to-use-describe-a-sound-in-the-splice-desktop-app).” Accessed 2026.

### Research and datasets

10. Elizalde et al. “[CLAP: Learning Audio Concepts From Natural Language Supervision](https://arxiv.org/abs/2206.04769).” 2022.
11. Chen et al. “[BEATs: Audio Pre-Training with Acoustic Tokenizers](https://arxiv.org/abs/2212.09058).” 2022.
12. van Merriënboer et al. “[Perch 2.0: The Bittern Lesson for Bioacoustics](https://research.google/pubs/perch-20-the-bittern-lesson-for-bioacoustics/).” 2025.
13. Wang, Vaze and Han. “[Dissecting Out-of-Distribution Detection and Open-Set Recognition](https://arxiv.org/abs/2408.16757).” 2024.
14. Google Research. “[AudioSet](https://research.google.com/audioset/index.html).” Accessed 2026.
15. Fonseca et al. “[FSD50K: An Open Dataset of Human-Labeled Sound Events](https://arxiv.org/abs/2010.00475).” 2020.
