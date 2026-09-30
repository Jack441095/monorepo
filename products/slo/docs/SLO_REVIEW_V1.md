# SLO — FULL CODE REVIEW V1

**Date:** 2026-09-30
**Scope:** `products/slo` at `bec0161` — 21 C++/JUCE source files plus headers, the Python classification pipeline, build system, and the ~60-file report corpus at the product root
**Reviewer:** read-only pass, then repair. Phase A findings below; Phase B/C repairs follow in the commit history.
**Verdict:** `NOT READY` — four P0s are documentation and data, two are audio-thread defects, and one benchmark metric does not measure what it claims.

Evidence discipline: `OBSERVED` (file:line or command output) → `INFERRED` severity → `UNVERIFIED`.

---

## Two facts a report does not know

Both were asserted as critical gaps in the corpus and are already closed in code. An agent re-reading those reports will re-raise dead blockers.

1. **The scan path is format-aware, not WAV-only.** `Source/SampleManagerEngine.cpp:2188` walks `"*"` and admits by `formatManager.findFormatForFileExtension()` (`:2192, :2199`). `Source/test_format_aware_scan_main.cpp:91-92` covers `AiffAudioFormat` and `FlacAudioFormat`, with CMake target `TestFormatAwareScan` (`:868`). The repo's own `validation/class-opt-v1/FORMAT_SUPPORT_CORRECTION.md:4-6` already says so.
2. **`PRODUCT_NAME` is `"SLO"`** (`CMakeLists.txt:491`). The old bundle identity (`BUNDLE_ID com.nitedsp.smartsamplemanager` `:481`, `PLUGIN_CODE AtSm` `:489`) is *not* fixed. Reports treat both halves as uniformly unfixed.

---

## Phase A1 — Plugin core

### Blockers

**A1-b1 — Audio-thread resource teardown.** `PluginProcessor.cpp:203-211`: `startPreparedPlayback()` is reached from `processBlock` via `:112-114`. Line 208 move-assigns `readerSource`, which frees the previous `AudioFormatReaderSource` → `BufferingAudioReader` → format reader, including a multi-hundred-KB `free()` and a file-descriptor close on a real-time thread. `PluginProcessor.h:67-68` claims "no allocation beyond the trivial pointer swap", which is true of the swap and false of the destructor.

**A1-b2 — `transportSource` touched from three threads unsynchronised.** `juce::AudioTransportSource` is not thread-safe. Audio thread: `processBlock` `:118-126`, `startPreparedPlayback` `:206-210`. Message thread: `playSample` → `:152`, `stopSample` → `:218,221`. `stopSample()` reading `isPlaying()` and calling `stop()` while `processBlock` is inside `getNextAudioBlock()` races `positionSeconds` and the source's internal state; the `:152` handoff races the `:208` write, which is a use-after-free rather than a torn flag.

**A1-b3 — `QuadTree` infinite recursion on coincident points.** `QuadTree.h:27-57`: `subdivide()` has no depth cap and no minimum-bounds guard, and `insertIntoChildren()` (`:56`) routes every non-contained point into the same child. `SampleManagerEngine.cpp:5062-5066` deliberately parks samples with no usable embedding at `(0,0)`, and `:5071-5072` does the same when HNSW returns no neighbours, so ≥33 such points recurse forever and overflow the stack on the message thread inside `rebuildSpatialIndexFull()` — reached from the 60 Hz editor timer (`PluginEditor.cpp:1199, :1277`). An editor crash on plugin open with a 33-file library.

### Major

