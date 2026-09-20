# SLO Competitor-Parity Test and Research Plan V1

**Planning date:** 2026-09-15  
**Purpose:** make SLO work correctly, feel credible beside mature sample browsers, and develop evidence-backed differentiators without blocking the private beta on speculative research  
**Companion plan:** `SLO_BETA_EXECUTION_MASTER_PLAN_V1.md`  
**Research rule:** no feature, label, threshold, or model reaches the release branch because it looks promising; it must pass a predeclared test against an untouched evaluation set and the complete product workflow

## 1. Outcome

The objective is not to clone every competitor. It is to reach parity on the core job—find the right local sound quickly and move it into a real project safely—then win on SLO's chosen strengths:

- local-first privacy;
- broad producer-oriented sample coverage rather than drum-only mapping;
- visible evidence, confidence, and abstention;
- safe duplicate handling and reversible organisation;
- useful acoustic similarity combined with semantic and physical filters;
- a strong Ableton workflow without taking ownership of the user's library.

“Working like its competitors” therefore means:

1. a large library can be added without fear or special preparation;
2. indexing is observable, cancellable, resumable, and non-blocking;
3. browse/search/filter results react immediately;
4. similarity results sound meaningfully related to producers;
5. audition is fast and musical;
6. favourites, history, collections, and duplicate groups preserve context;
7. drag-to-DAW and project reopen work predictably;
8. failures explain themselves and recover safely;
9. classification helps discovery without confidently inventing labels;
10. the product remains stable across realistic library sizes and long sessions.

## 2. Competitor reference model

This plan uses official product documentation as a workflow reference, not as ground truth for implementation or classification.

| Product | User expectation it establishes | What SLO should test |
|---|---|---|
| Sononym | similarity by overall sound plus spectrum, timbre, pitch, and amplitude; categorisation; duplicate/near-duplicate detection; filtering, history, bookmarking, waveform audition | aspect-weighted query-by-example, transparent similarity scores, fast compound filtering, exact/near-duplicate separation, history/favourites, low-friction audition |
| XLN Audio XO | visual organisation by sonic similarity, immediate similar-sample stepping, filters, favourites/history, hot swapping in context, easy DAW export | map usefulness, keyboard-speed exploration, “next similar” quality, filters affecting similarity, reversible preview/hot-swap behavior, drag reliability |
| Algonaut Atlas 2 | map-based exploration, sample organisation, kits/sequences, random inspiration | map navigation and discoverability; SLO does not need kit/sequencer parity for Beta 1 |
| Waves COSMOS | AI categorisation/tagging, one-shot/loop search, DAW-integrated browsing and tempo/key-synchronised preview | category/tag search, plugin-host stability, session-aware preview, clear recovery when scan/model services fail |
| Loopcloud | rich filters for instrument/key/BPM/type, tempo/key-matched preview, editing and DAW transfer | compound musical filters, context audition, source-versus-preview clarity, low-friction transfer |
| Ableton Live 12 Browser | background sound analysis, visible progress/pause, similarity search, similar-sample swapping, filters/tags, history and user labels | background indexing, pause/cancel, exact host integration, filter/history behavior, value beyond the browser already in the DAW |

Official references:

- Sononym product and similarity-search manual: `https://www.sononym.net/` and `https://www.sononym.net/docs/manual/similarity-search/`
- XLN Audio XO product and interface guide: `https://www.xlnaudio.com/products/xo` and `https://support.xlnaudio.com/hc/en-us/articles/16920363887645-Interface-Overview`
- Algonaut Atlas 2 manual: `https://algonaut.audio/manuals/atlas/2_0_2/index.html`
- Waves COSMOS: `https://www.waves.com/plugins/cosmos-sample-finder`
- Loopcloud features: `https://www.loopcloud.com/cloud/features`
- Ableton Live 12 browser/similarity manual: `https://www.ableton.com/en/manual/live-concepts/` and `https://www.ableton.com/en/live-manual/12/working-with-the-browser/`

