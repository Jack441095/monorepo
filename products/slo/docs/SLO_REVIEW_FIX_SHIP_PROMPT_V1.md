# SLO — REVIEW, FIX, SHIP PROMPT (V1)

> What this file is: a self-contained prompt that drives review of SLO (SmartSampleManager), repair of the load-bearing defects, and a beta release gate.
>
> How to use it: open the workspace and instruct the agent: *"Execute `SLO_REVIEW_FIX_SHIP_PROMPT_V1.md` against `monorepo/products/slo`. Produce all deliverables."*
>
> Owner: NITE DSP (Jack) · Created: 2026-09-30
> Product root: `monorepo/products/slo`
> Stack: C++/JUCE plugin (VST3/AU/Standalone, arm64 macOS) · Python ML pipeline (PANNs/CLAP ONNX, taxonomy classification) · SQLite cache · libcrypto read-only receipts
> Repo: `monorepo` · python tests: `cd SmartSampleManager/tools/classification_benchmark && python3 -m pytest`

---

## 0. Role and mission

You are a release engineer + audio-DSP reviewer for **SLO**, a macOS sample-library manager plugin for Ableton Live. It classifies samples into an Ableton taxonomy from PANNs/CLAP embeddings plus filename and DSP evidence, then sorts and tags a library.

Answer in order: (A) what is broken, (B) repair it with tests, (C) can this go to a closed beta. Verdict: `READY` / `READY WITH CONDITIONS` / `NOT READY`, numbered blockers, every finding cited to file:line or a command and its output.

Ground rules:

- R1 — Read-only first. Complete Phase A before editing.
- R2 — Evidence or it does not exist. The 60-file report corpus at the product root is a set of leads, not proof. Re-verify every load-bearing claim against source in `SmartSampleManager/Source/`.
- R3 — Never echo secrets. Paths and values redacted to `***REDACTED***`. A committed secret or personal path is P0.
- R4 — The audio callback is sacred. Any allocation, lock, file I/O, or logging reachable from `processBlock` is a blocker.
- R5 — The local-only promise. No network in the scan, classify, or sort path. The licensing client is the sole exception and must stay fail-closed.
- R6 — Small diffs, AGENTS.md style. Why-comments with dates and measurements. No banners, no robot docstrings, no banned filler words.
- R7 — Receipts. Per phase: commands run, files read, what was skipped and why.

**Two facts about the code that a report does not know.** Before trusting anything, establish these yourself — several "critical gaps" in the corpus were already closed when the reports were written:

- The scan path is **format-aware**, not WAV-only. `SampleManagerEngine.cpp:2188` walks `"*"` and admits by `formatManager.findFormatForFileExtension()`; `Source/test_format_aware_scan_main.cpp` covers AIFF and FLAC.
- `PRODUCT_NAME` is `"SLO"` (`CMakeLists.txt:491`). The old bundle identity (`com.nitedsp.smartsamplemanager`, `PLUGIN_CODE AtSm`) is still unfixed.

---

## Phase A — Reusable full review (read-only)

Run verbatim on every future SLO review. Four surfaces.

A1 — **Plugin core** (`SmartSampleManager/Source/*.cpp|*.h`). Real-time safety in `processBlock`; transport and reader ownership; lock scope and ordering; integer narrowing; unbounded allocation; file-write atomicity and backup; `QuadTree`/`HNSW`/`UMAP` index robustness; taxonomy and fusion-gate correctness. Skip the 25 MB generated `AcousticClassifierWeights.h` body — read only its header comment.

A2 — **ML pipeline** (`SmartSampleManager/tools/classification_benchmark/*.py`, `scripts/`, `validation/`). Metric correctness: are the reported numbers measuring what their names claim? Denominator bugs, class-absent F1, silent `continue` that shrinks the denominator, train/test leakage, vacuous assertions, `try!`-style fatal-on-regression patterns. Then re-derive 2–3 headline claims from the raw artifacts and report any contradiction between prose and JSON.

A3 — **Build, test, packaging** (`CMakeLists.txt`, `CMakePresets.json`, `docs/BUILD_TREE_POLICY.md`, CI, `scripts/verify_no_auto_install.py`). Test inventory counted from `ssm_add_engine_test()` call sites plus `add_executable()` targets, not copied from a report. Preset coverage. Auto-install guard. Read-only qualification receipt (`test_readonly_safety_qualification_main.cpp` uses real libsodium SHA-256 — confirm it still does).

