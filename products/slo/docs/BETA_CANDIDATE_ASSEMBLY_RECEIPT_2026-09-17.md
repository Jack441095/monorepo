# SLO Beta 1 Candidate Assembly Receipt V1

**Date:** 2026-09-17
**Executed by:** Cline (autonomous), Phase 1 Tasks 1–3 of `docs/ROADMAP_TO_BETA.md`
**Mode:** read-only against the main working tree; no files in `products/slo` modified, committed, or deleted.

## 1. Candidate worktree materialized

- Source: branch `codex/slo-beta-1-assembly` at `f9b502e` (tip of `origin/main`).
- Location: `/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/workspace/worktrees/slo/beta-1-assembly`
- Status: **870 files, 0 dirty** — a genuinely clean checkout.
- 7 stale worktree registrations pointing at the old volume path (`/Volumes/Jack_Gandy_1TB_SSD/NITE_DSP/...`, renamed to `Nite-DSP`) were pruned via `git worktree prune` before re-materializing.

## 2. Relationship to local main

- Local `main` is `dc855be` = `f9b502e` + **8 unpushed commits** (the assembly branch is an ancestor, not a fork).
- The 8 commits (inclusion-review surface):
  1. `ebbb164` perf Phase 1: skip inference-batch grace wait once scan pool drains
  2. `8dcee3b` perf Phases 2+3: measured 16/32 batch defaults + pathToIndex map
  3. `52a0951` perf Phase 4: progress-based benchmark wait + measured 5k/10k tiers
  4. `7b0a6ce` Phase 5 deliverable: `SLO_VOCAL_DISAMBIGUATION_PROPOSAL.md`
  5. `6990093` qualification session's remaining uncommitted state
  6. `970fad1` Vocal fix measured on reconstructed real corpus
  7. `04e9d47` survey-timing-split
  8. `dc855be` test: reproduce reversed audition tempo calculation
- Combined diff vs assembly branch: 67 files, +40,351/−4,071 — includes production changes in `SampleManagerEngine.*`, `PluginProcessor.*`, `AuditionTempo.h`, `CMakeLists.txt`, `CMakePresets.json` plus new tests (`test_inference_batch_flush`, `test_label_free_evidence_packet`, `test_path_index_integrity`, `test_physical_acoustics`, expanded `test_sort_preview_and_undo`).
- **Inclusion decision pending owner/engineering review** — these commits are the primary review surface for folding into the beta candidate.
- Note: this clean branch already ships the `SLO.vst3` product naming (build produces `SLO.vst3`).

## 3. Dirty-tree inventory of the OLD main working tree (Phase 1 Task 1)

