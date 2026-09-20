# SLO end-goal execution plan

## Goal

Turn an arbitrary audio library into a searchable, consistently named
catalogue with the highest practical correctness, while preserving an honest
`unknown`/`review` state for ambiguous audio. The system must never convert an
uncalibrated model score into an automatic rename.

The product contract is:

1. identify the audio's broad domain and source/family;
2. identify event/role and form independently;
3. infer physical attributes such as pitch, duration, tempo, brightness,
   noisiness, envelope and spatial width;
4. compose a deterministic human-readable name from those fields;
5. show evidence and alternatives;
6. rename only after a measured policy gate and explicit approval (or a very
   narrow, separately authorized auto tier).

“Correctly name everything” is not a defensible technical promise: mixtures,
ambiguous taxonomy boundaries, malformed files and sounds outside the ontology
do not have one objectively correct name. The correct product behaviour for
those cases is a useful explanation plus abstention.

## Naming contract

Store structured fields first; render a filename second:

```text
<family>_<role>_<form>_<pitch-or-key>_<tempo>_<descriptors>_<variant>.<ext>
```

Each field has an explicit `unknown` value and provenance. For example:

```json
{
  "domain": {"value": "music_sample", "source": "model_ensemble", "confidence": 0.98},
  "family": {"value": "drum", "source": "model_ensemble", "confidence": 0.96},
  "role": {"value": "kick", "source": "model_ensemble", "confidence": 0.94},
  "form": {"value": "one_shot", "source": "physical_evidence", "confidence": 0.82},
  "pitch": {"value": "unknown", "source": "pitch_detector", "confidence": 0.08},
  "attributes": ["low_end_heavy", "mostly_mono"],
  "name_state": "suggested"
}
```

Never collapse `Foley`, `Impact`, `Percussion`, `Loop` and `One-Shot` into one
flat class. They answer different questions and must remain independent axes.

## Evidence stack

### Ingestion and identity

- recursively discover supported audio and exclude sidecars;
- record complete-file hash, container metadata and decoder errors;
- group exact duplicates before training, retrieval or renaming;
- decode bounded windows and retain a failure receipt for every skipped file.

### Acoustic evidence

- music-tuned CLAP for producer-language concepts;
- generic CLAP for broader sound concepts and disagreement detection;
- a non-language acoustic encoder (BEATs/Perch/PANNs successor) for timbre and
  out-of-domain robustness;
- multi-view inference (full, early and late windows);
- physical definition cards for duration, onset density, periodicity, pitch,
  spectrum, envelope, clipping and stereo width;
- nearest-neighbour vectors for query-by-example and duplicate-family support.

### Name and metadata evidence

- parse filenames and folder names only as weak provenance evidence;
- normalize aliases (`bd`, `bass drum`, `kick`) through a controlled lexicon;
- treat embedded metadata as a separate source with its own provenance;
- require acoustic and/or physical corroboration before a name can pass an
  action gate.

## Decision policy

Use three tiers:

| Tier | Behaviour | Requirement |
|---|---|---|
| Evidence | show candidates, attributes, neighbours and reasons | no calibration required |
| Suggest | propose a structured name; user approves | calibrated class/domain gate |
| Auto | rename through preview, journal, verify and undo | very high precision lower bound on unseen collections |

The current GPU0 ensemble is evidence/suggestion only. Its 1,594 surviving
rows are the intersection of two uncalibrated models and three waveform views;
they are not auto-rename candidates yet.

## Minimal calibration, not exhaustive labelling

Human ear labels cannot be eliminated if the requirement is *correct* names.
They can be minimized by active learning:

1. start with the current 500-row disagreement queue;
2. label only the independent axes that matter for the requested action;
3. oversample model disagreement, boundary pairs, OOD candidates and new
   collections, while retaining a random audit slice;
4. fit class- and collection-aware calibration on development data;
5. freeze a sealed final set that is never used for tuning;
6. promote only when the lower confidence bound for precision clears the
   product promise on unseen collections.

Corrections from approval are valuable labels, but they become training data
only after the user confirms the correction and the duplicate/collection split
is recorded.

## Evaluation gates

Every release should report, separately for random, collection-held-out and
vendor-held-out splits:

- exact role precision and recall;
- structured-name exact match and field-level accuracy;
- top-five retrieval usefulness;
- abstention/selective risk curve and coverage;
- OOD false-known rate;
- duplicate-family consistency;
- boundary-pair confusion;
- filename-only versus audio-only versus fused evidence;
- collision/undo rate and scan latency.

Suggested first auto tier: only classes and collections whose one-sided 95%
precision lower bound is at least 99.5% on sealed held-out data, with a hard
OOD/rejection gate and zero unresolved name collisions. The threshold is a
product promise to be agreed, not a result currently demonstrated.

## Execution sequence

### Phase A — catalogue foundation

- finish the local-first evidence schema and deterministic name renderer;
- persist model/version, prompt bank, physical feature version and content hash;
- wire the current similarity index and disagreement queue into the review UI;
- make every action previewable, journalled and undoable.

### Phase B — attribute enrichment

- run physical definition cards over the corpus;
- add pitch/key, transient/form and rhythm heads with explicit confidence;
- add a third non-language encoder and compare its disagreements with CLAP;
- build per-collection normalization and OOD diagnostics.

### Phase C — sparse calibration

- review the active 500-row queue, starting with the highest disagreement;
- target boundary pairs and unseen collections rather than more familiar kicks;
- calibrate selective thresholds and measure the release gates above.

### Phase D — controlled naming

- enable structured-name suggestions for calibrated slices;
- require approval for every suggestion while collecting corrections;
- introduce auto actions only for slices that clear the statistical gate;
- continuously sample audits and immediately downgrade a slice after drift.

## Current evidence and next concrete action

Already available:

- label-free multi-view CLAP receipt;
- independent-model agreement receipt;
- two ranked review queues;
- normalized 512-D similarity index and query tool;
- physical definition cards for the highest-priority review queue;
- structured-name candidates that combine model and physical evidence;
- seven-way open-world domain-router receipt for specialist dispatch;
- time-localized segment manifest for routed event analysis;
- time-localized multi-label specialist receipt for 500 files / 2,076 windows;
- joined evidence packet combining ensemble, route, physical and segment data;
- configurable open-world specialist prompt banks and a GPU0 routed pilot;
- independent-model specialist agreement gate for routed domains;
- per-domain evidence-quality scorecard with explicit no-accuracy claim;
- corpus-wide routed specialist receipt (8,587/8,622 scored in one-view
  coverage mode) and full-corpus scorecard;
- optional full-corpus evidence packet joining that specialist receipt while
  retaining the stricter 500-file physical/segment bundle;
- packet-level structured filename candidates with native validation and
  review-only rendering;
- specialist uncertainty queue over the 2,943 full-corpus review candidates;
- append-only feedback events for accepting, correcting or rejecting a
  structured filename candidate (still no rename action);
- localhost review workspace evidence-packet mode with candidate binding;
- Wilson-bound name calibration report over reviewed decisions, with explicit
  minimum-sample and no-auto-action gates;
- review workspace endpoint for the advisory calibration report;
- packet-hash binding so calibration cannot mix evidence revisions;
- measured specialist evaluation against explicit verified labels (149-row
  defensible intersection; no slice currently clears an auto gate);
- threshold sweep identifying a 41-row high-confidence review slice for the
  next calibration sample;
- explicit routing-error accounting (25 verified rows were sent to a domain
  bank that cannot express their class);
- configurable router prompt-bank experiment, with a paired 237-file GPU0
  evaluation showing v2 below the built-in v1 baseline (80.6% vs 84.4%
  expected-domain routing and 84.6% vs 90.3% confident-suggestion precision);
- deterministic 500-row stratified calibration manifest spanning 25
  collections, with reserved disagreement, boundary, non-music and random
  audit lanes and no labels created;
- calibration sampling now rejects duplicate packet paths, removes exact-content
  aliases, and excludes the configured sealed-holdout collections (including
  matching content hashes) before any owner review;
- review-workspace `/api/calibration-sample` exposure with lane/domain filters,
  retaining the no-audio/no-mutation contract;
- calibration rows are now hash-bound to the loaded evidence packet and expose
  only bounded read-only candidate evidence for adjudication;
- the legacy v1 calibration manifest is rejected; the current v2 handoff is
  `tools/classification_benchmark/receipts/gpu0_label_free_calibration_sample_500_20260914_v2.json`;