- `SampleManagerEngine.cpp:6022-6023` — `size_t`→`int` narrowing on a resample buffer. Upsampling a long field recording wraps negative, so `copyLength < 0` and `resampled.begin() + copyLength` walks before the buffer.
- `:5937` — the entire file is decoded into a `std::vector<float>` to validate a WAV header, then decoded again at `:5981`. `channels` is an unvalidated `unsigned int` from the RIFF header feeding an unbounded `size_t` product.
- `:7007` — `reorganizeSamples()` holds `dbLock` across the whole sort, including per-row flushed journal writes `:7181-7208`. The 60 Hz timer calls `getSamples()` at `PluginEditor.cpp:1233`, so the UI freezes and cannot render the progress text it writes at `:1357-1361`.
- `:7262` — `undoLastSort()` takes `dbLock`, then calls `getMostRecentSortJournal()` which takes it again at `:7222`. Safe only because `juce::CriticalSection` is a recursive mutex, which the surrounding locking contract (`:2396, :2405`) never states. A `std::mutex` swap deadlocks.
- `:6415-6458` — WAV metadata rewritten in place with TagLib: no backup, no temp-and-rename, no dry run. `AbletonXmpWriter.cpp:104-112` does back up. `SampleManagerEngine.h:664` calls it "non-blocking"; the worker only relocates the block.
- `AbletonXmpWriter.cpp:157` — sidecar truncated in place, so a crash mid-write leaves a corrupt file that `:96-102` then refuses to touch, and `:107` overwrites the first backup on the next write.
- `PrecisionBrowser.cpp:675` — `ascending ? comparisonResult : !comparisonResult` returns true for equal elements in descending mode, violating the irreflexivity `std::sort` requires. The `filePath` tiebreak at `:614-671` is inverted too, so descending is not the reverse of ascending.
- `:1233` — `getSamples()` returns the vector by value including all 512-float embeddings; `runInferenceBatch` bumps the version per batch, so a 100k library copies hundreds of MB per second under `dbLock`. The FIFO path at `:4899-4906` only covers new rows.
- `:2423-2433` — `getSampleBpm` is a linear scan under `dbLock` on every audition click; `pathToIndex` (`:1105-1115`) exists for this.
- `:1536-1547` — `clearCache()` bulk `DELETE` on the message thread inside a modal dialog.
- `Licensing/LicenseManager.cpp:78` + `LicensePublicKey.h:3-13` — the shipped public key is the local mock's (private half in `licensing_server/`), so the repo holder can mint valid tokens; default endpoint `http://localhost:8420`; `verifyAndDecode:200-209` never checks `product_id` or `tier`; `:297,345,368` dereference a possibly-nil JSON object; `:124` reads an unbounded body. Display-only today (`PreferencesWindow.cpp:105-124`).
- `AppLogger.cpp:9-15` — process-wide `FileLogger` installed on first use, taking a `CriticalSection` and doing `write()`+`flush()`. Any JUCE internal log reachable from `processBlock` then performs locked file I/O on the audio thread.
- `AbletonTaxonomy.cpp:368-374, 420-431, 338-351` — `isFoleySourced()` runs only on the loop-variant path, so `Footstep`, filename-evidence vocals, and the `"Loop"` catch-all emit no `Foley` secondary tag, contradicting `AbletonTaxonomy.h:158-178`.
- `BetaDecisionPolicy.h:103-109` — `n.find("snap")` is a bare substring match, so Ableton's own `Snapshots` folder (plus "stops", "accord") is permanently capped at `Suggest`. `hasWord` at `AbletonTaxonomy.cpp:22-33` already does this correctly.
- `MlOverrideGate.h:25-34` — two unrelated comment blocks spliced mid-sentence, naming constants (`kPromotion*`) that do not exist. Actively misleading about the fusion-V2 gate.
- `AudioSimilarity.h:57` — `clamp01((cos+1)*0.5)` squashes the discriminative range into the top decile, so unrelated pairs read ~50% similar against seven aspects defaulting to 0.5. `AudioEvidence.h:62-74` never checks `item.second.valid`, the field `AudioSimilarity.h:70,106` gates on.
- `PluginProcessor.cpp:70-104` — when the playhead reports no position, `lastBeatPosition` is overwritten to `0`, and the "jumped backwards" branch then starts a queued audition on the next callback, defeating beat quantisation.
- `CorrectionLog.h:61-65` uses `~/Library/Application Support/SLO/` while `AppSettings.cpp:12-13` and `LicenseManager.cpp:49-54` use `SmartSampleManager` — three app-data roots for one product, and the correction log (the most valuable data collected) is the undiscoverable one.
- `PhaseCorrelationMeter.h` — 171 lines, no include or instantiation anywhere in `Source/`. Dead.
- `test_rt_deadline_stress_main.cpp:109-130` never sets a playhead, so `isDawPlaying` is always false and the audio-thread `startPreparedPlayback` path — the one in A1-b1 and A1-b2 — is never executed. The allocation counter measures the wrong path.

