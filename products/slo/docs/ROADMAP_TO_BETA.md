# SLO Roadmap to Beta (with extremely high quality classification)

**Written:** 2026-09-17
**Grounded in:** direct inspection of `products/slo` (source, docs, blocker register, accuracy reports, encoder research decision, beta execution master plan). Every claim below cites what was actually found; nothing is assumed.

> **Relationship to existing plans:** `SLO_BETA_EXECUTION_MASTER_PLAN_V1.md` already defines the beta release process (signing, licensing, host validation, cohorts). This document does not replace it — it adds the **classification-quality track** as a first-class workstream, sequenced against that plan, with measurable acceptance criteria and explicit owner decisions.

## 0. Execution status log

| Date | Phase | Outcome | Receipt |
|---|---|---|---|
| 2026-09-17 | Phase 1 (partial) | Clean candidate worktree materialized; configure + build + 41-binary test sweep all executed. **P0 defect found and fixed** — the candidate's embedding-output validator rejected every inference (`embeddingDim` 520 vs actual PANNs output 512). Fix recovered 11 of 12 failing tests; sweep now 40/41, the 1 failure environmental (B-003). | `docs/BETA_CANDIDATE_ASSEMBLY_RECEIPT_2026-09-17.md` |
| 2026-09-17 | Phase 1 (**re-opened**) | End-to-end run on real audio proved the P0 fix was necessary but insufficient: the chosen base commit is **superseded**. All 20/20 in-distribution files were rejected as OOD → product output `UNKNOWN` for everything. Two of the eight commits by which local main leads the branch are **mandatory**, not optional: `ebbb164` (contains the validator fix) and `6990093` (current classifier, v6 weights + calibrated centroids + taxonomy v5). Candidate re-materialized from main `dc855be`. | receipt §4a, §5b |

**Consequence for the whole roadmap:** every accuracy/performance number previously published for this lineage must be **regenerated** before it is quoted (see §2.1). A candidate that could not run inference cannot have produced a trustworthy benchmark, and the branch validator was structurally incapable of executing it. Phase 2 is therefore re-scoped as *re-establish first, then improve*.

---

## 1. Project analysis

### 1.1 What SLO is

**SLO — Sample Library Optimiser** (canonical name; formerly *Smart Sample Manager* — the JUCE bundle IDs still carry `com.nitedsp.smartsamplemanager`, `AtSm`, v1.0.0). A **macOS Apple Silicon** JUCE plugin producing **AU / VST3 / Standalone** from one CMake target, plus 31 test/benchmark executables. Source of truth: `SLO_SOURCE_ARCHITECTURE_MAP.md`.

### 1.2 Tech stack (verified from source tree)

| Layer | Implementation | Evidence |
|---|---|---|
| App/plugin | JUCE (`PluginProcessor.*`, `PluginEditor.*`) | `Source/` directory |
| Decode | dr_wav (**WAV-only discovery** — `addPathToQueue()` matches `*.wav` only) | `SLO_V1_WORKING_PRODUCT_DEFINITION.md` item 2, PARTIAL |
| Metadata | TagLib 2.3.1 (+ Ableton XMP sidecar writer) | `AbletonXmpWriter.*` |
| DSP features | `SampleManagerEngine.cpp` / `VectorMath.*` — energy, pitch/key, BPM, decay, ZCR, spectral centroid/rolloff, onset count | verified in source |
| Embedding | **PANNs CNN10** ONNX 512-D via **ONNX Runtime 1.29.0**, CoreML partitions where supported; ~23 MB model | `Models/panns_cnn10_embedding.onnx[.data]` |
| Classifier | Frozen 16-class softmax linear head (temperature 0.6864) over embeddings; filename/folder evidence outranks ML in the fusion hierarchy | `AcousticClassifier.h`, `AcousticClassifierWeights.h` |
| OOD gate | Nearest-centroid cosine + shrunk per-class thresholds; clears weak labels to Unknown | `AcousticClassifierCentroids.h`, `MlOverrideGate.h` |
| Storage | SQLite WAL cache, version-gated (`featureVersion`, `taxonomyVersion`, `embeddingModelVersion`), corruption quarantine + recovery | Task 4 audit |
| Search | HNSW nearest-neighbour + UMAP/knncolle/umappp 2-D map | `AudioSimilarity.h`, tests pass |
| Safety | Read-only scan verified with real SHA-256 before/after checksums (`TestReadOnlySafetyQualification`); Sort Library copy-by-default with journal/undo | B-013, B-011 closed |