- conservative open-world fusion receipt requiring route, base-model and
  specialist agreement before producing a candidate (21/21 correct on the
  149-row exact-label intersection at 14.1% coverage; review-only);
- full named evidence packet with the fusion decision joined at 8,621/8,621
  coverage for direct review-workspace consumption;
- open-world domain candidates retained separately for 947 non-music rows,
  with explicit review-only scope instead of forced music-taxonomy labels;
- broader merged verified-sample evaluation (225 exact supported-label rows;
  35/35 suggestions correct, 90.1% Wilson lower bound at 15.6% coverage),
  with path overlap and conflicting-label exclusions reported;
- specialist-gate ablation (36/36, 90.4% Wilson lower bound) retained as
  research evidence; the stricter gate remains default for open-world safety;
- append-only fused-candidate feedback events and a packet-hash-bound
  domain/scope calibration report, still with no automatic promotion;
- corpus-relative leave-one-out embedding novelty gate, with 95 outliers
  flagged and 16 high-novelty suggestions downgraded to review;
- native review overlay now displays fusion scope, novelty score and explicit
  OOD-review markers for those overrides;
- verified OOD distribution audit: 0/90 fused suggestions exceeded the novelty
  gate, versus 7/84 unknown-domain rows;
- native JUCE read-only packet parser with a real-packet verification test;
- standalone Library > Import AI Evidence review report;
- standalone runtime smoke confirmed the Library menu exposes the importer and
  opens the file-selection path; imported packets remain review-only;
- native evidence review now prioritizes explicit review/unknown-domain and
  OOD rows, then lowest-agreement evidence, so the first visible queue is the
  most informative calibration slice;
- completed 120-row Clap/Kick/Snare validation is now consumable by the nested
  collection-held-out recalibration audit; the corrected receipt retains the
  one out-of-scope `Vocal One-Shot` negative and remains review-only;
- a second, path-disjoint validation handoff is prepared at
  `tools/classification_benchmark/class_conditional_gate_validation_manifest_v2.json`
  (72 remaining candidates after duplicate and prior-batch exclusion);
- read-only safety receipts and focused regression tests.

The next implementation unit is to collect owner-approved decisions for the
stratified calibration manifest, then freeze a sealed holdout and fit
class/domain selective-risk gates. Phase A wiring remains review-only: render a
structured candidate name from the ensemble plus physical definition card and
segment evidence, show the evidence packet, and keep every action behind
explicit approval. This preserves the no-ear-label mode while creating the
smallest defensible path to a calibrated auto tier.

For the current 72-row class-gate handoff, a strict filename/folder-blind
review bundle is staged at
`products/slo/_artifacts/slo_strict_blind_class_gate_v2/review_queue.csv`.
The evaluator-only candidate mapping is separate and content-hash-bound;
embedded audio metadata is explicitly not stripped. Labels remain blank until
owner adjudication.

The first renderer is now available at
`tools/classification_benchmark/render_label_free_name.py`. It emits a
review-only candidate packet with stable content-id suffixes, making potential
name collisions visible before any action is considered.

The joined evidence hand-off is available at
`tools/classification_benchmark/receipts/gpu0_evidence_packet_8621_20260913.json`.
It is intentionally a review data contract, not a metadata import: downstream
UI code must preserve its `semantic_label: null` and approval state.
The standalone app now exposes that contract through `Library > Import AI
Evidence...`; it displays the highest-agreement rows in the existing results
overlay and keeps selection/playback separate from all write actions.

## Expanding from sample packs to “anything audio”

The universal version should be an open-world router, not a single flat
classifier. A broad event ontology is useful as a shared backbone—Google's
AudioSet currently describes 632 event classes—but SLO's producer taxonomy
should remain a separate specialist branch. The router should select experts
conditionally:

| Domain signal | Specialist evidence |
|---|---|
| music/sample | music CLAP, instrument/event heads, tempo/key/form |
| speech/voice | speech activity, language ID and ASR transcript |
| environmental/SFX | general acoustic encoder and multilabel event detection |
| animal/bioacoustic | bioacoustic encoder and species/event branch |
| mechanical/industrial | machine-sound anomaly and tonal/impulsive heads |
| unknown/mixture | retrieval, captioning and explicit OOD/rejection |

