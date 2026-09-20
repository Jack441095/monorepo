# SLO competitive research and end-state architecture plan V1

Date: 2026-09-12

## Executive decision

SLO should not try to win by becoming a single, ever-larger classifier that
forces every file into one class. The strongest sample and sound-effects
products combine several weaker but complementary capabilities: fast local
indexing, query-by-example, editable tags, physical audio filters, natural-
language retrieval, standards-aware metadata, and non-destructive auditioning.

The recommended end state is an **evidence-backed audio librarian** with four
distinct promises:

1. **Find:** retrieve useful sounds even when their filenames and predicted
   classes are wrong.
2. **Understand:** describe source, form, behaviour, and measurable acoustic
   properties without pretending every descriptor is equally certain.
3. **Organise:** suggest editable tags, collections, canonical duplicate groups,
   and standards-compatible metadata.
4. **Rename safely:** produce deterministic previews and mutate files only for
   independently qualified class/policy combinations, with a journal and undo.

This direction fits both the market evidence and SLO's own experiments. SLO's
current frozen Perch+CLAP nearest-centroid system reached **68.60% ± 0.46
collection-held-out accuracy**, **63.95 macro-F1**, and reduced `Other/none`
false accepts from **36.59% to 18.70%** after broad human labelling. Generic
model changes, fine-tuning, domain methods, augmentation, and flat factorised
classifiers have not cleared the project's +2 percentage-point promotion gate.
The product can nevertheless become substantially more useful before perfect
classification because retrieval, evidence, correction, and safe metadata do
not require a universally correct top-1 class.

## 1. What “high-end” should mean

High-end audio classification is not a single accuracy number. For SLO it should
mean all of the following:

- a result remains credible when an entire unseen vendor or collection is held
  out;
- the system can abstain and preserve `unknown`, `not enough information`, and
  `taxonomy gap` as different outcomes;
- music-sample concepts are represented on separate axes such as family, form,
  role, pitch, envelope, spectrum, rhythm, and processing;
- filenames, waveform measurements, embeddings, public-model suggestions, and
  human labels remain separate evidence sources with provenance;
- search remains valuable when the semantic label is uncertain;
- duplicate identity is resolved before similarity or renaming;
- every proposed name explains which evidence supplied each token;
- no automatic rename is enabled merely because a neural score is high;
- source audio is immutable by default, and every mutation is previewed,
  collision-checked, journalled, and reversible;
- the product has measured workflow value: less time to find a sound, fewer
  wrong suggestions, fewer corrections, and zero silent data loss.

The distinction matters. A browser can be excellent at finding “something like
this dark short kick” without knowing the one philosophically correct class.
Conversely, a classifier can have acceptable average accuracy while still being
unsafe to rename files on a new vendor pack.

## 2. Current SLO position

### 2.1 What is already strong

- The evaluation protocol now holds out whole collections and prevents exact-
  duplicate leakage. This replaced the old random cross-validation number,
  which overstated product performance by 9.7 percentage points.
- The incumbent is deliberately simple: nearest centroid over frozen Perch and
  CLAP embeddings. Its simplicity makes it auditable and robust under the
  measured domain shift.
- Breadth-first labelling is validated. Collection breadth has yielded roughly
  **+4.47pp per doubling of collections**, compared with **+1.81pp per doubling
  of labels**.
- The rejection boundary improved materially. On the wider corpus, mapping
  non-drum labels to rejection reduced false acceptance to **14.0%**.
- Physical definition cards, multi-window measurements, content hashes,
  duplicate groups, aspect similarity, correction types, and fail-closed rename
  planning already exist in research or shadow form.
- A full read-only qualification of 28,330 files produced 4,071 suggestions,
  19,949 reviews, 4,310 never-act rows, and **zero automatic renames**. That is
  the correct behaviour for the present evidence.

### 2.2 What remains weak

- Top-1 family classification on unseen collections is not yet reliable enough
  to act as file truth.
- Remaining errors are dominated by world coverage and the rejection boundary,
  not by an obviously missing generic encoder.