### 1.3 Runtime signal chain (from architecture map)

```
WAV path / drag-drop
  → SampleManagerEngine (TagLib metadata + dr_wav decode + DSP features)
      → AbletonTaxonomy category/subcategory/tags (17 classes, v2)
      → filename/folder/embedded-metadata evidence (fusion hierarchy)
  → PANNs CNN10 ONNX embedding (512-D, background worker)
  → 16-class linear head + centroid OOD gate
  → SQLite cache + HNSW/UMAP + JUCE UI
  → confirmed Sort Library move/rename (opt-in only) + audition playback
```

### 1.4 Classification quality — current honest state

The repo's headline numbers have been corrected over time; use only the current ones:

| Metric | Value | Source |
|---|---|---|
| Synthetic repo benchmark | 96.54% acc / 96.45% F1 | **SUPERSEDED — do not quote** (`SLO_CLASSIFICATION_ACCURACY_REPORT_V1.md` banner) |
| Real corpus, 5,157 files, 15 vendors, all 17 classes | **71.5% full-evidence / 39.0% audio-only** acc; macro-F1 **0.527 / 0.395** | `SLO_ACCURACY_ROADMAP_V1.md` (V2 benchmark) |
| Full-evidence accuracy driver | filename/folder evidence wins 81.2%/77.9% of the time | same |
| OOD false-known rate (cross-vendor) | **72.0%**; false-unknown 17.7% | B-007, `SLO_PRIVATE_BETA_READINESS_V1.md` |
| Vocal Loop cross-vendor recall | **4.5%** (1/22) — claim suppressed | B-008 |
| Encoder research (21,793 rows, 5-fold OOF, seed 42) | PANNs+DSP **73.86% / 69.98 F1** vs CLAP-music+DSP **82.20% / 79.27 F1** (+8.34 / +9.29 pp, every class improved) | `SLO_ENCODER_RESEARCH_DECISION_2026-09-15.md` |
| Shipped subtypes | 808/Reese bass (92.9% holdout), open/closed hat (92.3%), kick length | `SLO_PRODUCER_TAXONOMY_REQUIREMENTS_V1.md` |
| Shipped attributes | 10 of 16 requested; 1 honestly rejected | same |

**Key gaps for "extremely high quality":**
1. **Audio-only accuracy (39.0%) is the bottleneck** — most accuracy comes from filenames, not sound.
2. **The proven CLAP encoder lift (+8–9 pp) is not shipped** — blocked on 7 promotion gates (see Phase 5); checkpoint is ~744 MB vs ~23 MB PANNs; C++ parity, packaging, latency, license all unmeasured; the +8.34 pp split is row-stratified so near-duplicate/pack leakage may inflate it.
3. **OOD gate is too permissive** (72% false-known cross-vendor); two recalibration attempts were rigorously tried and honestly reverted as null results (`docs/classification/OOD_RECALIBRATION_V1_REPORT.md`).
4. **Vocal Loop is effectively broken cross-vendor** (4.5% recall).
5. **WAV-only scanning** — no AIFF/FLAC/MP3 (decode pipeline is dr_wav-specific).
6. Corpus ground truth itself has labeling errors (Vocal Loop "BVs", FX folder-key bug) — the yardstick needs repair before the classifier can be judged against it.

### 1.5 Performance & host constraints

- Cold scan (170-file fixture): 25,043 ms mean; cached scan 921 ms; **peak RSS 2,439 MB** (`SLO_PERFORMANCE_REPORT_V1.md`).
- Real 100/1k/10k-file receipts: peak RSS grows sub-linearly 2.7 → 3.0 → **4.2 GB**; 30-iteration soak clean, no leak (B-009 closed).
- RT: 0/2000 `processBlock()` deadline misses, 0 allocations (`TestRtDeadlineStress`, B-010 closed); full RT sign-off still needs live Ableton validation (B-004).
- Model inference runs on a background worker; the audio thread only mixes prepared audition playback — so classification latency is a scan-throughput problem, not an RT-thread problem.

### 1.6 Beta gate status (blocker register V2, 2026-09-14)