A4 — **Docs vs code.** Every numeric claim, version constant, git SHA, path, and thread/line citation in the ~60 root reports plus `docs/`. For each: does source agree? Record `OBSERVED` → `INFERRED` severity → `UNVERIFIED`.

Checklist for A:

- Audio thread: allocation, locks, file I/O, `juce::Logger`, `juce::File`.
- Unsynchronised shared state across audio / message / worker threads.
- Recursion without depth or progress guards.
- `size_t`→`int` narrowing on user-controlled sizes.
- Writes to user audio and to Ableton XMP sidecars: atomic? backed up? reversible?
- Report claims: git SHAs resolve? line numbers land? versions match the constants?
- Benchmark denominators: do they equal the number of rows actually evaluated?
- Secrets, remote hostnames, personal paths, and owner library contents in tracked files.

---

## Phase B — Repair the known blockers (from 2026-09-30 review)

Re-verify each in source, then repair with a regression test.

**B1 — Release-truth documents cite five git SHAs that do not exist.** `SLO_PRODUCT_TRUTH_MANIFEST_V1.json:15-23,109`, `SLO_CURRENT_WORKING_STATE_AUDIT_V1.md:9`, `SLO_SOURCE_ARCHITECTURE_MAP.md:10` all cite SHAs absent from the repo (`git cat-file` fails) and a branch that does not exist. The rollback instruction in the manifest is unexecutable. Fix: resolve each to a real commit or retract the claim, and add a test that every `rev` field in the truth manifest resolves. Do not invent a SHA to make it pass.

**B2 — Headline accuracy is wrong by 5.4× on one axis.** `docs/ROADMAP_TO_BETA.md:60,69,112,113` and `SLO_CURRENT_WORKING_STATE_AUDIT_V1.md:43` claim V2 is "71.5% full-evidence / 39.0% audio-only; macro-F1 0.527 / 0.395". The cited artifact `SmartSampleManager/docs/classification/REAL_CORPUS_CROSS_VENDOR_V2_REPORT.md:23-24` says 77.9% / 17.5%, macro-F1 0.528 / **0.073** — same 5,157 files. The artifact also instructs that both figures be reported together every time; neither doc honours that. Fix: correct every citation site to the artifact, and add a gate that fails when a quoted accuracy string does not appear in the report it cites. First determine *which side is current* — see Phase D item D2 — because that decides whether this is a doc fix or an accuracy regression.

**B3 — "WAV-only" asserted as a critical gap in 8 documents; the code is format-aware.** Stale sites: `SLO_CURRENT_WORKING_STATE_AUDIT_V1.md:34,75`, `SLO_V1_WORKING_PRODUCT_DEFINITION.md:29`, `SLO_PRIVATE_BETA_READINESS_V2.md:30,38`, `SLO_SCAN_INDEX_PIPELINE_REPORT_V1.md:49`, `SLO_EVAL_SCORECARD_2026-09-18.md:10`, `SLO_EVAL_REPORT_2026-09-18.md:20`, `docs/ROADMAP_TO_BETA.md:30,73,156`. The cited `findChildFiles(..., "*.wav")` and its confirming code comment do not exist. This made owner decision D-1 malformed. Fix: retract the claim everywhere, correct the roadmap decision to the real remaining gap (MP3/OGG need a runtime fixture each), and note that `FORMAT_SUPPORT_CORRECTION.md:45-46` is itself now stale — the drag/drop filter admits six extensions.

**B4 — `fusion_adversarial_accuracy` measures no adversarial condition.** `run_research_v3.py:861-883` picks a `misleading_cue` guaranteed to differ from the true label, so the metric reduces to accuracy restricted to confidence > 0.75; the `filename` is unpacked and never used, so the stimulus its own comment describes was never built. The number propagates to `slo_classification_metrics_v1.json:7` and a headline figure in `SLO_CLASSIFICATION_ACCURACY_REPORT_V1.md:20`. Fix: either build the adversarial set it claims to measure (filename says Kick, audio is Snare) and re-measure, or rename the metric to what it computes and correct the prose. Add a test that the metric responds to an actual adversarial input — a test that passes on the current code is the bug.