## 3. Parity, differentiation, and deferral

### 3.1 Must match for a credible beta

| Capability | Beta bar |
|---|---|
| Add/index folders | recursive, format-aware, progress visible, cancellation safe, partial failures visible |
| Incremental indexing | unchanged files are not re-analysed; changed/moved/missing files resolve correctly |
| Search/filter | filename, category, one-shot/loop, BPM, key, duration, favourites, and supported acoustic attributes combine correctly |
| Query by example | launch from any valid sample; useful top results; query remains visible; return to previous state |
| Preview | very low perceived latency; keyboard controls; rapid switching; no source mutation |
| Visual map | stable positions for an unchanged index; selection, zoom, filter, and similarity interaction remain understandable |
| Workflow memory | history, favourites, collections, filters, and selected library persist as designed |
| DAW transfer | drag valid audio to Ableton; missing files fail clearly; save/reopen retains plugin state |
| Trust | confidence and Unknown/OOD are clear; exact and near duplicates are distinguished |
| Recovery | corrupt files, permissions, missing drives, interrupted scans, forced quit, and cache corruption recover safely |

### 3.2 SLO differentiation to prove

- evidence-aware search: combine embedding similarity with physical facets such as brightness, duration, low-end weight, periodicity, transient shape, stereo character, and confidence;
- honest uncertainty: high-confidence results are demonstrably more precise than low-confidence results, and abstention improves trust;
- content identity: exact duplicates share stable identity while path aliases remain visible;
- safe organisation: preview every proposed operation, preserve provenance, Copy by default, journal every write, and Undo reliably;
- broad sound-library usefulness: drums, bass, vocals, synths, loops, FX, atmosphere, foley, risers, and impacts—not just drum one-shots;
- privacy: all analysis stays local and no sample audio is required for ordinary support.

### 3.3 Defer until evidence demands it

- beat sequencer, kit generator, or built-in content store;
- cloud sample catalogue;
- destructive duplicate cleanup;
- live microphone similarity search;
- waveform cropping/export;
- automatic time/key transformation;
- natural-language generative search beyond the controlled vocabulary;
- Windows/Intel Mac/multiple new DAWs;
- public claims of superior accuracy.

These may be valuable, but they are not required to prove the core SLO job.

## 4. Research questions

Each research question ends in a decision, not just a report.

| ID | Question | Decision enabled |
|---|---|---|
| RQ-01 | Which three sound-finding jobs cost producers the most time? | beta workflow and UI priority |
| RQ-02 | When producers say two samples are “similar,” which dimensions do they mean for each class? | similarity weighting by task/class |
| RQ-03 | Does SLO return a useful option in the top 5 as often as mature products? | retrieval promotion or redesign |
| RQ-04 | Does the visual map improve discovery versus list + filters? | retain, simplify, or deprioritise map |
| RQ-05 | Which categories/attributes change actual search decisions? | taxonomy scope; remove low-value labels |
| RQ-06 | At what confidence should SLO label, suggest, or abstain for each class? | calibrated decision policy |
| RQ-07 | What preview controls materially improve selection speed? | original, tempo-sync, key-lock, A/B priorities |
| RQ-08 | What library size/hardware combination breaks perceived responsiveness? | supported-size statement and architecture work |
| RQ-09 | Which recovery failures cause users to lose trust? | error/recovery design priority |
| RQ-10 | Is SLO sufficiently better than Ableton's own browser to remain open in a session? | positioning and product viability |
| RQ-11 | Do user corrections improve later search without destabilising prior behavior? | feedback-learning design |
| RQ-12 | Which SLO operations create anxiety even when technically safe? | consent, preview, and copy design |

## 5. Test architecture

### Layer 0 — contracts and static checks

- build/release manifest schema;
- model/taxonomy/preprocessing/class-order identity;
- supported-format registry and documentation match;
- production licensing rejects localhost/plain HTTP;
- no production secrets or local absolute paths;
- no source-audio mutation call reachable from scan/search/preview;
- release bundle contains notices and required model assets;
- user-facing product/version/host claims match the candidate receipt.