- Some labels describe heterogeneous buckets rather than coherent sound
  concepts. `Other/none` may be heterogeneous by design, but Percussion, Foley,
  SFX, Bass Hit, and several loop classes need careful semantic treatment.
- Current confidence is systematically optimistic on unseen collections.
- Dedicated human validation produced 39/40 Clap, 40/40 Kick, and 40/40 Snare,
  but their 95% Wilson lower bounds were only 87.12%, 91.24%, and 91.24%.
  None can yet support a 95%-precision automatic-action claim.
- The 210 MB model-delivery decision remains a deployment constraint.

### 2.3 Routes that should not be repeated without a new mechanism

- random cross-validation;
- class balancing as a general labelling policy;
- generic pack-mastering augmentation;
- LoRA as a presumed domain-generalisation fix;
- BEATs, Dasheng, MERT, or AST bake-offs simply because they are established
  public models;
- a coarse-to-fine cascade that uses the same unreliable family decision as its
  first gate;
- clustering as an automatic taxonomy generator;
- similarity score as class probability;
- filename tokens as labels;
- pseudo-labels promoted directly into ground truth.

BEATs is a particularly useful warning: despite excellent published general
audio benchmark results, SLO measured it at 47.30% collection-held-out versus
64.90% for the controlled Perch+CLAP incumbent, and the combined representation
was 1.57pp worse. Public benchmark strength does not guarantee fitness for
short, isolated, vendor-pack samples.

## 3. Competitive product comparison

The products below solve different jobs. The “lesson for SLO” column is an
architectural interpretation, not a claim made by the vendor.

| Product | Primary job | Officially documented strengths | Structural limitation for SLO's goal | Lesson for SLO |
|---|---|---|---|---|
| **Sononym** | Local sample discovery | Machine-learning similarity search; independent Overall, Spectrum, Timbre, Pitch, and Amplitude aspects; loop/one-shot and class filters; non-destructive library workflow | Primarily a retrieval/browser experience, not a statistically qualified naming authority | Make similarity multi-aspect and user-steerable; never disguise it as semantic certainty |
| **Ableton Live 12** | DAW-integrated browsing | Background analysis; similarity search; automatic tags for user samples up to 60 seconds; editable user tags, nested tags, filters, saved labels; pauseable analysis | Bound to a DAW and its workflow; one best-match auto-tag does not expose a full evidence model | Background indexing, visible status, editable machine suggestions, and search history are product essentials |
| **Soundly** | Professional SFX discovery and delivery | Natural-language and keyword search; related searches, autocomplete, thesaurus and translation; local/cloud libraries; spectrogram; collections; editable metadata; UCS 8.2.1 support and UCS renaming | Optimised for search and professional metadata workflow rather than proving acoustic top-1 class accuracy | Combine language, synonyms, metadata, and audio; treat UCS as an interoperability layer |
| **Soundminer** | Professional sound-asset database | Deep metadata editing and embedding; advanced fielded search; UCS extraction/suggestion; workflows, batch conversion, waveforms and production-tool integration | A metadata-centred professional system; quality depends heavily on supplied metadata and curated workflows | Metadata must travel with the asset; naming should be a deterministic workflow built from structured fields |
| **Loopcloud** | Sample-store and personal-library workflow | Automatic analysis/tagging; instrument/genre/key/BPM filters; loop/one-shot distinction; length, tone, rhythmic density and stereo-width filters; similar, rhythmic and harmonic matching; DAW-synchronised preview | Cloud/store-centred and oriented to creative discovery; commercial tags are not independently calibrated truth | Add physical facets and separate “similar,” “rhythmic match,” and “harmonic match” intents |
| **Waves COSMOS** | Simple sample organisation | Brings one-shots and loops into one searchable place, AI auto-tags them, and supplies a visual discovery workflow | Black-box categorisation offers limited evidence and no demonstrated safe-rename policy | Low-friction automatic organisation is valuable, but SLO should add provenance and abstention |
| **XLN Audio XO** | One-shot drum exploration | Detects one-shot drum samples, arranges them in a similarity space, offers a nearest-similarity list, history and favourites | Intentionally narrow: one-shot drums rather than loops, tonal material, or general SFX | A narrow, excellent mode can outperform a universal but vague experience; retain a dedicated drum workflow |
| **Algonaut Atlas 2** | Drum map and kit creation | Sonic similarity map, categories, hover audition, kit generation, manual category correction, resumable analysis | Long samples and loops may be excluded because they interfere with its drum workflow | Different forms need different analysis and UI paths; manual correction must be immediate |
| **Splice** | Cloud catalogue discovery | Tagged catalogue, Similar Sounds, and sound-as-query workflows that can return compatible samples beyond pack/tag boundaries | Not a local-library governance or safe-renaming system | Audio-to-audio retrieval is a core value surface independent of exact labels |