| Status | Items |
|---|---|
| **Open — blocked on owner (Jack)** | B-001 Apple Developer ID signing/notarisation (P0); B-002 clean-machine validation (P0); B-003 production HTTPS licensing (P0); B-004 live Ableton matrix (P1); B-005 AL-002 blind review (P1, protected set) |
| **Closed with evidence** | B-006, B-007 (measured, not passed), B-009, B-010, B-011, B-012 (13,044-duplicate-symbol build break), B-013 |
| **Residual** | B-008 Vocal Loop claim suppressed; B-014 fine-grained taxonomy in progress |
| **Dirty tree** | 109 tracked modifications + 709 untracked files; beta candidate must be assembled by positive inclusion (`SLO_BETA_EXECUTION_STATUS_2026-09-15.md`) |

**Current verdict:** engineering validation progressing; **external beta NO-GO**.

---

## 2. Quality benchmark definition — "extremely high quality classification"

### 2.1 Measurement discipline (non-negotiable)

Everything below is measured with the programme's established leakage-free protocol:
- **Vendor/pack-grouped held-out splits** (row-stratified splits are known to inflate via near-duplicates — this is exactly why the CLAP +8.34 pp result is not yet a claim).
- **Separate metrics always reported**: audio-only vs full-evidence (filename/folder) vs fused — never blended.
- **Confidence intervals** for low-support classes, not point estimates.
- **Per-class F1 with support counts** published with every number.
- Owner-authorized sealed holdout (AL-002-style blind review) for any promoted claim.
- New hard gate: **duplicate-family isolation** — near-duplicate groups must not straddle train/eval.

### 2.2 Acceptance criteria for Beta 1 (shipping PANNs path, frozen)

| ID | Criterion | Target | Rationale |
|---|---|---|---|
| QA-1 | Full-evidence accuracy, vendor/pack-grouped, real corpus | ≥ 75% | Current: 71.5% on 5,157 files — modest, evidence-backed lift needed |
| QA-2 | Audio-only accuracy, vendor/pack-grouped | ≥ 45% | Current: 39.0% — recalibration + evidence-rebalance only; do not block beta on this if QA-1 passes |
| QA-3 | OOD false-known rate, cross-vendor | ≤ 30% | Current: 72% — the single worst trust-eroding number |
| QA-4 | OOD false-unknown rate (known population) | ≤ 15% | Current: 17.7% |
| QA-5 | Classes with suppressed claims (Vocal Loop etc.) | Claim stays suppressed OR dedicated remediation reaches cross-vendor recall ≥ 40% | B-008 |
| QA-6 | No regression on shipped subtypes (808/Reese 92.9%, hat type 92.3%) after any recalibration | Hold within 2 pp | regression gate |
| QA-7 | Perf: 1k-file cold scan ≤ 10 min; peak RSS ≤ 3.5 GB arm64, measured on signed candidate | B-009 baseline; protects DAW-host memory budget |
| QA-8 | Confidence calibration: High band precision ≥ 85% on repaired real corpus | New (banding shipped in readiness V2) | makes graduated confidence trustworthy |
| QA-15 | **OOD gate coverage**: on the frozen known-class reference set, the gate must accept ≥ 80% of cases the Python pipeline classified as known, and the test must **fail** if it does not | New — added 2026-09-17 | `TestAcousticClassifierParity` skips OOD cases (`if (!res.isOod && ...)`), so a gate rejecting 100% of input passes the suite. This is the exact hole a build whose every output is `UNKNOWN` escaped through. See receipt §5b.1 |
| QA-16 | **Candidate identity integrity**: every receipted identity value (taxonomy version, model version, weight-set hash) is recorded *with the checkout path it was read from*, and cross-checked against the alternate worktree | New — added 2026-09-17 | The 2026-09-17 receipt recorded `kTaxonomyVersion = 5` for a candidate that actually shipped `= 2`, because the value was read from the main tree. A superseded classifier base was selected on the strength of that untested assumption |

**Beta 1 does not require the CLAP encoder.** Beta 1 requires *honesty + OOD trustworthiness*; Phase 5 promotes CLAP for Beta 2.


### 2.3 Acceptance criteria for "extremely high quality" (post-beta, CLAP-era)