### Layer 1 — deterministic unit tests

- tokenisation, aliases, negative terms, Unicode, case, punctuation;
- filters and compound Boolean behavior;
- category/subtype/attribute/confidence presentation;
- Unknown versus never-scanned versus failed;
- path containment and collision naming;
- stable content IDs and exact-duplicate grouping;
- similarity-score ordering and tie behavior;
- persisted filter/history/favourite/collection state;
- preview plan calculation without applying a transformation;
- entitlement state machine;
- schema migration and version invalidation.

### Layer 2 — component/integration tests

- decode → features → embedding → classifier → cache → UI model;
- query sample → embedding/index → ranked results → filters;
- format-aware scan across WAV/AIFF/FLAC/OGG and only formats actually compiled in;
- corrupt/unsupported files mixed with valid audio;
- rescan after edit, rename, move, delete, drive removal, and restoration;
- exact duplicate versus gain-adjusted/converted/cropped near duplicate;
- index build while users browse and preview;
- cancellation at discovery, decode, inference, write, and finalisation stages;
- multi-instance cache access;
- licence activation/offline/revocation around plugin state restoration;
- Copy/Move/Cancel/Undo on disposable fixtures if Sort Library is enabled.

### Layer 3 — end-to-end product tests

- clean installation → activation → first scan → discovery → preview → drag → project reopen;
- upgrade from previous beta with existing index and preferences;
- rollback to previous beta with a newer index schema;
- first launch with model missing/corrupt;
- first launch offline after prior activation;
- external SSD disconnect/reconnect during scan and during preview;
- force quit during scan then safe restart;
- macOS audio-device change while previewing;
- two plugin instances in one Ableton set;
- long session with repeated searches, previews, scans, and project saves.

### Layer 4 — performance and scale

- cold scan, warm scan, incremental scan, launch/hydration, text search, filter, similarity, map load, preview latency, cancellation latency, steady/peak RSS, CPU, cache growth, disk I/O, and UI stalls;
- run on internal SSD and representative external SSD;
- capture hardware, OS, filesystem, library composition, model, candidate SHA, and thermal state;
- test at 1k, 10k, 50k, and 100k files; 250k is the post-beta stretch tier;
- all performance tests must use mixed real audio plus declared adversarial fixtures, not repeated copies alone.

### Layer 5 — host compatibility

- exact signed AU/VST3 in the supported Ableton Live version;
- scan, load, transport start/stop, preview, drag, state save/reopen, sample-rate/buffer changes, offline activation, update, and uninstall;
- `auval` plus a VST3 validator where available;
- host automation/state serialization test even if SLO exposes few automatable parameters;
- test opening a project when the indexed external drive is missing.

### Layer 6 — producer evaluation

- moderated task study;
- blinded retrieval judgments;
- competitor crossover benchmark;
- seven-day diary beta;
- exit interview focused on actual sessions and abandoned attempts.

### Layer 7 — beta observability

- opt-in, privacy-preserving structured events or manual ledger for install, activation, scan complete, query, useful result, drag, crash, support, and correction;
- no audio upload;
- explicit denominators and release IDs;
- stop conditions tied to safety and reliability.

## 6. Corpus and fixture programme

### 6.1 Four distinct corpora

| Corpus | Purpose | Labels visible to developers? | Mutation allowed? |
|---|---|---:|---:|
| Engineering fixtures | deterministic unit/integration tests | yes | only inside disposable copies |
| Development corpus | feature/model iteration | yes | read-only source |
| Validation corpus | threshold/model selection | aggregate results only where practical | read-only source |
| Sealed test corpus | final promotion decision | no until candidate frozen | read-only source |

Never tune and report on the same split. Group splits by vendor, pack, recording session, and content hash so related files cannot leak across partitions.

### 6.2 Representation requirements