### 3.1 Where SLO can be genuinely differentiated

No compared product, based on its public documentation, combines all of these
in one local-first system:

- collection-held-out evaluation and explicit domain-shift reporting;
- independent evidence provenance for name, waveform, embedding, model and
  human claims;
- factorised descriptions that preserve unknown values;
- typed taxonomy-gap feedback;
- hash-first duplicate identity with path aliases;
- statistically qualified, class-specific action policies;
- deterministic rename previews, approval receipts, collision protection,
  mutation journal, and undo.

SLO should not try to out-market established browsers on catalogue size. Its
defensible position is **the local audio librarian that shows its work and does
not damage the library**.

## 4. Research and open-data comparison

### 4.1 AudioSet: vocabulary and broad teacher, not SLO ground truth

Google's AudioSet provides a hierarchical ontology of 632 audio-event nodes and
2,084,320 human-labelled ten-second clips, with 527 classes represented in the
released dataset. It spans human, animal, music, and environmental sounds. The
ontology includes stable IDs, display names, descriptions, synonyms, child
relationships, positive examples, and restrictions.

Use it for:

- vocabulary discovery and parent/child mappings;
- zero-shot candidate prompts;
- a dormant real-world branch covering animals and environmental events;
- auxiliary multi-label teacher output;
- identifying concepts that are difficult for human annotators.

Do not use it as a direct replacement for SLO labels. Ten-second web-video
events are materially different from isolated production samples, designed
impacts, processed drums, stems, loops, and vendor naming conventions.

### 4.2 FSD50K: open examples for environmental and musical events

FSD50K contains 51,197 human-labelled Freesound clips across 200 AudioSet
classes and more than 100 hours of audio. It is a practical source for testing
whether a dormant real-world branch can distinguish broad sources such as
animals, vehicles, materials, weather, and human actions.

Its best role is **auxiliary evaluation and representation probing**. Licence,
provenance, class balance, recording context, and domain mismatch must be
checked per intended use. It should not be silently mixed into the commercial
training corpus.

### 4.3 HEAR: how to evaluate representations rather than chase leaderboards

HEAR evaluates general audio representations across 19 tasks spanning speech,
environmental sound, and music, with both scene and timestamp embeddings. Its
API explicitly separates whole-clip embeddings from temporal embeddings.

The relevant lesson is architectural: SLO needs both.

- **Scene embeddings** support broad semantic retrieval and whole-file family
  evidence.
- **Timestamp embeddings** support onset count, event sequence, loop/phrase
  structure, mixed-content detection, and explanations tied to regions.

HEAR should be used as a screening reference. SLO's collection-held-out product
benchmark remains the promotion authority.

### 4.4 CLAP and language-audio teachers

CLAP places audio and natural-language descriptions in a shared embedding
space, enabling flexible zero-shot queries beyond a fixed class list. This is
valuable for search prompts, alternative descriptions, taxonomy-gap triage and
weak auxiliary tags. SLO already benefits from CLAP as part of its incumbent.

Language-audio similarity should not be converted directly into a filename.
Prompt wording, abstract concepts, and domain bias make it a retrieval score,
not a calibrated statement of identity.

### 4.5 UCS: the output standard for sound effects

The Universal Category System is a public-domain initiative defining a common
sound-effects category list, filename structure, and supporting synonyms. The
current public release is UCS 8.2.1. It is already supported by professional
tools such as Soundly and Soundminer.