### What the core does well

- `processBlock` (`PluginProcessor.cpp:60-127`) is genuinely allocation- and I/O-free in steady state: playhead fetch, beat test, atomic exchange, transport render. The `BufferingAudioReader` + `TimeSliceThread` design (`:191-200`) is the correct architecture, with timeout 0 explained (yield silence, never stall), and the reader is opened on the message thread (`:141-143`) specifically to keep I/O out of the callback.
- The `pendingPlayback` handoff (`PluginProcessor.h:96-111`) is a proper single-owner exchange: the producer retires an unconsumed handoff, the audio thread peeks only to decide *whether* to start, and the destructor retires without touching the transport. That is subtle concurrency, and it is right — it is also the pattern A1-b2 should adopt.
- Fail-closed throughout: `runInferenceBatch:4820-4854` marks a batch retryable rather than caching a zero vector; `hasSafeEmbeddingBuffer:248-258` is the single shared predicate; `loadAndResampleWaveform:5918-5945` validates with dr_wav before handing to the tolerant JUCE reader; `MlOverrideGate.h:145-163` clears stale labels on OOD.
- Integer-overflow discipline where it counts: `runFullUMAP:5786-5830` bounds `nobs` before narrowing and keeps `ndim*nobs` / `nobs*2` in `size_t`, with exact thresholds in the comment.
- `AbletonXmpWriter.cpp:95-130` refuses to destroy a sidecar it cannot parse, backs up before modifying, and only touches its own `<rdf:li>`.
- `BetaDecisionPolicy.h` is one global 0.93 gate rather than per-class thresholds, with `:28-30` recording why per-class was measured and rejected (−12pp on unseen libraries), and `requiresApproval = true` carrying the inline note `// BETA: eligible != automatic`.
- `~SampleManagerEngine:449-478` joins every worker before tearing down members, with comments naming the reproduced use-after-free that motivated each join.
- `LabelFreeEvidencePacket::parse` is exemplary untrusted-input handling: 256 MB cap, row cap, absolute-path requirement, duplicate rejection, finiteness and range checks on every score. `SortFileSafety.h:45-62` uses `renamex_np(..., RENAME_EXCL)` precisely because JUCE's move/copy can delete the target.

---

## Phase A2 — ML pipeline

Test baseline: `358 passed in 23.74s`. Three files abort collection (C17).

### Blockers

**A2-b1 — `fusion_adversarial_accuracy` measures no adversarial condition.** `run_research_v3.py:861-883`:
```python
misleading_cue = "Kick" if true_lbl != "Kick" else "Snare"
if conf > 0.75: final_pred = pred_lbl
else:           final_pred = misleading_cue
```
`misleading_cue != true_lbl` in every branch, so the fallback is *guaranteed wrong* and `correct_fusion` increments iff `conf > 0.75 and argmax == true_lbl`. The metric reduces exactly to accuracy restricted to calibrated confidence > 0.75. The denominator is `len(y_clean)` — the whole clean set, not an adversarial slice — and `0.8828616352201258 == 1123/1272` exactly, the same 1272 as `dataset_size_clean`. `filename` is unpacked at line 861 and never used, so the stimulus its own comment at `:854-856` describes ("Filename says 'Kick' but audio is Snare") was never built. Published at `slo_classification_metrics_v1.json:7` and `SLO_CLASSIFICATION_ACCURACY_REPORT_V1.md:20`.

**A2-b2 — The primary benchmark artifact contradicts seven documents.** `REAL_CORPUS_CROSS_VENDOR_V2_REPORT.md:23,25` (generated) reports **77.9%** full-evidence, **17.5%** audio-only, macro-F1 **0.528 / 0.073**. Seven docs quote **71.5% / 39.0%** and **0.527 / 0.395** for the same 5,157 files. The artifact is internally consistent (4017/5157 = 77.89% with 1140 errors; evidence rows 2897×0.812 + 1684×0.985 + 576×0.012 = 4018). Both files landed in the same commit `f4a90d2c`. The gap is not cosmetic: the artifact shows DSP evidence winning only 576/5157 files (11.2%) at 1.2% accuracy, and Percussion — the largest class at 1251 files — at 0.0% audio-only. That is the opposite of the scorecard's "fusion lift real".