- all 17 production primary classes plus explicit OOD/rejection material;
- balanced minimums for critical classes, not only natural-frequency totals;
- at least 15 vendors/source families initially, then add genuinely different libraries;
- one-shots and loops; dry and processed; short and long; tonal and noisy; mono and stereo;
- 44.1/48/96 kHz, 16/24/32-bit where supported;
- WAV/AIFF/FLAC/OGG and every format SLO publicly claims;
- filenames ranging from descriptive to opaque/random;
- folder structures ranging from informative to deliberately uninformative;
- independent tester-owned collections for usability, never silently merged into training.

### 6.3 Adversarial fixture set

- zero-byte, truncated, header-corrupt, extreme-length, silence, NaN/Inf, clipped, DC-offset, very quiet, and very loud files;
- Unicode, emoji, long paths, duplicate names, mixed case, leading dots, and reserved punctuation;
- symlinks and loops; unreadable folders; nested depth; files changed during scan;
- removable drive disappears and returns;
- exact byte copies across paths;
- same audio in different containers/bit depths;
- gain-adjusted, polarity-inverted, channel-swapped, silence-padded, cropped, and resampled near duplicates;
- misleading filename/folder labels;
- out-of-taxonomy field recordings, speech, full songs, stems, MIDI/non-audio, and model-confusing hybrids.

### 6.4 Scale packs

- S1: 1,000 files for every-commit smoke and correctness.
- S2: 10,000 files for release-candidate regression.
- S3: 50,000 files for weekly performance and recovery.
- S4: 100,000 files for beta support claim.
- S5: 250,000 files for competitor-scale research after Beta 1.

Generated repetition may fill load-test volume but cannot count toward retrieval, classification, or cache-identity diversity.

## 7. Competitor crossover study

### 7.1 Design

- Use properly licensed/trial copies and official workflows; do not reverse engineer private formats or models.
- Use the same tester-owned or licensed evaluation library on the same Mac and SSD.
- Compare SLO, Ableton Live 12 Browser, Sononym, and one visual-map competitor (XO or Atlas where the corpus fits its drum focus). Add COSMOS/Loopcloud only where their local-library workflow is directly comparable.
- Counterbalance product order to reduce learning effects.
- Give each product a fixed onboarding allowance.
- Record screen and task timings only with participant consent.
- Blind retrieval audio where possible: export anonymised candidate IDs and audition without product branding/order cues.
- Separate “feature absent” from “feature present but worse.”

### 7.2 Participant plan

- Discovery: 6 producers across electronic, hip-hop, cinematic/sound-design, and pop workflows.
- Formative usability: 6–8 participants, two rounds.
- Comparative benchmark: 12 participants minimum; 20 preferred before strong claims.
- Experience spread: novice library-browser users, regular Ableton-browser users, and users of at least one dedicated sample manager.

### 7.3 Core tasks

1. Add a 10k library and find out whether indexing is progressing.
2. Find five short dark kicks, then choose one for a track.
3. Starting from a reference snare, find a brighter but otherwise similar alternative.
4. Find a 120-BPM tonal loop in a compatible key.
5. Find a variation of an opaque-named sample using only its audio.
6. Return to a sound heard three steps earlier and favourite it.
7. Identify exact duplicates and inspect near-duplicate candidates without deleting anything.
8. Drag a selected sound into Ableton, save, close, and reopen.
9. Recover after the source drive disappears.
10. Explain why SLO labelled or abstained on three ambiguous samples.

### 7.4 Measures

- task completion without assistance;
- time to first plausible result and time to committed selection;
- audition count and backtracking count;
- query reformulations/filter changes;
- top-5 usefulness;
- confidence in chosen sound;
- perceived control, trust, and workload;
- errors, recoveries, and abandonment;
- preference and reason after using all products;
- whether the chosen sound survives in the project after 24 hours.

### 7.5 Competitive decision rule

SLO reaches core parity when:

- its median completion rate is within 10 percentage points of the best comparator across core tasks;
- median time-to-selection is no worse than 1.25× the best comparator and is best on at least one SLO differentiator task;
- producer-blinded retrieval preference (`win + 0.5 × tie`) is at least 45% against the strongest comparator with uncertainty reported;
- at least 70% of reference queries have one producer-rated useful result in SLO's top 5;
- trust/safety is not worse than any comparator and no participant believes SLO changed source audio during read-only tasks.

This is a non-inferiority bar for a private beta, not permission to claim superiority publicly.

## 8. Retrieval and similarity research

### 8.1 Query set

Build 200 content-hash-unique reference queries, stratified by class and search intent:

- close variation;
- same instrument, different brightness;
- same instrument, shorter/longer;
- same pitch/timbre;
- same temporal envelope;
- loop with compatible tempo/key;
- texture/FX with similar evolution;
- exact/near-duplicate discovery;
- deliberately impossible or OOD request.

### 8.2 Human judgments

- Pool top 20 results from SLO variants and comparators; remove product identity and randomise.
- Obtain at least three producer judgments per query-result pair where affordable.
- Rate: not relevant, plausible, useful, excellent; separately tag the dimension of similarity.
- Track inter-rater agreement; disagreement is product information, not label noise to hide.
- Preserve participant role/genre without using personal identity in model data.

### 8.3 Metrics

- success@1, success@5, success@10;
- nDCG@5/10;
- mean reciprocal rank for the first useful result;
- class/intention slices;
- duplicate-crowding rate;
- vendor/pack diversity in top 10;
- query latency and ranking stability;
- producer preference against baseline/comparator;
- correction rate after selection in a real session.

### 8.4 Experiments

- production embedding baseline versus weighted similarity;
- global weights versus class-conditional weights;
- embedding-only versus embedding + physical facets;
- content-deduplicated versus path-level results;
- single-window versus multi-segment representation for loops/long sounds;
- exact query versus selected waveform region, only after the basic workflow is stable;
- approximate-index settings versus exact-search audit subset;
- diversity reranking to prevent one pack or duplicate family filling the result list.

Promotion gate:

- statistically and practically meaningful top-5 improvement on validation;
- no regression above the declared tolerance in any critical class;
- latency/memory within budget;
- sealed-test result reproduced in C++ production parity;
- UI communicates what changed;
- model/index version and migration behavior defined.

## 9. Classification, tags, and OOD research

### 9.1 Measure the right system

Always report four separate modes:

1. audio-only model;
2. filename/folder/metadata heuristic evidence;
3. fused production result;
4. user-corrected result.

Report overall and macro metrics, per-class precision/recall, vendor/pack slices, and coverage. A high score on descriptive filenames cannot be presented as acoustic accuracy.

### 9.2 Beta decision targets

- high-confidence precision ≥ 90% overall and ≥ 80% per critical class once each class has at least 30 sealed examples;
- medium-confidence precision ≥ 80% overall;
- low-confidence output is presented as a suggestion, never an authoritative tag;
- coverage at those precision levels is reported rather than forced;
- false-known rate on OOD high-confidence outputs ≤ 10%; otherwise lower coverage/abstain;
- no critical class may have near-zero recall without a visible limitation or fallback workflow;
- calibration error and reliability plots accompany thresholds;
- Unknown must be distinguishable from not-yet-analysed and analysis-failed.

Targets are promotion bars, not claims about current performance.

### 9.3 Priority research order

1. calibrate confidence/abstention per class without reopening the sealed set;
2. improve weak high-value primary classes identified in producer tasks;
3. evaluate Pad/Stab product placement using real retrieval tasks before changing primary taxonomy;
4. add only subtypes that improve an observed workflow and clear held-out precision;
5. validate low-end-heavy as a useful independent facet;
6. investigate distortion/cleanliness only if producer studies rank it highly enough to justify new DSP;
7. treat natural-language terms as controlled filter/query mappings until independently calibrated.

### 9.4 Correction research