**B5 — 168,749 occurrences of the owner's home path across 216 tracked files.** Worst: `results_content_addressed_embedding_index_testing_v1.json` (14,297), `review_collections_breadth_candidate_v4_evidence.json` (8,093), `results_review_collections_testing_v1.json` (8,089). This publishes the owner's real name, commercial library vendors, and folder structure. `products/slo/.gitignore:36-49` already excludes `*.jsonl` as user-specific, but the same data arrived as `.json`. Fix: add ignore rules keyed to the content class, not the extension (`results_*/review_collections_*/definition_cards_*`), and add a `scripts/check_no_personal_paths.sh` gate that fails when the volume path or a username appears in a tracked file. Scrubbing history is a separate owner decision — report it, do not rewrite.

**B6 — Audio-thread resource teardown.** `PluginProcessor.cpp:203-211`: `startPreparedPlayback()` runs from `processBlock` via `:112-114`, and line 208 move-assigns `readerSource`, freeing the previous `AudioFormatReaderSource` and its `BufferingAudioReader` — a large `free()` and a file-descriptor close on a real-time thread. `PluginProcessor.h:67-68` claims "no allocation beyond the trivial pointer swap", which is wrong about the destructor. Fix: retire the old source on the message thread (or hand it to a queue) so the audio thread only publishes a pointer, and correct the comment. Add a test that the audio-thread handoff performs no free.

**B7 — `transportSource` / `readerSource` touched from three threads with no synchronisation.** Audio thread at `PluginProcessor.cpp:118-126,206-210`; message thread via `playSample` `:152` and `stopSample` `:218,221`. `stopSample()` reading `isPlaying()` and calling `stop()` while `processBlock` is inside `getNextAudioBlock()` races `positionSeconds` and the source's internal state; the `:152` handoff races the `:208` write, which is a use-after-free. Fix: single-owner command handoff, following the pattern `pendingPlayback` already uses (`PluginProcessor.h:96-111`) — one atomic queue, drained by one thread. Add a concurrent play/stop stress test.

**B8 — `QuadTree` infinite recursion on coincident points.** `QuadTree.h:27-57` has no depth cap and no minimum-bounds guard; `insertIntoChildren()` routes every non-contained point into the same child. `SampleManagerEngine.cpp:5062-5066` deliberately parks samples without a usable embedding at `(0,0)`, and `:5071-5072` does the same when there are no neighbours, so a library of 33+ pending or permanently-failed embeddings subdivides forever and overflows the stack on the message thread inside `rebuildSpatialIndexFull()`. Fix: bucket identical coordinates in one leaf, and stop subdividing when a node is smaller than one point. Test with 64 samples at the same coordinate.

**B9 — `reorganizeSamples()` holds `dbLock` across the entire sort.** `SampleManagerEngine.cpp:7007` takes the lock on the first line and releases it after thousands of `moveFileTo`/`copyFileTo` calls plus a per-row flushed journal write `:7181-7208`. The 60 Hz editor timer calls `getSamples()` at `PluginEditor.cpp:1233`, so the UI freezes for the length of the sort and cannot render the progress text it writes at `:1357-1361`. `canUndoSort()` and `getMostRecentSortJournal()` block identically. Fix: adopt the three-phase snapshot/publish discipline that `runFullUMAP()` already documents at `:5760-5764`. Test that `getSamples()` stays responsive during a sort of a large fixture.

**B10 — `slo_corrections.db` is not gitignored.** `products/slo/.gitignore:25` covers `*.sqlite3` but nothing matches `*.db`. `corrections_store.py:29` writes it beside the source, and the table holds `file_path` and `user_note` — licensed sample paths plus user annotations, which the module docstring at `:12-14` claims is safe to share. Not committed today, but nothing prevents it. Fix: ignore it, add the path gate from B5, and correct the docstring.

Repair rules: one blocker per commit, single-line message stating what changed and why. Each repair ships a regression test named for the behaviour it protects. Run `swift`/CMake tests and `python3 -m pytest` after each group.

---

## Phase C — Major hardening (same branch, after B is green)