**A2-b3 — The scorecard misquotes the artifact it cites.** `SLO_EVAL_SCORECARD_2026-09-18.md:12` reads "81.2%/77.9% when filename/folder wins". In the cited table 81.2% is FILENAME only, the FOLDER row is **98.5%**, and 77.9% is the overall figure, not a per-source one.

### Major

- `run_benchmark.py:350-352` hardcodes `adv_total = 2` instead of `len(adv_results)`; reused at `:366`.
- Macro-F1 divides by `len(labels)` (full taxonomy) rather than classes present, so an unmeasured class contributes 0.0 and silently deflates the average: `run_benchmark.py:41`, `run_real_corpus_v2_benchmark.py:48`, `run_research_v3.py:294`, `eval_accuracy.py:62`.
- `run_benchmark.py:293-294` computes two accuracy figures in one report over different label sets.
- Silent `continue` skips shrink the evaluation denominator with no counter, warning, or non-zero exit: `run_benchmark.py:238-239, 306-308, 322-324, 331-333`; `run_real_corpus_v2_benchmark.py:106-108, 126-128`. The `(N matched)` printed at `:177, :699` is computed *after* the skip, so a fixture that stops matching quietly re-bases accuracy on a biased subset. The honest pattern already exists at `build_real_corpus_v2.py:483-491`.
- `run_research_v3.py:675-681` records an unmapped factorized prediction as `class_to_idx[0]`, biasing both the "Factorized 81.8%" figure and the flat-vs-factorized comparison.
- `GOLDEN_SET_V1_REPORT.md:16` is not reconstructible from its own N: 58.8% = 100/170 is self-consistent, but the precision column implies 140 predictions while a 100/170 confusion requires FP = 70. 30 predictions unaccounted for, and the matrix lists 5 of 7 zero-F1 classes.
- `corrections_store.py:85-91` `promote()` returns `conn.total_changes` (all writes on the connection), not rows promoted; with `AND status='pending'` a repeat call promotes 0 rows and returns a growing number.
- `run_real_corpus_v2_benchmark.py:186-188` describes a Wilson interval as "across 15 vendors" when `eval_contract.py:29-43` is an iid binomial over files, which are correlated within a vendor by construction.
- `run_real_corpus_v2_benchmark.py:139` defaults `{"n": 0, "recall": 0.0}`, printing `0.0%` for classes the same report says were not measured.
- `feature_cache.py:51-52` keys on `(size, mtime_ns)`, so an in-place edit preserving both is served from cache; the docstring correctly rejects path-only keying and then reintroduces a narrow version of it.
- `train_physics_inversion_gpu.py:345-346` hardcodes the remote training root and a conda interpreter path — a remote host path, which AGENTS.md §3 forbids.
- `run_real_corpus_v2_benchmark.py:162` writes the owner's absolute corpus path into a committed report.
- `test_f0_drums.py`, `test_f0_gain.py`, `test_batch_extract.py` contain zero `def test_` yet load a gitignored `.npz` and run `cross_val_score` at module scope, so `pytest` aborts with 3 collection errors on a clean clone (reproduced above).

### Verified clean

- The 12 `assert not (set(g[tr]) & set(g[te]))` guards are not vacuous: `g` is a real grouping key (`vendor`, `source_family`, `pack`), and `domain_generalization_eval.py:151-157` names the overlapping groups on failure.
- Fixtures do not leak ground truth into features — they key on paths and content ids.
- No path traversal in `label_tool.py`, `taxonomy_gap_review_tool.py`, `review_workspace_server.py`; all bind `127.0.0.1`.
- `run_research_v3.py:687-690` raises on incomplete OOF predictions, and temperature is calibrated on OOF logits (`:700-705`), not the in-sample fit.