| ID | Criterion | Target |
|---|---|---|
| QA-9 | Audio-only accuracy, vendor/pack-grouped, duplicate-family-isolated | ≥ 70% |
| QA-10 | Full-evidence accuracy | ≥ 85% |
| QA-11 | OOD false-known | ≤ 10% |
| QA-12 | Per-class F1 floor | no class < 0.55 F1 (with CIs); weak classes named, not hidden |
| QA-13 | Inference cost | per-file embedding ≤ 150 ms arm64 CPU fallback; 1k-library index ≤ 8 min; peak RSS ≤ 4 GB |
| QA-14 | Blind review | owner-authorized sealed set passes pre-declared protocol |

### 2.4 Evaluation assets (already exist — verify, don't rebuild)

- **Real corpus V2**: 5,157 licensed files, 15 vendors, all 17 classes (`docs/classification/REAL_CORPUS_CROSS_VENDOR_V2_REPORT.md`) — primary benchmark.
- **CLAP benchmark tooling + model archives** under `SmartSampleManager/tools/classification_benchmark/` (some archived as `.tgz` in `Nite-DSP-Operations/products-archive/slo` per `cleanup-deletions-2026-09-17.md` — re-extract if needed).
- **21,793-row training corpus** + encoder-quality receipt (`_artifacts/slo_encoder_quality_detailed_20260915.json`, SHA-256 `83c8ab41…62682f`).
- **OOD cross-vendor gate corpus** (168 genuinely out-of-taxonomy files; 620 known set).
- **Owner-labeled taxonomy queues**: 624 unique-hash consolidation, two 120-row master batches, duplicate-safe merger, localhost reviewer (B-014 evidence).
- **Required new asset**: a **corpus-label-repair pass** (FX/Foley folder-mix bugs, "BVs"-class labeling errors) with an owner-approved changelog — QA numbers are meaningless until the yardstick is repaired.

---

## 3. Roadmap to Beta

Phases follow the critical path from the master plan, with the classification-quality track interleaved. Estimates assume credentials + clean Mac available (master-plan horizon: 6 focused weeks, up to 12 calendar).

### Phase 0 — Owner decisions (Day 0; blocks everything below)

| # | Decision | Options | Recommendation |
|---|---|---|---|
| D-1 | **WAV-only vs multi-format for Beta 1** | ship WAV-only documented vs close AIFF/FLAC/MP3 decode | WAV-only acceptable (28,330-file real-corpus survey shows WAV dominance); document limitation |
| D-2 | **Approve the QA-1..QA-8 gate table** (§2.2) or amend | accept / amend | accept — targets are evidence-derived |
| D-3 | **Authorize corpus-label repair** (touching benchmark ground truth needs owner sign-off) | yes/no | yes — no honest accuracy claim possible until then |
| D-4 | **Re-open OOD threshold spec** (B-007 is spec-frozen; two null attempts done) | reopen with vendor-grouped method vs ship with graduated "likely X" labels | ship graduated Unknown UX for Beta 1; reopen OOD only via vendor-grouped method |
| D-5 | **CLAP promotion lane**: authorize parallel post-beta branch + deployment-cost study (744 MB, CPU fallback, distillation/quantisation options) | now / after beta | authorize cost study now; promotion stays gated per the 7 gates in `SLO_ENCODER_RESEARCH_DECISION_2026-09-15.md` |
| D-6 | Start Apple Developer ID enrollment **now** (long lead time) | — | per B-001 |

### Phase 1 — Foundation: clean, reproducible candidate (Week 1) — **EXECUTED 2026-09-17, see §0**

**Tasks**
1. Dirty-tree inventory into buckets: shipping / test / evidence / generated / research / unrelated. ✅ done — 13 modified shipping files, 380 untracked, bucketed in the assembly receipt §3.
2. Create clean beta worktree by **positive inclusion**; reproduce full build + the test sweep from it. ✅ done — worktree from `codex/slo-beta-1-assembly@f9b502e`, 870 files, 0 dirty; build 100%; sweep 40/41.
3. Freeze model/taxonomy/preprocessing identity (ONNX hash, `kTaxonomyVersion`, temperature, class order) into a candidate receipt. ✅ done — receipt §4 (model SHA-256, `kTaxonomyVersion = 5`, temperature `0.686393678188324`).
4. Re-verify read-only safety + production-cache guard on the candidate. ✅ `TestReadOnlySafetyQualification`, `TestSafetyRegression`, `TestCacheIntegrity`, `TestCacheVersionEnforcement` all PASS.