Current live status of the `products/slo` checkout (smaller than the 2026-09-15 preflight's 109 M + 709 ??, now **30 M + 380 ??** — partial consolidation happened since):

| Bucket | Contents | Disposition |
|---|---|---|
| Shipping-code review | 13 modified: `CMakeLists.txt`, `CMakePresets.json`, `AuditionTempo.h`, `PluginProcessor.{h,cpp}`, `SampleManagerEngine.{h,cpp}`, `SLO_BETA_BLOCKER_REGISTER_V2.md`, taxonomy docs | review for inclusion into candidate |
| Shipping-code review (untracked) | `Source/SortFileSafety.h`, `Source/test_umap_eligible_main.cpp` | SortFileSafety likely ships; test goes with tests |
| Test/evidence code | `tools/classification_benchmark/{mw_features,physics_cache}.py` (modified); untracked docs `SLO_PERF_AND_REALTIME_PASS_V1.md`, `SCALE_TIER_RESULTS.md`, `SLO_RT_DEADLINE_STRESS_V1_REPORT.md` | include with candidate or evidence bucket |
| Research / generated | `SmartSampleManager/tools/classification_benchmark/`: 332 untracked (184 py, 102 json, 27 jsonl, 7 csv, 6 log, 4 h, 1 cpp, plus `ground_truth/frozen/` dir) | research bucket — stays out of shipping lineage |
| Receipts (root) | 32 untracked root files: `SLO_*.md` reports + `slo_*.json` receipts | evidence bucket — publish alongside, not inside shipping tree |
| Unrelated workstream | `nitedsp/website/` 15 modified (account/beta/eula/legal/pricing pages, package.json) + 3 untracked backend files | NOT part of the SLO beta candidate — separate workstream |

## 4. Candidate identity capture (Phase 1 Task 3)

| Item | Value |
|---|---|
| Git HEAD (candidate) | `f9b502e0c511f040b6d70087e03f4d02c94f3557` |
| Local main | `dc855bee2e7f0cb8e66973df28c229f9542ec480` (8 ahead, unpushed) |
| Model | `panns_cnn10_embedding.onnx` — SHA-256 `cbc3653cf2ef3cc35f6be48c4863b6d735b0ff85af3b3e9607706a0f467ffad2` (84,379 B) — **byte-identical in both worktrees** |
| Model data | `panns_cnn10_embedding.onnx.data` — SHA-256 `8e2b47834248ba6ba0e0993bedcac8babd01666e82a5faf77aaeaca69fa086a8` (24,248,320 B) |
| Classifier head | **branch `f9b502e`: `AcousticWeights::modelVersion = 4` / main `dc855be`: `modelVersion = 6`** — different weights files |
| Taxonomy version | **branch `f9b502e`: `kTaxonomyVersion = 2` / main `dc855be`: `kTaxonomyVersion = 5`** (`AbletonTaxonomy.h:26`) |

> **Correction to this receipt's own earlier draft:** the taxonomy value previously recorded here (`= 5`) was read from the *main tree*, not from the candidate worktree. The candidate branch actually carries `kTaxonomyVersion = 2`. This was caught by cross-checking both checkouts side by side and is the same class of error that §5b is about — never trust an identity value without naming the checkout it came from.

### 4a. Two different classifier weight sets in this repository

The embedding model is shared, but the **16-class head and the OOD centroids are not**:

| Artifact | Branch `f9b502e` (candidate) | Main `dc855be` |
|---|---|---|
| `AcousticClassifierWeights.h` | `modelVersion = 4` | `modelVersion = 6` (7296-line rewrite in `6990093`) |
| `AcousticClassifierCentroids.h` thresholds | `0.95965, 0.93450, 0.95773, ...` (all ≥ 0.93) | `0.7480, 0.8092, 0.8500, ...` (0.71–0.85) |
| File size of centroids header | 110,839 B | 107,612 B |
| `kTaxonomyVersion` | 2 | 5 |

The main-tree thresholds are **byte-equal to the values in the training export scripts' own outputs** (`AcousticClassifierCentroids_v5.h` / `_v6.h` in `tools/classification_benchmark/`), which is independent evidence that main carries the exported, calibrated set and the branch carries a superseded one.

## 5. Build qualification (Phase 1 Task 2)

- Environment blocker found and resolved: `/usr/local/bin/cmake` is x86_64/Rosetta and cannot dlopen the arm64 CommandLineTools `libxcrun` → configure failed. Fixed by using `/opt/homebrew/bin/cmake` (arm64, 4.4.3) first in PATH. **Record this for the runbook.**
- `cmake --preset ssm-qualification` (Release, plugin LTO, tests no LTO, build tree outside checkout at `_build/ssm-qualification`): **PASSED** (exit 0, 115.2 s).
- Build of plugin + test/benchmark executables: **PASSED** — `[100%] Built target TestSafetyRegression`, 41 test binaries + `ClassificationBenchmark` + `BenchmarkScan` produced. Logs: `slo-qual-build.log` (first attempt), `slo-rebuild.log` (post-fix, `/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/workspace/`).

### 5a. P0 defect found by qualification — embedding-output validator rejected every inference

The first sweep failed 12 of 41 tests. Root cause located in the candidate branch itself, introduced by its own hardening commit:

| Item | Value |
|---|---|
| Defect | `hasExpectedEmbeddingOutput()` validated the ONNX output width against `AcousticWeights::embeddingDim` (520) while PANNs CNN10 emits `[batch, 512]` — the error text even reported 512 |
| Introduced by | `a7d56da` "fix(slo): validate embedding tensor outputs" (present in `f9b502e`, the candidate base) |
| Impact | **Deterministic total inference failure** on every scanned file — classification returns nothing; the model never actually ran. Silent in the sense that it is a validation predicate, not a crash |
| Related second instance | `hasSafeEmbeddingBuffer()` carried the identical confusion: it checked the persisted 512-D PANNs vector against the 520-D classifier-input width, which would have rejected every cache-hydrated row and restored the "hydrated rows are never classified" defect |
| Fix applied | Compare against `AcousticClassifier::pannsDim` (512) in both predicates; `AcousticClassifier.h:23` defines it and `:25` pins `static_assert(pannsDim + dspFeatureDim == AcousticWeights::embeddingDim)`, so 512 and 520 stay mechanically tied |
| Diff size | 1 file, +10/−4 in `Source/SampleManagerEngine.cpp`, comments only otherwise — no behavioural change beyond the two widths |
| Verification | Rebuilt clean; `TestAcousticClassifierInputSafety`, `TestAcousticClassifierParity`, `TestEmbeddingQuality` now pass |

**Before/after on the same 41 binaries, same build tree, same machine:**

First sweep (buggy base) — 12 failures:
`TestCacheVersionEnforcement, TestEmbeddingQuality, TestFindSimilar, TestFindSimilarWeighted, TestFormatAwareScan, TestLicensing, TestMalformedAudio, TestNearDuplicates, TestPersistedCacheHydration, TestReferenceSearch, TestSampleEngine, TestTimbreRefinement`

Second sweep (after fix) — **TOTAL pass=40 fail=1 failed=TestLicensing**

11 of the 12 failures were caused by the single width mismatch. The 1 residual failure is environmental, not a defect: bare `TestLicensing` requires a live activation key/endpoint (roadmap blocker **B-003**). Its offline mode passes — `./TestLicensing --url-policy` → `ALL LICENSING URL POLICY TESTS PASSED SUCCESSFULLY!` (exit 0).

Failure signatures were a coherent cluster — similarity search, cache hydration, version enforcement, malformed audio, timbre refinement all consume the 512-D embedding that the validator was rejecting. This is consistent with, and confirming of, the single-root-cause diagnosis rather than 12 independent bugs.

Logs: `workspace/slo-test-sweep.log` (first), `workspace/slo-sweep2.log` (second).

**Interpretation for the roadmap:** this is precisely the class of defect QA-1..QA-14 exist to catch, and it is evidence that *no prior accuracy number was measured with a working inference path on this branch lineage*. Any benchmark quoted for this candidate must be regenerated before it can be trusted (roadmap §2 caveat).

**Status: fix present as an uncommitted working-tree change in the candidate worktree — commit/push is an owner decision (it must not be silently folded into the branch history).**

### 5b. P0 (BLOCKING) — the chosen candidate base is superseded and cannot classify correctly

The P0 in §5a was fixed inside the `f9b502e` worktree and recovered 11 tests. That was **necessary but not sufficient**, and it was the wrong place to fix it. Building the engine and running it end-to-end on real audio exposed the real problem.

**End-to-end evidence.** `ClassificationBenchmark scan` was run on 20 real corpus files (the first 20 of the frozen 5,157-file `real_corpus_v2/audio_only` set, all genuinely `Bass One-Shot` from `MGF Mega Pack`) using the `f9b502e` build:

| Field | Observed |
|---|---|
| `diagMlEvaluated` | `true` (the §5a fix did restore inference) |
| `embedding` | 512 floats, 321 non-zero — a real embedding, not a stub |
| `diagMlSubcategory` | `Foley` (wrong) |
| `diagMlConfidence` | 0.263 |
| `diagMlCentroidCos` | **0.462** |
| `diagMlIsOod` | **`true`** |
| `subcategory` (product output) | **empty — every file presented as `UNKNOWN`** |

**All 20/20 in-distribution files were rejected as OOD.** The product would show "Unknown" for the entire library.

**Why.** The OOD gate is `bestCos < perClassOodThreshold[bestClass]`. In `f9b502e` every per-class threshold is ≥ 0.93 (`0.95965, 0.93450, 0.95773, 0.97027, ...`), while a genuine training-class sample scores 0.462. The thresholds are not tunable noise — they were **exported from a superseded classifier**:

- Branch `f9b502e`: `AcousticWeights::modelVersion = 4`, `kTaxonomyVersion = 2`, thresholds 0.93–0.977
- Main `dc855be`: `AcousticWeights::modelVersion = 6`, `kTaxonomyVersion = 5`, thresholds 0.71–0.85

The main-tree threshold vector is byte-equal to `AcousticClassifierCentroids_v5.h` / `_v6.h` produced by the repository's own export tooling — i.e. main carries the calibrated export and the branch carries an obsolete one.

**Git proof.** Two of the eight commits by which local main is ahead of the branch are *not* optional:

| Commit | Subject | Why it is required |
|---|---|---|
| `ebbb164` | SLO perf Phase 1: skip inference-batch grace wait once scan pool drains | **Also contains the `pannsDim` validator fix.** This is the commit that repairs §5a. `git merge-base --is-ancestor ebbb164 f9b502e` → **false** |
| `6990093` | Commit the 2026-09-14 qualification session's remaining uncommitted state | Rewrites `AcousticClassifierWeights.h` (7296 lines), `AcousticClassifierCentroids.h`, `AcousticClassifier.h`, and the taxonomy to v5 |

Its own message states the motivation: *"branch self-consistency … a fresh clone of the branch could not previously compile or reproduce the test results."* That is precisely the condition observed here.

**Consequence — the candidate must be rebuilt from `dc855be`.** The §5a edit is *not needed* on main, because main already contains it:

```
dc855be:SmartSampleManager/Source/SampleManagerEngine.cpp
  124:  && shape[1] == AcousticClassifier::pannsDim
  239:  return embedding.size() == static_cast<size_t>(AcousticClassifier::pannsDim)
```

The same Local main vs `origin/main` gap was already flagged in §2 of this receipt as "inclusion decision pending". That framing understated it: **the 8-commit gap is not an optional inclusion review — it contains the fix for total inference failure and the current classifier.** Shipping from `f9b502e` would ship a plugin that labels every file Unknown.

**Action taken:** a second worktree was materialized at `dc855be` (`workspace/worktrees/slo/beta-1-main`) and is being built and re-validated. The `f9b502e` worktree's §5a edit is retained as a record but should **not** be merged forward — main already has the correct predicate.

#### 5b.1 Controlled experiment — identical embeddings, only the header varies

`ClassificationBenchmark` feeds the *runtime* embedding, so it cannot isolate the classifier from the embedding extractor. To separate the two, the 50 frozen embeddings stored in `tools/classification_benchmark/parity_references.json` (real cases the Python pipeline classified as known classes, held constant) were re-scored against each header's centroids and thresholds directly, parsed from the C++ source:

| Header | best-centroid cosine (median) | rejected as OOD |
|---|---|---|
| Main `dc855be` (`modelVersion = 6`) | **0.9230** (min 0.6148, max 0.9886) | **4 / 50 = 8%** |
| Branch `f9b502e` (`modelVersion = 4`) | 0.3876 (min 0.2867, max 0.4594) | **50 / 50 = 100%** |

Same inputs, same day, same machine. **The branch's centroids are not merely mis-thresholded — they occupy an incompatible embedding space.** Main's acceptance rate of 92% is consistent with the 5th-percentile design in `train_gpu_classifier_v2.py:292` (≈95% expected acceptance); the branch's 0% is not consistent with any calibration intent.

**Two further conclusions this isolates:**

1. **The embedding extractor is not the problem.** The *runtime* embeddings from the branch build scored median cosine 0.363 against the branch's centroids (see §5b table: `diagMlCentroidCos`), and the *frozen training-time* embeddings score 0.3876 against those same centroids. Runtime and training embeddings therefore land in the **same** space — the PANNs path is consistent. The defect is entirely in the shipped classifier head/centroids.
2. **`TestAcousticClassifierParity` cannot catch this.** `Source/TestAcousticClassifierParity.cpp:364` reads:

   ```cpp
   if (!res.isOod && res.subcategory != expectedSub)   // OOD cases are silently skipped
   ```

   All 50 reference cases are labelled with a known class, so a gate that rejects **100%** of them still reports **PASS**. This test validates the head's logits and the gate's arithmetic, but not its calibration. It is why a build whose entire output is `UNKNOWN` shipped through a green suite. (Roadmap action: add a gate-coverage assertion — see QA-15.)

### 5c. Main candidate (`dc855be`) re-validation — the correct base

The main worktree was configured, built, and run end-to-end on the **same 20 real corpus files** used for the `f9b502e` failure above.

| Metric | Branch `f9b502e` (model v4) | Main `dc855be` (model v6) |
|---|---|---|
| `Unknown` (product output empty) | **20 / 20 = 100%** | **0 / 20 = 0%** |
| Classified as a known class | 0 / 20 = 0% | **20 / 20 = 100%** |
| `diagMlCentroidCos` median | 0.3632 (max 0.4635) | **0.9169** (min 0.8445, max 0.9391) |
| Flagged OOD | 20 / 20 | **0 / 20** |
| Audio-only accuracy on the 20 | 0% | **55%** (11/20) |

The 0.9169 observed median is within 0.01 of the 0.9230 predicted independently in §5b.1 from the frozen reference embeddings — the two methods agree, so neither is an artefact of the other.

**Build:** `cmake --preset ssm-qualification` + build → `BUILD_EXIT=0`, all three product artefacts produced (`SLO.component` AU, `SLO.vst3` VST3, `SLO.app` standalone), plus the test and benchmark executables.

**Conclusion:** `f9b502e` was the wrong base. `dc855be` is the correct beta candidate base, and no source edit is required on it — it already contains the corrected predicate.

---

- D-1 default: Beta 1 ships WAV-only (documented limitation).
- D-3 default: corpus-label repair authorized for Phase 2 (not yet executed).
- D-4 default: graduated Unknown UX is the Beta 1 answer to OOD false-known; threshold spec NOT reopened.
- D-5 default: CLAP stays a post-beta lane; no C++ port started.
- D-6: **cannot be executed by a session** — Apple Developer ID enrollment needs the owner.

## 7. Next steps

1. ~~Await build result~~ **DONE** — build PASSED, 41 binaries + 2 benchmarks produced.
2. ~~Run the full test sweep on the candidate~~ **DONE** — 40/41 PASS. The single failure is environmental (B-003 licensing endpoint), not a code defect.
3. **OWNER DECISION — commit the P0 fix** (§5a). It is currently an uncommitted working-tree change in the candidate worktree. It should be committed as its own reviewable change with the receipt cross-referenced; without it, the candidate cannot classify anything.
4. Owner/engineering review of the 8-commit inclusion surface (§2).
5. Decide whether perf phases 1–4 ride into Beta 1 (recommended: yes — they are the measured batch/scan improvements and come with new tests).
6. **Regenerate every accuracy/performance number on this fixed candidate** before quoting any figure (roadmap §2). Prior figures in `SLO_CLASSIFICATION_ACCURACY_REPORT_V1.md` / `SLO_PERFORMANCE_REPORT_V1.md` were measured on a lineage where, on this branch's validator, inference would not have run at all — the numbers must be re-established against a known-working inference path.

## 8. Qualification status summary

| Gate | Status |
|---|---|
| Candidate materialized, clean checkout | ✅ 870 files, 0 dirty |
| Configure (arm64 cmake) | ✅ PASSED (115.2 s) |
| Build (plugin + tests + benchmarks) | ✅ PASSED, 100% |
| Test sweep | ⚠️ 40/41 PASS; 1 environmental (B-003) |
| P0 regression fixed & verified | ✅ 11 tests recovered |
| P0 fix committed | ❌ owner decision |
| Evidence regenerated on fixed candidate | ❌ pending (roadmap Phase 2) |
| Apple signing (B-001), clean machine (B-002) | ❌ owner-gated |
| Live Ableton validation (B-004) | ❌ pending |
| Blind review (B-005) | ❌ pending |

**Bottom line:** the candidate moves from *"cannot classify anything"* to *"code-complete and test-clean, pending owner-gated release prerequisites and fresh evidence."*