SLO should map its real-world/SFX branch to UCS IDs and fields at export time.
It should not flatten its internal music-sample concepts into UCS where the
fit is poor. Internal evidence may be richer and factorised; UCS is the
interchange view.

## 5. The end-state architecture

```text
immutable audio + path aliases
            |
            v
  [1] identity and ingest
      full SHA-256, format, duration, collection/vendor, metadata
            |
            v
  [2] multi-window analysis
      full clip | onset windows | regular timestamp windows | tail
            |
            v
  [3] independent evidence producers
      filename/path    physical DSP    audio embeddings
      public teachers human claims     duplicate/near-duplicate evidence
            |
            v
  [4] factorised evidence record
      domain | source/family | form | role/event | acoustic attributes
      provenance | confidence | disagreement | unknown reason
         /                 |                    \
        v                  v                     v
 [5a] retrieval       [5b] tag suggestion    [5c] policy engine
 lexical/vector/      editable multi-label   calibration/abstention/
 aspect/filter search collections            class qualification
                                                   |
                                                   v
                                           [6] naming and action
                                           preview -> approve -> journal
                                           -> apply -> verify -> undo
```

### 5.1 Layer 1: immutable identity and ingest

Use complete-file SHA-256 as content identity, with every observed path retained
as an alias. Store source collection/vendor separately from folder position.
Never let moved files create new training examples or fill similarity results
with exact copies. Parse embedded BWF/iXML/ID3-style metadata without trusting
it as acoustic truth.

Required properties:

- resumable and incremental scans;
- cache keys include content hash, analyser version, model version and window
  strategy;
- failures are visible and retryable;
- disconnected drives preserve catalogue records but clearly show unavailable
  audio;
- no source mutation during analysis.

### 5.2 Layer 2: multi-window waveform analysis

A single mean-pooled whole-file vector cannot define all sample forms. Analyse:

- the complete clip;
- an onset-centred short window for transient identity;
- an early-body window for pitch and timbre;
- regular timestamp windows for event changes and repetition;
- the tail for decay, ambience and effects;
- detected active regions separated from leading/trailing silence.

Physical measurements should include, where meaningful:

- duration, active duration and silence ratio;
- onset count, onset spacing, periodicity, estimated tempo and rhythmic density;
- attack, decay, sustain stability and tail length;
- spectral centroid, rolloff, bandwidth, flatness, low/mid/high energy ratios;
- fundamental-frequency track, pitch confidence, pitch stability, key/chroma
  confidence and glides;
- loudness, crest factor, dynamic range and clipping;
- stereo width, correlation and channel count;
- harmonic/noise/transient balance.

These are evidence, not universal definitions. For example, “drum loop” should
be supported by repeated percussive events across time and more than one event
or timbral role, but a sparse tom loop may have few onsets and a layered single
impact may have several onsets. The semantic claim comes from combining physical
evidence with learned context and uncertainty.

### 5.3 Layer 3: independent evidence producers

Every producer emits a claim with `value`, `score`, `source`, `model/version`,
`supporting regions`, and `known/unknown` state.

- **Name evidence:** tokenised filename/path, synonyms and vendor metadata.
  Strong for family hints, weak for form, and never a label.
- **Physical evidence:** deterministic measurements and derived rules.
- **Embedding evidence:** Perch/CLAP and any future promoted representation.
- **Public teacher evidence:** AudioSet/FSD/UCS-mapped suggestions, kept weak and
  explicitly out-of-domain.
- **Human evidence:** verified label, correction, taxonomy gap, ambiguity or
  note, with reviewer and timestamp.
- **Identity evidence:** exact duplicate and conservative near-duplicate links.

Disagreement is a feature. A filename saying `perc_loop` while temporal evidence
looks like a single hit is exactly the kind of item that should enter a targeted
review queue.

### 5.4 Layer 4: factorised representation

Do not replace the current proven flat classifier with the previously failed
coarse-to-fine cascade. Instead, add parallel descriptive heads and independent
unknown states:

| Axis | Example values | Why separate it |
|---|---|---|
| Domain | music sample, sound effect, speech, ambience, unknown | Prevents animal and field-recording concepts from destabilising the music branch |
| Source/family | drum, bass, synth, voice, animal, vehicle, material | Answers what generated the sound |
| Form | one-shot, loop, phrase, sustained, texture, recording, unknown | Prevents `hat` or `perc` from being asked to encode temporal form |
| Event/role | kick, snare, impact, riser, fill, call, movement | Captures functional identity |
| Pitch | pitched/unpitched, pitch, key, stability, confidence | Supports musical use without forcing unreliable key values |
| Envelope | impulsive, pluck, sustained, swelling, decaying | Generalises across instruments and real-world sounds |
| Spectrum/timbre | bright, dark, noisy, harmonic, low-heavy | Enables useful filtering and explanations |
| Rhythm | onset density, periodicity, BPM, groove signature | Supports loops and rhythmic matching |
| Spatial/processing | mono/stereo, dry/wet, reverberant, distorted | Separates production state from source identity |
| Provenance | human, name, DSP, model, imported metadata | Makes every output auditable |

A product description can then be assembled as “music sample / drum / loop /
dense / bright / dry” even if the exact drum subtype is uncertain. That is more
honest and often more useful than a forced `Hi-Hat Loop` label.

### 5.5 Layer 5a: retrieval as the first-class value surface

Implement four search modes that can be combined:

1. **Text and synonym search:** literal metadata plus a controlled vocabulary;
   unsupported terms remain visible instead of being hallucinated into filters.
2. **Structured facets:** family, form, BPM, key confidence, duration, brightness,
   low-end weight, transient density, stereo width, rejection state and source.
3. **Query by example:** content-deduplicated nearest neighbours.
4. **Intent-specific matching:** overall, spectrum/timbre, pitch/harmonic,
   amplitude/envelope, and rhythm/groove, each with a visible weight.

Results should explain the match: “92 spectrum, 81 envelope, 34 pitch,” not just
“87% similar.” Search quality should be evaluated with retrieval metrics and
human usefulness, not classifier accuracy.

### 5.6 Layer 5b: editable multi-label suggestions

Present suggestions as removable chips grouped by axis. Machine and user tags
must look different and retain provenance. A user correction should be one of:

- accept;
- correct to an offered value;
- `not in list` with the missing value recorded;
- `not enough information`;
- `taxonomy gap` with a note;
- reject as unsupported/non-target audio.

Each event enters an append-only ledger. It may become a training candidate only
after identity verification, validation-set exclusion, duplicate checks and an
explicit promotion decision.

### 5.7 Layer 5c and 6: policy, naming and mutation

Keep four action tiers:

- **never act:** ambiguity, taxonomy gap, OOD, identity conflict, duplicate risk,
  model/version mismatch or unsupported evidence;
- **review:** insufficient or conflicting evidence;
- **suggest:** useful candidate name or tags, but owner confirmation required;
- **automatic:** only a class/policy combination whose independent validation
  lower confidence bound clears the promised precision.

The naming engine must be deterministic and independent of model inference. It
receives structured fields and a template such as:

```text
{family}_{event}_{form}_{pitch?}_{bpm?}_{descriptor?}_{index}
```

Every token must show its provenance. Before apply, validate current content
hash, source root, extension, destination collision, duplicate receipt, approval
receipt and plan signature. Write a journal before mutation; verify after; offer
undo. Metadata-only export should be available without renaming.

## 6. Training strategy

### 6.1 What to train next

Training should resume after the current breadth queue is complete and audited.
The first GPU job should be a **controlled incumbent rebuild**, not a new model
family:

1. freeze the exact expanded label manifest and collection groups;
2. exclude path aliases and seal validation collections;
3. rebuild Perch+CLAP features only where cache/model identity requires it;
4. fit the nearest-centroid incumbent and current calibrated alternatives;
5. report collection-held-out accuracy, macro-F1, per-class recall, rejection
   false accepts, calibration and coverage;
6. compare paired seeds against the frozen v2 receipt;
7. update no production policy unless a pre-registered gate passes.