Every expert returns time-localized, multi-label evidence plus an abstention
score. A clip may therefore be `speech + traffic + background_music`, or
`kick + distortion`, instead of being forced into one class. Captions and
natural-language retrieval are explanations and search surfaces; they are not
ground truth. Speech transcription is a separate privacy- and
retention-controlled product path.

The training ladder is:

1. self-supervised pretraining on the unlabeled SLO corpus;
2. public weakly labelled pretraining and ontology alignment;
3. specialist adapters for music, speech, SFX, bioacoustics and machinery;
4. sparse active human calibration on disagreements and OOD cases;
5. collection-held-out calibration and selective auto-action gates.

New clusters that repeatedly fall outside the ontology become candidates for a
new specialist or taxonomy addition, never an automatic rename class.

Temporal evidence now covers the complete GPU0 packet. The packet-driven
manifest `tools/classification_benchmark/receipts/gpu0_segment_manifest_full_8621_20260914.json`
contains 8,621 files and 36,281 non-semantic windows with zero decode errors.
Global window batching and one-resample-per-source processing produce the
matching `gpu0_segment_classifier_full_8621_20260914.jsonl` receipt, scoring
all 36,281 windows; 7,391 files have at least one review-only segment
suggestion. The integrated hand-off is
`gpu0_evidence_packet_full_named_ood_gated_segments_8621_20260914.json`, with
ensemble, domain, specialist, name, fused/OOD and temporal coverage for all
8,621 rows. Segment prompt similarity remains uncalibrated evidence for
review/routing, never semantic ground truth or automatic action authority.
The first temporal aggregation audit is recorded in
`gpu0_segment_classifier_eval_merged_verified_20260914.json`: on the 225-row
exact supported-label overlap, file-top and score-sum temporal voting both
scored 178/225 (79.11% precision; 73.33% Wilson lower bound). Windows therefore
provide useful localization but are not yet an accuracy improvement; a learned
or calibrated temporal fusion gate remains future work.

Unsupervised discovery is available through
`tools/classification_benchmark/build_label_free_cluster_manifest.py`. Running
DBSCAN over the normalized 8,621-file CLAP index produced 153 cluster
hypotheses and 3,527 noise/outlier rows in
`gpu0_label_free_cluster_manifest_8621_20260914.json`. These assignments can
surface recurring sounds outside the current prompt ontology and guide new
specialists, but remain unnamed until reviewed or independently calibrated.
They are joined into the evidence packet as `cluster_discovery` and cannot
authorize an action.
The native read-only evidence overlay now shows cluster IDs/sizes or an
explicit discovery-noise marker when this evidence is present.
The ranked queue
`tools/classification_benchmark/build_label_free_cluster_review_queue.py`
prioritizes the 100 most useful cluster/noise groups using size, non-music
route concentration and packet coverage, with representative files for each
group. This is the review input for adding a specialist or taxonomy branch;
cluster IDs are never promoted directly to labels.
The companion audit
`tools/classification_benchmark/audit_label_free_cluster_specialist_proposals.py`
then ranks route and specialist actions: in the current 100-group queue it
flags 39 groups for new-specialist/ontology review, one for router improvement,
one noise bucket, and 59 as consistent with an existing specialist. These are
review and model-development priorities, not automatically generated labels.
The prompt-proposal generator
`tools/classification_benchmark/build_label_free_specialist_prompt_proposals.py`
converts representative filenames into repeated lexical hints and acoustic
prompt templates. The hints are frequency-filtered, weak evidence for drafting
specialist experiments, never ear labels or promoted training targets.

An optional supervised-reference retrieval branch is implemented in
`tools/classification_benchmark/build_label_free_retrieval_evidence.py`. It
requires matching model identity metadata and rejects dimension-only matches,
which prevents mixing CLAP and PANNs vectors. Using a music-CLAP reference
index with exact filename overlaps excluded, the strict 0.98 similarity tier
produced 485 corpus suggestions; on the 492-row merged-label overlap it yielded
31 suggestions, 27 correct (87.10% observed precision; 71.15% Wilson lower
bound). It is therefore review-only evidence, not part of the conservative
fused auto boundary. The native parser/overlay exposes its candidate and
similarity, and the retrieval evidence is joined in the full packet.