- capture accept/correct/reject/not-in-list with model/taxonomy version and required notes for taxonomy gaps;
- never train directly from raw beta events;
- de-duplicate by content hash and separate the user's private label from shared research consent;
- sample corrections for owner review;
- maintain replay tests so new models do not break previously corrected items;
- run shadow evaluation before any learned update reaches production.

## 10. Tempo, key, and context-audition research

### 10.1 Ground truth

- use musically reviewed loops across straight, swung, half-time, double-time, triplet, and syncopated material;
- record both notated and perceived tempo where they legitimately differ;
- include tonal, atonal, modal, ambiguous, and key-changing samples;
- do not treat filename BPM/key as independent truth; it may seed review only.

### 10.2 Metrics

- BPM exact tolerance ±2;
- metrical-family accuracy including half/double relationships;
- confidence calibration and abstention rate;
- key root accuracy, root+mode accuracy, and compatible-key usefulness;
- false BPM on one-shots;
- context-preview alignment error and audible artifacts;
- producer preference for original versus synchronised audition.

### 10.3 Staged delivery

1. display trusted metadata and confidence honestly;
2. filter using accepted BPM/key evidence;
3. preview source at original speed/pitch reliably;
4. add tempo-sync preview behind an experimental flag;
5. add key-lock only after key confidence and artifact quality pass;
6. never modify the source file; export/render is a separate explicit future workflow.

## 11. Performance and responsiveness programme

### 11.1 Competitive budgets

| Operation | Beta target | Stretch target |
|---|---:|---:|
| Window usable after launch with 10k cached files | ≤ 5 s | ≤ 2 s |
| First scan progress visible | ≤ 1 s | ≤ 300 ms |
| Text/filter update at 100k cached files | p95 ≤ 150 ms | p95 ≤ 75 ms |
| Similarity results at 100k cached files | p95 ≤ 750 ms | p95 ≤ 300 ms |
| Preview click-to-audio | p95 ≤ 100 ms | p95 ≤ 50 ms |
| Stop preview | p95 ≤ 100 ms | p95 ≤ 50 ms |
| Cancel scan acknowledgment | ≤ 2 s | ≤ 500 ms |
| UI input stall while indexing | no stall > 250 ms | no stall > 100 ms |
| 100k mixed-file scan | completes safely; UI remains usable | ≥ 20 files/s median |
| Steady RSS after 100k scan | ≤ 3.0 GB target; document if not met | ≤ 2.0 GB |
| 30-cycle warm scan | no upward RSS/cache leak trend | same at 100 cycles |

If the 100k target is not met, Beta 1 may launch only with an honestly smaller supported-size statement and a measured plan to expand. It may not silently imply competitor-scale support.

### 11.2 Profiling questions

- why existing evidence shows multi-gigabyte fixed/retained memory;
- model/session count per instance and whether it can be safely shared;
- batch size, worker count, decode buffers, embedding retention, and map memory;
- SQLite query/index plans at 10k/50k/100k;
- HNSW construction/search memory and parameter trade-offs;
- cost of 2-D map materialisation and refresh;
- UI invalidation/repaint frequency during scan;
- cold versus warm filesystem cache;
- external-drive and thermal-throttling effects;
- cancellation latency inside decode/inference jobs.

Every optimisation needs a before/after receipt and the full correctness/safety suite.

## 12. Workflow acceptance catalogue

### W-01 First run

- user understands local-only behavior and chooses a folder;
- progress appears immediately;
- first results become usable before the entire library finishes where technically safe;
- skip/cancel never creates a broken partial state;
- closing during scan restarts safely.

### W-02 Find a known type

- search “kick”, select one-shot, short duration, dark;
- result count and active filters are visible;
- clearing one filter preserves others;
- no unsupported value is silently filled.

### W-03 Find a variation

- start similarity from a selected sample;
- compare query and candidate quickly;
- adjust timbre/brightness/duration emphasis;
- duplicate aliases do not crowd out distinct sounds;
- back returns to the prior browse state.

### W-04 Creative wandering

- map and random/diverse discovery avoid repeatedly surfacing one pack;
- history returns to previously auditioned sounds;
- favourite persists after restart;
- visual position is stable for unchanged content.