GPU 1 may be used if it is free, but the remote machine must **not be restarted,
rebooted, or have unrelated processes killed**. Availability should be checked
read-only before a job, with a device-pinned process and durable logs/checkpoints.

### 6.2 Productive training experiments after the rebuild

Run only bounded, mechanism-specific experiments:

- **parallel attribute heads:** predict form, envelope, pitch presence,
  periodicity class and broad family as auxiliary outputs, without routing one
  head through another;
- **temporal pooling for loops:** compare whole-clip pooling against onset and
  timestamp aggregation specifically on one-shot/loop/phrase errors;
- **prototype memory:** compare class centroids, multiple prototypes per class,
  and content-deduplicated labelled-neighbour retrieval under the same grouped
  folds;
- **OOD/rejection model:** train explicit known-vs-rejection evidence using broad
  negative collections, measured primarily by false acceptance;
- **language teacher for missing vocabulary:** use CLAP/AudioSet prompts to rank
  taxonomy-gap candidates for human review, never as automatic gold labels;
- **name/audio disagreement model:** learn when filename evidence should be
  ignored, based on verified disagreements rather than generic token weights.

Each experiment needs a written hypothesis, a fixed incumbent, paired grouped
folds, a minimum material gain, and a rollback rule. Do not change more than one
mechanism at once.

### 6.3 How public datasets can reduce—not replace—labelling

Public data can help without pretending it matches the product domain:

- initialise broad real-world/animal/SFX vocabulary;
- train auxiliary domain/source heads;
- supply negative examples for music-sample rejection;
- test whether embeddings retain animal, vehicle, material and environmental
  distinctions;
- create a teacher shortlist for targeted review;
- test temporal event detection separately from sample-pack classification.

Keep public and SLO examples in separately reportable domains. Promotion is
based on SLO collection-held-out and sealed product validation, not a blended
headline metric.

## 7. Real-world sounds and animals

Real-world audio should remain a **dormant sibling branch**, not an immediate
expansion of the active classifier. A scalable hierarchy is:

```text
real-world
  animal
    mammal | bird | insect | amphibian | other/unknown
    vocalisation | movement | eating | wingbeat | group/chorus
  human
    speech | vocal non-speech | movement | crowd
  environment
    weather | water | fire | wind | ambience
  mechanical
    vehicle | engine | tool | appliance | mechanism
  material
    wood | metal | glass | fabric | liquid | earth
```

The crucial design is again factorisation. “Dog bark” is source `dog`, event
`bark`, form `one-shot or sequence`, plus distance, environment and processing.
“Bird ambience” is not merely `bird`: it may contain multiple sources and a
continuous scene. AudioSet can seed vocabulary and examples; UCS can supply the
professional export mapping; FSD50K can exercise the branch. No active music
policy should change until a separate dataset, benchmark and product requirement
exist.

## 8. Measurement programme

### 8.1 Classification and rejection

- collection/vendor-held-out accuracy and macro-F1;
- per-axis accuracy and missing-value rate;
- per-class precision/recall and confusion by collection;
- `Other/none` and OOD false-accept rate;
- expected calibration error and reliability plots;
- delivered precision and coverage at each action tier;
- 95% Wilson lower confidence bound for every auto-action class;
- performance on short/long, one-shot/loop, tonal/noisy and easy/hard slices.

### 8.2 Retrieval

- Recall@5/10 and mean reciprocal rank on labelled query sets;
- human “useful result in top 5” rate;
- duplicate-adjusted diversity of results;
- retrieval quality by overall, timbre, pitch, envelope and rhythm intent;
- median time and auditions required to find a usable sound.

### 8.3 Product safety and learning

- suggestion acceptance, correction, abstention and taxonomy-gap rates;
- percentage of suggested filename tokens with visible provenance;
- stale-cache, collision and identity-guard rejection counts;
- scan completion/retry time and cache hit rate;
- rename plan/apply/verify parity;
- zero unjournalled mutations and successful undo tests;
- label value by new collection, class boundary and evidence-disagreement bucket.

## 9. Phased execution plan

### Phase A — freeze and finish the evidence base

Status: in progress.