### Numeric claim verification

| Claim | Verdict |
|-------|---------|
| 96.54% acc / 96.45% macro-F1, N=1272 | **Consistent.** 1228/1272; a unique consistent per-class confusion matrix exists at those counts |
| 62.9% full / 30.2% audio-only (V1) | **Consistent** with `REAL_CORPUS_CROSS_VENDOR_V1_REPORT.md:21-22` (390/620) |
| 88.29% "fusion-adversarial" | **Contradicted** — A2-b1 |
| 71.5% / 39.0% (V2) | **Contradicted** by the artifact — A2-b2 |

---

## Phase A3 — Build, test, packaging

- Test inventory says 31 executables in five docs. Actual: 41 `ssm_add_engine_test()` call sites (`CMakeLists.txt:794-1139`) + 18 `add_executable()` = 59 registered names, 55 unique. Nine different denominators exist across the corpus (31, 34, 37, 41, 46/47, 28, 55).
- `slo_test_results_v1.json:5` asserts `{"status": "FAIL", "diagnostic": "ld: 13044 duplicate symbols"}` while `SLO_BETA_BLOCKER_REGISTER_V2.md:11` marks B-012 CLOSED and `SLO_CURRENT_WORKING_STATE_AUDIT_V1.md:56` says it was re-verified. The object-library shape both describe is live at `CMakeLists.txt:706, 746-748, 768`. Any pipeline consuming the JSON inherits a P0 that two docs say is closed.
- `docs/BUILD_TREE_POLICY.md:8-12` lists three tiers; `CMakePresets.json` defines `ssm-base` (hidden), `ssm-dev`, `ssm-qualification`, `ssm-release-candidate`, and **`ssm-sanitize`** (Debug + ASan/UBSan), which is undocumented, making the policy's own "the supported tiers are" sentence false.
- The toolchain on this machine: `/usr/local/bin/cmake` is an **x86_64** binary and cannot configure on this arm64 host (`libxcrun.dylib … need 'x86_64'`). `/opt/homebrew/bin/cmake` 4.4.3 arm64 configures and builds cleanly. Worth recording, because any doc instructing `cmake --preset` without qualifying the binary will fail on Apple Silicon with a confusing dlopen error.
- `verify_no_auto_install.py` and `option(SSM_INSTALL_PLUGINS_AFTER_BUILD … OFF)` (`CMakeLists.txt:247-248`) are intact, with the re-regression guard at `:244-246`.

---

## Phase A4 — Docs vs code

### Blockers

**A4-b1 — Every git SHA in the release-truth docs is non-existent.** `SLO_CURRENT_WORKING_STATE_AUDIT_V1.md:9` (`be3e6310a…`), `SLO_SOURCE_ARCHITECTURE_MAP.md:10` (`dd60ddb3…`), and `SLO_PRODUCT_TRUTH_MANIFEST_V1.json:15-23` (five more, plus branch `engineering/slo-format-aware-scan-v1`) — `git cat-file -t` fails on all of them and the branch does not exist. The manifest's rollback instruction at `:109` is unexecutable, in the document designated as the release authority.

**A4-b2 — "WAV-only" asserted as critical in 8 documents.** Stale sites: `SLO_CURRENT_WORKING_STATE_AUDIT_V1.md:34,75`, `SLO_V1_WORKING_PRODUCT_DEFINITION.md:29`, `SLO_PRIVATE_BETA_READINESS_V2.md:30,38`, `SLO_SCAN_INDEX_PIPELINE_REPORT_V1.md:49`, `SLO_EVAL_SCORECARD_2026-09-18.md:10`, `SLO_EVAL_REPORT_2026-09-18.md:20`, `docs/ROADMAP_TO_BETA.md:30,73,156`. The cited `findChildFiles(..., "*.wav")` and its confirming comment do not exist. The docs also contradict each other: `SLO_BETA_EXECUTION_MASTER_PLAN_V1.md:73` says the scan is format-aware, while `SLO_PRODUCT_TRUTH_MANIFEST_V1.json:37` still lists `not_enabled_input_formats: ["AIFF","FLAC","MP3"]`. This made owner decision `docs/ROADMAP_TO_BETA.md:156` ("ship WAV-only documented vs close AIFF/FLAC decode") malformed — AIFF/FLAC is closed.