### W-05 Use in Ableton

- plugin loads without stealing transport/audio focus;
- previews stop predictably;
- drag copies/references the intended source file;
- saved set reopens with state intact;
- missing external drive shows a safe, recoverable state.

### W-06 Correct SLO

- user can say wrong, uncertain, or not-in-list;
- original machine result and version remain auditable;
- correction affects presentation as designed without corrupting shared truth;
- private data and research consent remain separate.

### W-07 Duplicates

- exact duplicate group explains paths and stable identity;
- near duplicates are clearly candidates, not facts;
- no delete button/action in Beta 1;
- reveal-in-Finder and keep/preferred-path choices are safe.

### W-08 Recovery

- corrupt cache is quarantined/rebuilt without source mutation;
- unsupported files are reported and skipped;
- disconnected drives remain registered without destructive pruning;
- reinstall/upgrade/rollback preserves or safely migrates the index.

## 13. Automation plan

### On every shipping-code change

- static/contract checks;
- fast native safety/taxonomy/presentation tests;
- affected Python research-tool tests;
- format/path/cache regression;
- model/header parity if classifier inputs change.

### Nightly on the beta branch

- all native executables run directly;
- all Python tests;
- S1 cold/warm/incremental scan;
- adversarial fixture suite;
- multi-instance and forced-cancel stress;
- manifest/model identity check;
- leak/undefined behavior sanitizer lane where supported.

### Weekly

- S2/S3 scale test;
- 30-cycle soak;
- exact versus approximate similarity audit subset;
- retrieval benchmark by class/intent;
- calibration/OOD dashboard from the frozen development/validation sets;
- signed-artifact host smoke once signing exists.

### Every release candidate

- clean worktree and clean Release build;
- every native executable executed;
- licensing E2E;
- read-only SHA-256 safety;
- S2 minimum and S4 for changes affecting index/scan/performance;
- signed/notarised package checks;
- clean-Mac and Ableton matrices;
- upgrade and rollback;
- exact documentation/known-limitations review;
- owner gate.

Flaky tests are release defects. Quarantining requires an owner, reason, risk statement, and expiry date; passing on retry is not a pass.

## 14. Experiment lifecycle

Every experiment has:

1. problem statement tied to a producer task;
2. baseline and candidate;
3. predeclared primary metric, guardrails, slices, and minimum effect;
4. immutable input manifest and content hashes;
5. train/development/validation/sealed-test boundaries;
6. deterministic configuration and environment receipt;
7. failure/null-result report as seriously as a win;
8. C++ parity test for any shipped logic;
9. performance, memory, migration, safety, and UI impact;
10. explicit outcome: reject, continue research, shadow, beta flag, or production promotion.

Promotion requires approval from product, engineering, and evidence owners. A research script, generated header, or impressive sample pack demo is not a production candidate by itself.

## 15. Eight-week execution programme

This programme runs alongside the release plan; external Apple/licensing work should not wait for research.

### Week 1 — benchmark foundations

- freeze product workflows and comparator set;
- inventory current automated coverage against sections 5 and 12;
- build S1/S2/adversarial manifests;
- define metrics and receipt schemas;
- run current SLO baseline without changing behavior;
- recruit discovery participants.

**Exit:** coverage matrix, immutable baseline, unresolved-test backlog.

### Week 2 — correctness and recovery

- fill high-risk integration gaps: incremental rescan, disconnect/reconnect, force quit, unsupported formats, cache recovery, upgrade/rollback;
- run complete journey twice;
- fix only evidenced P0/P1 issues.

**Exit:** core correctness suite passes; recovery behavior documented.

### Week 3 — performance and compound search

- run S1–S4 profiling;
- add end-to-end similarity + facets tests;
- measure query, filter, map, preview, and cancellation latency;
- profile retained memory and multi-instance cost.

**Exit:** supported-scale statement and prioritised performance work.

### Week 4 — producer research round 1