- Complete and audit the current 600-file breadth queue.
- Back up verified labels in at least two independent locations; decide whether
  encrypted/versioned ground truth should be tracked rather than left ignored.
- Seal collection-held-out validation sets and their hashes.
- Confirm all 28,330 source files have stable identity records and reconcile the
  partial acoustic-duplicate index.
- Preserve the current v2 incumbent receipt as the comparison point.

Exit gate: integrity-clean manifest, zero group leakage, zero unresolved label
escape records, reproducible baseline.

### Phase B — ship retrieval value in shadow/read-only form

Status: partially implemented.

- Consolidate identity, physical cards, model embeddings, name evidence and
  metadata into one versioned evidence index.
- Complete query-by-example in the product UI with aspect weights and explained
  scores.
- Add structured filters for form, length, pitch confidence, tempo, onset
  density, brightness, low end, stereo and rejection status.
- Add background-analysis state, pause/resume/retry and unavailable-drive state.
- Add search history, saved collections, favourites and typed corrections.

Exit gate: useful top-5 retrieval on a blind query set, no source mutation, and
stable incremental rescans.

### Phase C — controlled retraining and factor evidence

Status: waits for Phase A labels.

- Rebuild the incumbent on the expanded breadth corpus.
- Run the parallel attribute-head and temporal-loop experiments.
- Build a dedicated broad-negative/OOD evaluation set from new collections.
- Calibrate by collection using nested splits; keep raw and calibrated scores.
- Produce class cards with support count, collections, failure modes, confusion,
  delivered precision and eligible action tier.

Exit gate: a reproducible receipt and at least one pre-registered improvement
that passes its mechanism-specific gate, or an honest negative result.

### Phase D — suggestion-only naming beta

Status: safety foundations exist; product integration incomplete.

- Convert factor evidence into editable tag/name suggestions.
- Show a before/after path preview and token provenance.
- Keep every file owner-confirmed; no automatic tier.
- Embed or export UCS-compatible metadata for applicable SFX records.
- Record acceptance and correction events in the promotion ledger.

Exit gate: zero data-loss incidents, plan/apply parity, high suggestion utility,
and independently tested undo.

### Phase E — qualify narrow automatic actions

Status: not currently qualified.

- Choose only stable, coherent classes with enough independent collections.
- Gather a sealed candidate stream that was not used for model selection or
  threshold calibration.
- Require the 95% Wilson lower bound to exceed the advertised precision, not
  merely raw point accuracy. A practical collection target is at least 100
  independent examples per candidate class, but the statistical gate—not the
  count alone—is authoritative.
- Revalidate after any model, taxonomy, evidence, or calibration change.
- Start with copy/export or metadata-only actions before physical renames.
- Roll back an automatic tier immediately if live audited precision violates its
  promise.

Exit gate: signed class-policy receipt, independent validation, collision and
duplicate guards, journal/undo qualification.

### Phase F — optional real-world branch

Status: research only.

- Map a limited AudioSet vocabulary into SLO's domain/source/event/form axes.
- Map exportable SFX concepts to UCS 8.2.1.
- Evaluate public backbones on FSD50K/HEAR-style tasks and on a small local
  sealed set without mixing metrics.
- Activate only if a concrete product workflow justifies the model size,
  taxonomy and support burden.

Exit gate: separate requirements, benchmark, storage/model budget and owner
decision. No effect on music-sample policies before then.

## 10. Recommended product sequence

The shortest credible path is:

1. finish the breadth labels;
2. rebuild and audit the incumbent;
3. make Find Similar, aspect search and physical filters excellent;
4. expose editable factor tags and evidence;
5. release deterministic rename suggestions with no automatic mutation;
6. learn from corrections and taxonomy gaps;
7. qualify a few narrow automatic classes statistically;
8. expand to real-world sounds only as a separate product branch.

This sequence avoids waiting for an impossible universal classifier before SLO
is useful. It also avoids letting product pressure weaken the rename safety
standard.

## 11. Immediate backlog

### Now, without additional labels