**A4-b3 — Headline accuracy wrong by 5.4× on one axis.** `docs/ROADMAP_TO_BETA.md:60,69,112,113` and `SLO_CURRENT_WORKING_STATE_AUDIT_V1.md:43`. See A2-b2. The artifact also instructs at `:26-27` that both figures be reported together every time; neither citing doc honours it. Compounding: `docs/ROADMAP_TO_BETA.md:18` invalidates its own table — every accuracy number from this lineage "must be regenerated" because the candidate's embedding validator rejected every inference (520 vs actual 512) — and §1.4 was not regenerated.

**A4-b4 — Build reported as both broken and fixed.** See A3.

### Major

- `SLO_LICENSE_MODEL_AUDIT_V1.md:8` and `SLO_SOURCE_ARCHITECTURE_MAP.md:49` say taxonomy version 2; `AbletonTaxonomy.h:45` is `kTaxonomyVersion = 5`. This is the cache-invalidation gate, so a v2 cache reclassifies on load. `kFeatureAnalysisVersion = 8` (`SampleManagerEngine.h:134`) is documented nowhere.
- Two safety audits state Sort Library is move-by-default (`SLO_FILE_DATA_SAFETY_AUDIT_V1.md:15`, `SLO_SECURITY_PRIVACY_AUDIT_V1.md:16`); `SampleManagerEngine.h:822` defaults `copyInsteadOfMove = true` and `PluginEditor.cpp:1839` passes `true` explicitly. Both audits are wrong in the direction that *understates* safety. `SLO_BETA_BLOCKER_REGISTER_V2.md:19` still titles B-011 "Sort Library is move-based" while marking it closed.
- `SLO_BETA_BLOCKER_REGISTER_V2.md:4,30` cites `NITE_DSP_SLO_MASTER_PLAN_V1.md` / `_V2.md` / `NITE_DSP_SLO_FINE_SUBCATEGORIZATION_V1.md` as the evidence trail for five of seven "closed with real evidence" rows. None exist in the repo. `receipts/` is gitignored (`products/slo/.gitignore:63-66`), so the register's load-bearing evidence is deliberately out of version control.
- Vocal Loop recall is reported as 77.4% (41/53, "Recovered", "suppression can be lifted") in `docs/BETA_CANDIDATE_MAIN_RECEIPT_2026-09-17.md:112,134` and as 4.5% (1/22, "effectively broken") in `docs/ROADMAP_TO_BETA.md:63,72` — both dated the same day. The source of truth `VOCAL_LOOP_CROSSVENDOR_V1_REPORT.md:31` says 4.5%. The 41-of-53 figure has no supporting report.
- `SLO_CURRENT_WORKING_STATE_AUDIT_V1.md:27,30,76` escalates `PRODUCT_NAME "Smart Sample Manager"` as a product-facing P0; `CMakeLists.txt:491` is `"SLO"`. The audit's *other* half stands — the bundle identity is unfixed — but both halves are reported as uniformly unfixed.
- Build and worktree paths are wrong across the corpus: `slo_test_results_v1.json:4` and `SLO_CURRENT_WORKING_STATE_AUDIT_V1.md:7` point at a pre-consolidation `<volume>/NITE_DSP/...` root that does not exist; the real root is `<volume>/Nite-DSP/monorepo`.
- Dirty-state claims are all stale: `SLO_CURRENT_WORKING_STATE_AUDIT_V1.md:10` ("1 tracked file modified … ~30 untracked") and `SLO_PRODUCT_TRUTH_MANIFEST_V1.json:22` (`dirty_entries: 49`) against a clean `git status --porcelain -- products/slo`.
- Every docs-side line citation for the mutation path is wrong. `SLO_CURRENT_WORKING_STATE_AUDIT_V1.md:61-62` places the sort at "~line 5055-5093" and `SLO_READ_ONLY_SAFETY_REPORT_V1.md:15` repeats "~line 5055". The file is 7,407 lines; `reorganizeSamples` is at `:7005`, `previewSortLibrary` at `:6820`. The safety *conclusion* is correct — no mutation site touches user audio during scan — but the citations are unusable for an auditor.
- `README.md` is 7 lines and points at `../../workspace/worktrees/slo/`, which does not exist. It states no build command, no formats, no licence position, no blocker status, and does not mention the format question the repo itself calls "the honesty gap" (`FORMAT_SUPPORT_CORRECTION.md:43-44`).
- `products/slo/nitedsp/.DS_Store` is tracked; that directory contains nothing else, and the manifest's `research_separation` claim about `nitedsp/backend` and `nitedsp/website` describes directories that are gone.
- Superseded clusters sit at the product root with no forwarding stub: `SLO_BETA_BLOCKER_REGISTER_V1/_V2.md`, `SLO_PRIVATE_BETA_READINESS_V1/_V2.md`, `docs/THURSDAY_*_FINAL_REPORT.md` ×3, `NITE_DSP_BUILD_OPTIMISATION_REPORT_V1[_1].md` ×2.
- `git log -- products/slo` returns 4 commits. `f4a90d2c` added 1,204 files in one commit; the three since touched three prompt docs, a CI workflow deletion, and the ONNX model. Every date asserted inside the 60-file corpus is unverifiable against git.