**Additional outcome not in the original task list:** a **P0 inference-blocking defect** was discovered and fixed (§0, receipt §5a). Phase 1's purpose — producing a candidate you can actually trust — is what surfaced it; the gate worked.

**DoD:** clean tree pushes ✅; immutable candidate builds ✅; full native suite passes from the candidate ⚠️ (40/41, 1 environmental); identity receipt published ✅.
**Remaining owner action:** commit the P0 fix; review the 8-commit inclusion surface.
**Risk realized:** the defect proves the value of building from a clean candidate rather than trusting the dirty tree.
**Dependencies:** none. **Effort:** 3–5 days.
**Risk:** research material entangled with shipping code (`tools/` has 490 untracked files) — mitigate by including, not bulk-deleting.

### Phase 2 — Classification quality track, Beta 1 scope (Weeks 1–3, parallel with Phase 1)

**Tasks**
1. **Corpus-label repair** (D-3): FX/Foley/Riser folder-mix bugs, abbreviation gaps; owner-reviewed changelog; regenerate the V2 benchmark after repair.
2. **Evidence-hierarchy rebalance diagnostics**: per-class audio-only vs filename evidence win rates; identify classes where filename evidence actively *harms* (V4-H showed Vocal Loop damaged by filename outranking ML).
3. **Graduated Unknown UX**: restructure the result model from binary known/Unknown to "likely category + possible subtype + attributes + confidence" (gap confirmed in `SLO_PRODUCER_TAXONOMY_REQUIREMENTS_V1.md` §Unknown handling) — the honest Beta 1 answer to the 72% false-known number.
4. **Confidence calibration measurement** (QA-8): High-band precision on repaired corpus; retune banding only under the pre-declared protocol.
5. **Vendor/pack-grouped re-evaluation** of the shipping classifier on the repaired corpus → QA-1..QA-5 receipts.
6. **Regression guard**: rerun subtype tests (bass timbre, hat type, kick length) against any recalibration (QA-6).

**DoD:** QA-1..QA-6 receipts exist from the exact candidate; every user-facing claim matched to evidence; anything failing QA-5 stays claim-suppressed.
**Dependencies:** D-2, D-3, D-4 decided. **Effort:** 2–3 weeks (evaluation compute is modest; **no model training is required for Beta 1**).
**Risk:** recalibration attempts historically return null results — the gate table is designed so honest graduated labels still ship.


### Phase 3 — Release hardening of the exact candidate (Weeks 2–4)

**Tasks** (from the master-plan critical path)
1. Production HTTPS licensing: activation, offline grace, expiry, revocation, outage drills (B-003 — needs owner credentials).
2. Sign, notarise, staple, manifest, checksum all artifacts (B-001).
3. Clean-Mac install/reinstall/uninstall + Gatekeeper assessment (B-002).
4. Ableton Live exact-artifact matrix: scan, instantiate, preview, drag, save/reopen, missing-drive (B-004).
5. UI gaps from readiness V2: **scan-progress indicator** (confirmed missing from `PluginEditor.cpp`), empty/error states walkthrough.
6. Performance gates on the signed build: 100/1k/10k cold/warm/rescan timings, peak/post RSS, soak, cancellation (QA-7).
7. Sort Library: keep beta-flagged **OFF** unless its exact build passes preview/Copy/Move/cancellation/journal/Undo acceptance on disposable fixtures.

**DoD:** §13 of `SLO_BETA_EXECUTION_MASTER_PLAN_V1.md` met for engineering items; blocker register updated with receipts.
**Dependencies:** Phase 1; B-001/002/003/004 unblocked by owner. **Effort:** 2–3 weeks.
**Risk:** RSS ceiling vs DAW host — mitigation documented (one-instance guidance, bounded-corpus guidance in pilot).

### Phase 4 — Pilot & private beta (Weeks 5–8)