- unify the research/shadow evidence stores behind one content-addressed schema;
- define and test retrieval benchmarks for overall/timbre/pitch/envelope/rhythm;
- finish UI explanations for why a result matched;
- add background analysis progress and retry receipts;
- implement metadata-only export and UCS mapping tests;
- generate class/evidence cards from existing receipts;
- test suggestion preview, collision handling, journal and undo on disposable
  fixtures;
- design the sealed auto-action validation protocol;
- evaluate public teacher outputs only as taxonomy-gap/review candidates.

### Immediately after the 600 labels

- freeze the manifest;
- run the controlled incumbent rebuild, pinned to GPU 1 only if read-only checks
  show it is free, with no restart or process killing;
- regenerate collection-held-out and rejection reports;
- identify the top three error mechanisms, not just the top three confused
  classes;
- run no more than the two best mechanism-specific experiments before reviewing
  results;
- refresh the read-only 28,330-file qualification plan with the new model while
  leaving production policy unchanged.

## 12. Final recommendation

SLO does not need to solve “what is every possible sound?” in one model before
it can become a strong product. It needs to know what it knows, retain the
evidence behind each claim, make uncertain audio easy to find, learn cleanly
from corrections, and reserve file mutation for a much higher evidential bar
than search or tagging.

The competition validates the multi-surface product; SLO's experiments validate
the conservative learning and safety strategy. The resulting product is not a
clone of Sononym, Soundly, Ableton, COSMOS, XO, Atlas, Loopcloud or Soundminer.
It combines their strongest interaction patterns with a verification layer they
do not publicly foreground: collection-aware measurement, provenance, explicit
abstention, and statistically qualified renaming.

## Sources

### Products and standards

- [Sononym — product overview](https://www.sononym.net/about/sononym/)
- [Sononym — filtering and classifications](https://www.sononym.net/docs/manual/filtering/)
- [Ableton Live 12 — sound similarity](https://www.ableton.com/en/manual/live-concepts/#sound-similarity)
- [Ableton Live 12 — browser, auto tags and tag editor](https://www.ableton.com/en/live-manual/12/working-with-the-browser/)
- [Soundly — product, search, local libraries, metadata and UCS](https://getsoundly.com/)
- [Soundly support — UCS naming and local indexing](https://getsoundly.com/support/)
- [Soundminer — product tiers and metadata capabilities](https://store.soundminer.com/)
- [Soundminer — UCS integration](https://store.soundminer.com/blogs/news/ucs-universal-category-system)
- [Soundminer — scanning and embedded metadata](https://info.soundminer.com/docs/scanning)
- [Loopcloud — product features](https://www.loopcloud.com/cloud/features)
- [Loopcloud — search, physical filters and match modes](https://www.loopcloud.com/cloud/blog/5123)
- [Waves COSMOS — official introduction](https://www.waves.com/introducing-cosmos-sample-finder)
- [XLN Audio XO — official interface overview](https://support.xlnaudio.com/hc/en-us/articles/16920363887645-Interface-Overview)
- [Algonaut Atlas 2 — map and similarity workflow](https://algonaut.audio/manuals/atlas/2_0_2/map.html)
- [Algonaut Atlas 2 — analysis scope and resumability](https://algonaut.audio/manuals/atlas/2_0_2/map_create_edit.html)
- [Splice — Similar Sounds](https://splice.com/blog/introducing-similar-sounds/)
- [Universal Category System](https://universalcategorysystem.com/)

### Research, ontologies and datasets

- [Google AudioSet](https://research.google.com/audioset/)
- [AudioSet ontology repository and schema](https://github.com/audioset/ontology)
- [Freesound research datasets — FSD50K](https://labs.freesound.org/datasets/)
- [FSD50K paper](https://arxiv.org/abs/2010.00475)
- [HEAR benchmark](https://hearbenchmark.com/)
- [HEAR tasks and data](https://hearbenchmark.com/hear-tasks.html)
- [HEAR scene and timestamp embedding API](https://hearbenchmark.com/hear-api.html)
- [CLAP: Learning Audio Concepts From Natural Language Supervision](https://arxiv.org/abs/2206.04769)
- [BEATs: Audio Pre-Training with Acoustic Tokenizers](https://arxiv.org/abs/2212.09058)