- **C1** `SampleManagerEngine.cpp:6022-6023` — `size_t`→`int` narrowing on a resample buffer; upsampling a long field recording wraps negative and `copyLength < 0` walks before the buffer. Bound before narrowing.
- **C2** `:5937` — the whole file is decoded into a `std::vector<float>` to validate a WAV header, then decoded again. Read a bounded prefix; the check only needs "did the decoder produce frames". `channels` is an unvalidated `unsigned int` from the RIFF header.
- **C3** `:7262` — `undoLastSort()` takes `dbLock`, then calls `getMostRecentSortJournal()` which takes it again. Works only because `juce::CriticalSection` is a recursive mutex, which the locking contract never states. State the contract or restructure; a `std::mutex` swap would deadlock.
- **C4** `:6415-6458` — WAV metadata rewritten in place with TagLib, no backup, no temp-and-rename, no dry run. Compare `AbletonXmpWriter.cpp:104-112`, which does back up. `SampleManagerEngine.h:664` calls it "non-blocking"; the worker only moves the block off the message thread.
- **C5** `AbletonXmpWriter.cpp:157` — sidecar truncated in place, so a crash mid-write leaves a corrupt file that `:96-102` then refuses to touch; and `:107` overwrites the first backup on the next write.
- **C6** `PrecisionBrowser.cpp:675` — `ascending ? comparisonResult : !comparisonResult` returns true for equal elements in descending mode, breaking the irreflexivity `std::sort` requires. The `filePath` tiebreak at `:614-671` is inverted too, so descending is not the reverse of ascending.
- **C7** `:1233` — `getSamples()` returns the vector by value including all 512-float embeddings; `runInferenceBatch` bumps the version per batch, so a 100k library copies hundreds of MB per second under `dbLock`. The FIFO path at `:4899-4906` only covers new rows.
- **C8** `:2423-2433` — `getSampleBpm` is a linear scan under `dbLock` on every audition click; `pathToIndex` at `:1105-1115` already exists.
- **C9** `:1536-1547` — `clearCache()` runs a bulk `DELETE` on the message thread inside a modal dialog.
- **C10** `Licensing/LicenseManager.cpp:78` + `LicensePublicKey.h:3-13` — the shipped public key is the local mock's, so anyone with the repo can mint valid tokens; the default endpoint is `http://localhost:8420`; `verifyAndDecode:200-209` never checks `product_id` or `tier`; `:297,345,368` dereference a possibly-nil JSON object; `:124` reads an unbounded response body. `LicenseManager` is display-only today (`PreferencesWindow.cpp:105-124`), so fix before anything gates on it.
- **C11** `AppLogger.cpp:9-15` — a process-wide `FileLogger` installed on first use, which takes a `CriticalSection` and does `write()` + `flush()`. Once installed, any JUCE internal log reachable from `processBlock` performs locked file I/O on the audio thread. Message-thread-only.
- **C12** `AbletonTaxonomy.cpp:368-374,420-431,338-351` — `isFoleySourced()` is only called on the loop-variant path, so `Footstep`, every filename-evidence vocal, and the `"Loop"` catch-all emit no `Foley` secondary tag. `AbletonTaxonomy.h:158-178` promises it on all paths at 62% recall / 69% precision.
- **C13** `BetaDecisionPolicy.h:103-109` — `n.find("snap")` is a bare substring match, so **Ableton's own `Snapshots` folder**, plus "stops" and "accord", are permanently capped at `Suggest`. Token-boundary matching; the `hasWord` helper at `AbletonTaxonomy.cpp:22-33` already exists.
- **C14** `MlOverrideGate.h:25-34` — two unrelated comment blocks are spliced mid-sentence, and the text names constants (`kPromotion*`) that do not exist. Actively misleading about the fusion-V2 gate.
- **C15** `AudioSimilarity.h:57` — `clamp01((cos + 1) * 0.5)` squashes the discriminative range into the top decile, so unrelated pairs read as ~50% similar against seven aspects that default to 0.5. Use `max(0, cos)`. Also `AudioEvidence.h:62-74`: `isValid()` never checks `item.second.valid`, the field `AudioSimilarity.h:70,106` gates on.
- **C16** Python denominators: `run_benchmark.py:350-352` hardcodes `adv_total = 2`; macro-F1 divides by `len(labels)` not classes present (`run_benchmark.py:41`, `run_real_corpus_v2_benchmark.py:48`, `run_research_v3.py:294`, `eval_accuracy.py:62`); `:293-294` computes two accuracy figures over different label sets. Silent `continue` skips at `run_benchmark.py:238-239,306-308,322-324,331-333` shrink the denominator with no counter. `run_research_v3.py:675-681` records unmapped predictions as `class_to_idx[0]`, biasing the "Factorized 81.8%" figure.
- **C17** `test_f0_drums.py`, `test_f0_gain.py`, `test_batch_extract.py` contain zero `def test_` yet load a gitignored `.npz` and run `cross_val_score` at import, so `pytest` aborts with three collection errors on a clean clone. Add `conftest.py` scoping, or convert to real tests.
- **C18** `train_physics_inversion_gpu.py:345-346` hardcodes `cd <remote training root>` and a hardcoded conda interpreter path. AGENTS.md §3 forbids committing remote host paths.
- **C19** `run_real_corpus_v2_benchmark.py:162` writes a personal absolute path into a committed report; `:186-188` describes a Wilson interval as vendor-clustered when `eval_contract.py:29-43` is an iid binomial over correlated files; `corrections_store.py:85-91` returns `conn.total_changes` not rows promoted; `feature_cache.py:51-52` keys on `(size, mtime_ns)`, so an in-place edit preserving both is served stale.
- **C20** Docs: test inventory says 31 executables, there are 55 (`ssm_add_engine_test()` × 41 plus `add_executable()` × 18) and nine competing denominators exist. `kTaxonomyVersion` is 5, two audits assert 2 — and it is the cache-invalidation gate. `slo_test_results_v1.json` asserts a `FAIL` build that `SLO_BETA_BLOCKER_REGISTER_V2.md:11` says is closed. `SLO_BETA_BLOCKER_REGISTER_V2.md:4` cites master-plan files that do not exist. `docs/BUILD_TREE_POLICY.md` omits the `ssm-sanitize` ASan/UBSan preset. `README.md` points at a worktree path that does not exist. Publish `docs/INDEX.md` with status, date, and supersedes per report.