1. 2–3 person internal pilot with hard gates: no file mutation, no host crashes, RSS within ceiling, licensing stable.
2. 5–8 producer cohort; opt-in correction capture with **embedding-only logging** (512-D vector, no audio upload — privacy-positive, already recommended in `SLO_ACCURACY_ROADMAP_V1.md` Stage 3); extend `tagUserOverridden` to structured correction records.
3. Feedback instrumentation focused on: false positives, Unknown behaviour, memory, host stability (per readiness V1 pilot controls).
4. Support runbook live + stop-the-line incident policy for any source-file mutation.

**DoD:** pilot + cohort metrics pass; blocker register and receipts archived; internal pilot meets the hard gates of the master plan.

### Phase 5 — Post-beta: the "extremely high quality" promotion (Beta 2 lane; starts during Phase 4)

Runs the **7 promotion gates already pre-declared in `SLO_ENCODER_RESEARCH_DECISION_2026-09-15.md`** against the CLAP-music+DSP candidate (+8.34 pp acc / +9.29 pp macro-F1 evidence):

1. Vendor/pack-grouped **blind** evaluation with duplicate-family isolation (fixes the known inflation risk of the row-stratified +8.34 pp result).
2. No material class regression; confidence intervals for low-support classes.
3. **Python→C++ export parity** for CLAP preprocessing/inference (does not exist; the production C++ path is PANNs-only today).
4. Signed-Release measurements: package size (~744 MB checkpoint vs ~23 MB PANNs!), cold start, per-file latency, 1k/10k throughput, peak RSS, **CPU fallback**, AU/VST3 host stability.
5. Redistribution-license + third-party notices legal review (CLAP checkpoint weights are not owned).
6. OOD/Unknown threshold recalibration for the new encoder with false-confident-error limits.
7. Immutable separate candidate + rollback plan — **never an in-place Beta 1 branch swap**.

Also in this lane: taxonomy completeness decisions (Pad/Stab primary slots; guitar/orchestral/world classes — a periodic product decision per `SLO_ACCURACY_ROADMAP_V1.md` Stage 4), remaining subtypes (sub/distorted bass, acoustic snare/rimshot, crash/ride) via the proven separability-first method, and — only once real users exist — the correction-aggregation backend and a real training pipeline (Stages 6–7 of the accuracy roadmap; do **not** build speculatively).

**Effort:** 4–8 weeks after beta start; gated by QA-9..QA-14.
**Risks:** model size and redistribution rights are the top two open questions; both get early decision points (D-5 cost study) so they cannot ambush Beta 2.

---

## 4. Risk register (top 5)

| Risk | Impact | Mitigation |
|---|---|---|
| CLAP lift doesn't survive vendor/pack-grouped, duplicate-isolated eval | Beta 2 quality claim collapses | run gate 1 **early** in Phase 5; PANNs path stays frozen and shippable regardless |
| ~744 MB model kills packaging/memory budget | encoder promotion blocked | D-5 deployment-cost study (distillation/quantisation options) before any C++ port work |
| OOD false-known stays >30% after repair | user trust in labels erodes | graduated "likely X, uncertain" UX is the Beta 1 answer; OOD recalibration is Beta 2 |
| Owner-blocked items (B-001..B-005) slip calendar | beta delayed regardless of engineering | start Apple enrollment + credential requests Day 0 (D-6) |
| Benchmark ground-truth errors contaminate all claims | every number untrustworthy | corpus-label repair (Phase 2.1) precedes all re-measurement |

---

## 5. One-page sequence

```
Day 0    D-1..D-6 owner decisions; start Apple Developer ID (long lead)
Week 1   Phase 1 clean candidate        | Phase 2 corpus-label repair begins
Week 2-3 Phase 2 QA-1..QA-6 receipts    | Phase 3 licensing/signing/clean-Mac
Week 3-4 Phase 3 Ableton matrix, perf gates, UI gaps
Week 5-6 Phase 4 internal pilot -> 5-8 producer private beta
Week 5+  Phase 5 CLAP promotion gates (parallel lane) -> Beta 2
```

**Bottom line:** SLO's engineering and evidence discipline is unusually strong (every number receipt-backed, null results honestly published). The path to beta is: clean candidate → honest Beta 1 quality gates (measured on a repaired corpus, with trustworthy OOD/Unknown behaviour) → owner-blocked release ops → pilot. The genuinely large classification-quality leap (+8–9 pp from the CLAP encoder) is already proven at research level and sequenced for Beta 2 through seven pre-declared promotion gates.