### Claims that hold

- **No network in scan/classify/sort.** No `WebInputStream` or `juce::URL` in `Source/` outside `Licensing/LicenseManager.cpp:109,113`. No telemetry symbol anywhere.
- **Licensing fails closed.** `LicenseManager.cpp:9-43` enforces HTTPS except literal loopback and rejects user-info `@` at `:27-28` to block lookalike-host credential smuggling; exercised at `test_licensing_main.cpp:44-50`.
- **Model hashes reproduce exactly.** `SLO_LICENSE_MODEL_AUDIT_V1.md:6-7` verified by `shasum -a 256`.
- **Read-only safety is genuinely proven.** `test_readonly_safety_qualification_main.cpp:3,15-16,90,115` does real libsodium `crypto_hash_sha256` over raw bytes before and after, writing a receipt.
- **RT evidence is honest.** `SLO_RT_THREADING_AUDIT_V1.md:13` states the original limitation before closing it, and restates scope limits at `:19-21`.
- **Formats are real:** `CMakeLists.txt:490` `FORMATS VST3 AU Standalone`.

---

## Secrets and hygiene

No credentials, API keys, or private keys. No non-loopback IPs. `.wav` files and `test_cpp_parity_standalone` are correctly gitignored. The 1.4 GB of model blobs (`.onnx`, `.npz`, `.npy`) are correctly ignored via `products/slo/.gitignore:38,49` — verified with `git check-ignore`.

**Personal data at volume.** 216 tracked files contain **168,749** occurrences of the owner's home path. Worst: `results_content_addressed_embedding_index_testing_v1.json` (14,297), `review_collections_breadth_candidate_v4_evidence.json` (8,093), `results_review_collections_testing_v1.json` (8,089), plus ~25 more over 500 hits. This publishes the owner's real name, commercial library vendors, and folder structure. `products/slo/.gitignore:36-49` shows the intent was the opposite — `label_manifest_*.json`, `verified_*.csv`, `receipts/`, `*.jsonl` are excluded as "user-specific" — but 158 `results_*.json` / `review_collections_*.json` files slipped past because the rule set matches extension, not content class.

**222 MB tracked** for a 55-test plugin, including three copies of the same 25 MB generated weight header (one production, two research).

**`slo_corrections.db` is not gitignored** — `.gitignore:25` covers `*.sqlite3`, nothing matches `*.db`. It holds `file_path` and `user_note`. Not committed today; nothing prevents it.

---

## Test and build state

```
python3 -m pytest (excl. 3 broken files)   358 passed in 23.74s
python3 -m pytest (full)                   3 collection errors, Interrupted
/opt/homebrew/bin/cmake --preset ssm-release-candidate   Configuring done (179.3s)
```

Full C++ build and the 55-target suite are pending; see `docs/SLO_BETA_READINESS_V1.md` for the gate verdict.