---

## Phase D — Beta gate

**D1** — Decide the two owner questions before touching the accuracy numbers, because they determine whether B2 is a documentation fix or a regression:
- *Which V2 run is current, the artifact's 77.9%/17.5% or the docs' 71.5%/39.0%?* Re-run the benchmark if the models are available locally. If not, say so and mark the figures `UNVERIFIED` rather than picking one.
- *Scrub the personal paths from git history, or leave them and accept the exposure?* Present the blast radius either way.

**D2** — Versions agree: `kTaxonomyVersion` (5), `kFeatureAnalysisVersion` (8), `kEmbeddingModelVersion`, `kStateSchemaVersion`, `PRODUCT_NAME` (`SLO`), bundle identity (`com.nitedsp.smartsamplemanager`, `AtSm` — still the old identity, and an open owner decision), and the format list in every doc that states one.

**D3** — Clean Release build from HEAD, with the `ssm_qual_full` and `ssm-qualification` presets green. Resolve the split: either `slo_test_results_v1.json` is current and B-012 is open, or the JSON is stale. Annotate whichever is wrong with the date its verdict was true, so a machine-readable P0 stops re-raising every cycle.

**D4** — Test inventory recounted from `CMakeLists.txt`, all 55 targets enumerated, one denominator used everywhere, and the nine existing numbers reconciled or explicitly retired.

**D5** — No network in scan/classify/sort, verified in source and in the built binary. Licensing client fail-closed and its public key not the mock's before it gates anything.

**D6** — Read-only safety re-proven: real libsodium SHA-256 over raw bytes, before and after, receipt written. Sort defaults to copy (`SampleManagerEngine.h:822`) — correct the two audits that say move.

**D7** — Secrets and personal data clean: no credentials, no remote hostnames, no owner library paths in tracked files. `slo_corrections.db` ignored. History exposure reported.

**D8** — Reports reconciled: every git SHA resolves, every line citation lands, every version constant matches, no superseded report at the product root without a supersede pointer, and `docs/INDEX.md` published.

**D9** — Refresh `SLO_BETA_BLOCKER_REGISTER_V2.md` and `docs/ROADMAP_TO_BETA.md` with dated evidence. Redo the owner decisions D-1 (formats) and the identity decision against what the code actually does.

Hard stop: any P0 → stop and deliver the blocker report. No beta until every P0 shows `VERIFIED FIXED`.

---

## Deliverables (new files only, outside `Source/`)

1. `docs/SLO_REVIEW_V1.md` — Phase A per-file findings with citations.
2. Phase B + C repairs committed on a feature branch, each with a regression test.
3. `docs/SLO_BETA_READINESS_V1.md` — Phase D per-phase findings and the verdict.
4. `docs/SLO_BETA_BLOCKERS_V1.md` — prioritized P0/P1 list with exact fix steps.
5. Updated `SLO_BETA_BLOCKER_REGISTER_V2.md` and `docs/ROADMAP_TO_BETA.md`; published `docs/INDEX.md`.
6. Sign-off checklist (ticked or crossed) plus a per-phase receipt.