- six discovery/formative sessions;
- compare SLO with Ableton plus one dedicated browser;
- identify top three failed jobs and top three SLO advantages;
- change product priorities, not model thresholds, based on results.

**Exit:** evidence-backed workflow backlog and revised beta script.

### Week 5 — retrieval benchmark

- build 200-query pool;
- gather blinded judgments;
- score production baseline, weighted/aspect variants, deduplicated/diversity variants;
- select at most one candidate for further validation.

**Exit:** retrieval decision report; no candidate promoted yet.

### Week 6 — classification and context audition

- calibration/selective-risk analysis on frozen data;
- weak-class and OOD review;
- tempo/key ground-truth pilot;
- original-versus-context-preview usability prototype if justified.

**Exit:** beta policy thresholds/limitations; research candidates remain gated.

### Week 7 — competitor crossover

- 12-participant comparative tasks where feasible;
- exact same hardware/library and counterbalanced order;
- calculate completion, time, retrieval usefulness, trust, workload, and preference;
- identify beta blockers versus post-beta advantages.

**Exit:** parity scorecard and go/fix/defer decisions.

### Week 8 — release-candidate synthesis

- implement only bounded, evidenced beta blockers;
- rerun affected layers plus full release qualification;
- freeze benchmark and known-limitations reports;
- hand exact candidate into clean-Mac/internal-pilot gates.

**Exit:** competitor-informed product-qualified RC or an explicit blocked report with owners.

## 16. Deliverables

- `SLO_COMPETITOR_WORKFLOW_MATRIX_V1.md`
- `SLO_TEST_COVERAGE_MATRIX_V1.json`
- `SLO_CORPUS_MANIFESTS_V1/` stored outside shipping source where required
- `SLO_ADVERSARIAL_FIXTURE_SPEC_V1.md`
- `SLO_PERFORMANCE_SCALE_RECEIPT_V1.json`
- `SLO_RETRIEVAL_BENCHMARK_V1.json`
- `SLO_CLASSIFICATION_SELECTIVE_RISK_V1.json`
- `SLO_TEMPO_KEY_GROUND_TRUTH_PROTOCOL_V1.md`
- `SLO_COMPETITOR_CROSSOVER_PROTOCOL_V1.md`
- `SLO_COMPETITOR_PARITY_SCORECARD_V1.md`
- `SLO_BETA_KNOWN_LIMITATIONS_<release-id>.md`
- exact-candidate qualification, host, installation, licensing, and rollback receipts from the beta master plan.

## 17. First implementation backlog

### Test gaps to address first

1. one executable journey test that scans a mixed-format fixture, waits for progress, queries, filters, finds similar, previews through a test sink, persists state, restarts, and verifies source hashes;
2. external-drive disappearance/reappearance test with no destructive prune;
3. forced-quit/restart cache transaction test;
4. compound similarity + category + attribute + BPM/key filter tests;
5. result diversity and duplicate-crowding regression;
6. 100k cached query/filter/similarity benchmark;
7. preview start/stop/rapid-switch latency harness;
8. Ableton state round-trip fixture and manual script;
9. update/rollback schema compatibility test;
10. production licensing failure-mode matrix.

### Research tasks to begin first

1. six producer discovery sessions using the ten tasks in section 7;
2. current-production 200-query retrieval baseline;
3. producer-calibrated aspect-similarity judgments;
4. high-confidence precision/coverage and OOD selective-risk curves;
5. retained-memory profile at 10k and 50k before attempting model changes;
6. small reviewed tempo/key set focused on real audition decisions.

## 18. Final readiness rule

SLO is competitor-credible for private beta when the core workflows pass, the competitive non-inferiority study clears its bar, the supported scale is honest and stable, the exact artifact passes Ableton/clean-Mac qualification, and producers repeatedly find useful sounds without fearing for their libraries.

It does not need every competitor feature. It does need to be faster, clearer, safer, or more useful in at least one meaningful part of the sound-finding job—and merely no worse on the rest of the core journey.
