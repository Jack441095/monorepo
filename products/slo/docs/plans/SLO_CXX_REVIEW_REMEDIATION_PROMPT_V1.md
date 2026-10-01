# SLO C++ REVIEW REMEDIATION — AGENT PROMPT (V1)

> **What this is:** a self-contained prompt to drive an AI coding agent through the fix list from a full read-only review of the SLO production C++ (`SmartSampleManager/Source`). Every finding below was verified against the vendored JUCE 8.0.2 in `../_cache/fetchcontent` and, where numeric, by compiling the claim. It is a *remediation* brief, not another audit — do not re-audit, fix.
>
> **How to use it:** open the workspace root (`/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP`) and instruct the agent: *"Execute `SLO_CXX_REVIEW_REMEDIATION_PROMPT_V1.md` in full. Phase 0 is read-only. Phase 1+ only on branch `slo/review-fix-v1`. Phase 4 needs owner sign-off before it starts. Produce every deliverable in §7."*
>
> **Owner:** NITE DSP (Jack) · **Created:** 2026-10-01
> **Product root:** `monorepo/products/slo/SmartSampleManager/` (C++/JUCE source of truth)
> **Docs/receipts root:** `monorepo/products/slo/` (`SLO_*.md`, `validation/`)
> **Stack (verify, don't assume):** JUCE 8.0.2 + CMake; PANNs CNN10 ONNX 512-D via ONNX Runtime; 16-class linear head + nearest-centroid OOD gate; SQLite WAL cache; HNSW + UMAP; TagLib 2.3.1; dr_wav; TagLib-side XMP/Ableton sidecars; libsodium for content fingerprints.

---

## 0. Role & mission

You are a **principal systems engineer with an audio-real-time specialism**. Your mission, in order:

1. **BASELINE** — get the 43 substantive test binaries actually running and green. Right now they cannot be run by any single command (§1 R1).
2. **STOP THE BLEEDING** — fix the four P0s that can destroy or strand a user's audio. Each needs a failing-then-passing test.
3. **FIX THE REAL BUGS** — the P1 list, in the order given.
4. **DELETE** — remove the dead code the review found, so the next reviewer isn't misled by it.
5. **REPORT** — what changed, what is proven, what you refused to do and why.

**Success criteria (all must hold):**
- Every fix ships with a test that **failed before it and passes after**. No exceptions, no "the existing suite covers it".
- Every P0 and P1 in §3–§4 is either fixed and tested, or explicitly deferred with a written reason in §7.
- `ctest` runs the suite and reports it. This is the gate for everything in Phase 1.
- `main` untouched. All work on `slo/review-fix-v1`. Nothing pushed.
- No new network calls, telemetry, or cloud inference. No audio or filenames leave the machine.
- No secrets, hostnames, or personal paths in the diff.

---

## 1. Ground rules (non-negotiable)

- **R1 — Make the tests runnable first.** `enable_testing()` and `add_test()` appear **zero times** in `SmartSampleManager/CMakeLists.txt`, and the six `ssm_qual_*` groups are `add_custom_target(... DEPENDS <executables>)` (`:1251-1278`) — they *build* the binaries, they never *run* them. Do not touch a source file until `ctest` executes the 43 substantive binaries and you have a green baseline recorded in §7. Baseline first, or every later claim is unfalsifiable.
- **R2 — One logical change → its test → full `ctest` → commit.** Never batch unrelated fixes. Commit message = one plain line, what changed and why it matters. **No AI attribution trailers, ever.**
- **R3 — A failing test precedes every fix.** For each finding, write the test that reproduces the defect, watch it fail, then fix, then watch it pass. If you cannot make it fail, you have not found the bug — stop and re-read the finding.
- **R4 — Do not re-audit.** The findings are verified. Spend your budget writing tests and fixing. If you find something new and serious, log it in §7 under "new findings" — do not start fixing it unprompted.
- **R5 — Data safety outranks elegance.** Sort Library moves and renames the user's irreplaceable audio. When a fix trades safety for simplicity, take the safe option and say so.
- **R6 — Comment style per `AGENTS.md`.** Explain *why*, the trade-off, or the gotcha. Record the edge cases that bit us. No banner comments, no robot docstrings, no "robust/seamless/comprehensive/leverage/ensure that". State exact numbers and units.
- **R7 — Cost discipline.** Never load wholesale: `Source/AcousticClassifierWeights.h` (25 MB generated data blob — read its declaration block only), `Source/parity_references.json` (572 KB), `Source/AcousticClassifierCentroids.h` (108 KB), `*.onnx`, `*.wav`, `*.npz`, `*.pt`, `_cache/`, `build*/`, `.venv/`, `__pycache__/`. Use `ls`, `wc`, `head`, `jq`, targeted greps.
- **R8 — Approval gate — these go to PROPOSALS (§6), not execution:**
  - Changing the sort journal format (CSV → JSONL). It invalidates every existing `.slo_sort_journal_*.csv` on user disks.
  - The `PluginProcessor` audio-thread ownership change (P1-10). Load-bearing; see §6.
  - Any threshold change (`PhysicalAcoustics.h`, `AbletonTaxonomy.cpp`, `MlOverrideGate.h`, per-class OOD). Needs a holdout measurement, not a guess.
  - Bumping `AbletonTaxonomy::kTaxonomyVersion` or any cache/schema version.
  - Deleting >100 lines in one commit, or anything touching `Source/AcousticClassifierWeights.h` / `AcousticClassifierCentroids.h` (both `DO NOT EDIT MANUALLY` — regenerated by script).
- **R9 — Revert on red.** If a fix breaks tests and the cause isn't obvious in a few attempts, revert, log it as a failed experiment, and move to the next finding. Failed experiments are legitimate output.
- **R10 — Never touch a running Ableton Live session, and never commit user audio, stems, or session data.**

---

## 2. Phase 0 — Baseline (READ-ONLY)

Confirm each claim before acting on it. If reality disagrees with this brief, reality wins — report the disagreement and re-plan.

1. Configure a build: `cmake --preset ssm-dev` in `SmartSampleManager/`. Record configure time and whether the arch preflight passes (it should — `CMAKE_OSX_ARCHITECTURES` is pinned `arm64`).
2. Build one test binary and run it by hand. Record how long the full 43-binary build takes.
3. Verify `ctest` really is absent: `grep -c "enable_testing\|add_test(" CMakeLists.txt` → expect `0`.
4. Record the current `deadline_misses` / `callback_max_ms` from `test_rt_deadline_stress_main` — you need the before-number for P0-3.
5. **Write down the working directory each test binary is launched from.** Three of them resolve cache dirs relative to `getCurrentWorkingDirectory()` (`test_kick_length_main.cpp:31`, `test_readonly_safety_qualification_main.cpp:59`, `test_rt_deadline_stress_main.cpp:75`), so their behaviour depends on where `ctest` happens to run them from. This matters the moment you register them.

**Deliverable:** a baseline table (binary | runs? | pass/fail | seconds) in §7.

---

## 3. Phase 1 — The four P0s (data loss + audio-thread stall)

> Order is deliberate: P0-1 is the only finding in this document that can take a recording.

### P0-1 — Undo destroys any file the user put back at the original path
`Source/SampleManagerEngine.cpp:7388` (move branch), `:7413` (copy branch)

```cpp
if (destFile.existsAsFile()) {
    sourceFile.getParentDirectory().createDirectory();
    if (destFile.moveFileTo(sourceFile)) {      // <-- no sourceFile.existsAsFile() check
```

JUCE 8.0.2, `_cache/fetchcontent/juce-src/modules/juce_core/files/juce_File.cpp:300`:

```cpp
bool File::moveFileTo (const File& newFile) const {
    ...
    if (! newFile.deleteFile())   return false;   // destination unlinked FIRST
    return moveInternal (newFile);
}
```

**Why it matters:** after the sort, the user re-sorts, a backup agent restores, they copy a take back, or a second SLO instance touches the same library — any of those puts a live file at `sourceFile`. Undo `unlink`s it and reports success. This is a normal state, not a race.

**Test to write first:** in `test_sort_preview_and_undo_main.cpp` — sort one file in move mode, then write a *different* file at the original path, then undo. Assert the pre-existing file is **still there, byte-identical**, and that the undo reports a failure for that row rather than success.

**Fix:** refuse to touch an occupied destination. `if (sourceFile.existsAsFile()) { result.failedCount++; continue; }` before the move, and for copy mode compare against a recorded pre-copy size/hash before deleting.

### P0-2 — `SortFileSafety.h` is dead code, and three docs cite it as the safety net
Zero references outside the file itself. The only mentions in the whole product are Markdown:
- `docs/SLO_REVIEW_V1.md:63` — *"`SortFileSafety.h:45-62` uses `renamex_np(..., RENAME_EXCL)` precisely because JUCE's move/copy can delete the target"*
- `docs/plans/SLO_CLASSIFICATION_OPTIMIZATION_PROMPT_V1.md:42`
- `docs/plans/SLO_CLASSIFICATION_QUICKCHECK_PROMPT_V1.md:28`

The real path at `:7242`/`:7247` uses `copyFileTo`/`moveFileTo`, and the only protection is `chooseNonDestructiveDestination` (`:163`) — a check-then-act against a non-atomic delete-then-move. The gap-closing code was written and commented and never called.

**This is a fork in the road. Pick one and commit to it:**
- **(a) Wire it up.** Call `sortSafety::moveExclusive` / `copyExclusive` at `:7247`, `:7388`, `:7413` and in `AbletonXmpWriter.cpp:107`. `moveExclusive` uses `renamex_np(..., RENAME_EXCL)` — one atomic syscall that fails if the destination exists, which closes both the P0-1 window and the check-then-act gap at once. This is the preferred option: the code already exists and is correct.
- **(b) Delete it** and correct the three docs. Only if you conclude exclusive-move is unnecessary. You will not — see (a).

Under (a), `SortFileSafety.h` becomes reachable and the docs become true. Add it to `R6`'s safety-critical list in your final report.

### P0-3 — `AudioTransportSource::stop()` on the audio thread costs up to 1 s
`Source/PluginProcessor.cpp:140` and `:240`

Vendored JUCE 8.0.2, `juce_AudioTransportSource.cpp:133`:

```cpp
void AudioTransportSource::stop() {
    if (playing) {
        playing = false;
        int n = 500;
        while (--n >= 0 && ! stopped) Thread::sleep (2);   // 500 x 2 ms = 1000 ms
```

`stopped` is cleared only inside `getNextAudioBlock()`. When `stop()` is called *from* `processBlock`, the only thread that could clear it is the one blocked in the loop, so it always runs all 500 iterations. Every STOP during audition stalls the audio thread ~1 s — and since `:139` already gain-ramped the buffer to zero, it's a 1 s hole of silence. `:240` repeats it on every PLAY that replaces a still-sounding sample.

**Why the existing RT test misses it:** `test_rt_deadline_stress_main.cpp:112` re-fires `playSample` every 100 iterations against `test_kick.wav`, which is exactly 1.000 s (44100 frames = 86 blocks), so the transport has always finished by the time it would matter — and the test never calls `stopSample()` at all.

**Test to write first:** change the stress fixture to `real_kick_a.wav` (2.000 s) or add one `stopSample()` mid-playback. Watch `deadline_misses` jump and `callback_max_ms` approach 1000.

**Fix (do both halves):**
- Delete `:240` entirely. The `transportSource.setSource(nullptr)` on the very next line already clears `playing` inside JUCE's own `ScopedLock (callbackLock)` with no spin. The 15-line comment above it arguing the `stop()` is needed is wrong — verify that and delete the comment too.
- `:140` needs a real handoff: the audio thread cannot non-blockingly clear `playing`, so let the message thread perform the halt and the audio thread apply only the gain ramp. Design this with care; it is the highest-risk change in the document and R8 applies.

### P0-4 — The sort journal is neither durable nor crash-safe
Three defects, all in `SampleManagerEngine.cpp`:

1. **`:213-215`** — `appendSortJournalRow` always `return true` and discards the write result. `rename()` needs only a directory entry, so on ENOSPC the `moveFileTo` at `:7247` **succeeds** while the `PLANNED`/`COMMITTED` rows vanish. Files moved, undo history gone, `undoLastSort()` reports *"No committed actions found in journal."* The audio is then only recoverable by hand.
2. **`:7362`** — `undoLastSort` consumes only `COMMITTED`. Kill the DAW between `:7247` and `:7252` and that file is moved with only a `PLANNED` row, which holds the full source→destination mapping but is refused. Accept `PLANNED` rows where `!source.existsAsFile() && dest.existsAsFile()` — that is provably the "the move landed, the log didn't" state and is safe to reverse.
3. **`:195-198`** — `journalCsvField` escapes `"` but not newlines, and both the writer and `parseJournalCsvLine` split on `\n`. A POSIX filename may legally contain `",\n`, so a hostile sample pack can forge a `COMMITTED` row and make Undo `moveFileTo` over a path of its choosing. The threat model is already stated at `:6527` ("untrusted input ... travels with a file rather than being typed in-app").

**Fix:** (1) return the real write status and refuse to claim a sort is undoable when the journal is degraded. (2) accept the `PLANNED`-only state. (3) is an **R8 approval item** — a format change invalidates every journal on user disks. The in-place option (reject `\r`/`\n`/`"` in `journalCsvField`) needs no format change and closes the injection; propose the JSONL migration separately, since `CorrectionLog.h` already does it correctly.

**Test to write first:** a journal containing a filename with an embedded newline, parsed back, must yield exactly one row.

---

## 4. Phase 2 — P1 fixes, in this order

**Group A — RT and host lifecycle** (do these together; they touch the same file)
- **P1-8** `retiredWriteIndex` (`PluginProcessor.h:137`) is only ever `fetch_add`ed and `load`ed — never reset, never wrapped, no modulo. Slot ≥ 8 hits the overflow branch *for the life of the plugin instance*, leaking a reader (fd + 32k buffer + time-slice registration) **and** doing a `juce::String` allocation plus a blocking `write(2)` to stderr from inside `processBlock` — which `AppLogger.cpp:13-19` documents as forbidden. Fix: `% kRetiredReaderSlots` on the fetch_add; drain all 8 slots unconditionally with `exchange(nullptr)`. Then delete the overflow branch, which becomes unreachable. Correct the header comment at `:123-134` — it describes a burst limit; the code was a lifetime limit.
- **P1-9** `PendingPlayback` (`PluginProcessor.h:106`) is a plain aggregate holding a raw `AudioFormatReaderSource*`. `:195`, `:295` and `:32` all `delete` the struct and nothing else, so the reader's `~BufferingAudioReader` never runs and it is never unregistered from the `TimeSliceThread`. The comment at `:191-195` ("deleting it here returns the file handle") is factually wrong — correct it. One click reaches it: PLAY then STOP inside the same beat. Fix: `std::unique_ptr` member, `std::move` at the consumer (`:126`).
- **P1-10** `startPreparedPlayback` (`:236`, `:254`) allocates ~5× and takes 2 locks per audition **on the audio thread**: `setSource` with a resampling rate builds a `ResamplingAudioSource`, then `prepareToPlay` does `buffer.setSize` + 3 `calloc` + `flushBuffers` (a `CriticalSection`), then `ScopedLock callbackLock`. The comment at `:236` claims realtime safety. **R8 approval item** — propose moving `stop`/`setSource`/`start` to the message thread; JUCE's `callbackLock` already serialises it, and the retire ring (P1-8) already solves the `readerSource` lifetime race it was written to work around.
- **P1-11** Quantised audition never fires on a host reporting `isPlaying` with no PPQ. `currentBeat` stays `0.0`, `nextBoundary` pins at `1.0`, neither trigger at `:116` can be true — the pending handoff holds an open fd indefinitely and the user hears nothing. `isDawPlaying` is also never cleared when `getPlayHead()` returns null. Add a test with a `nullopt` playhead.
- **P1-12** `WaveformPreviewComponent.h:25` — `loadFile` has no same-file early-out, so the 60 Hz `timerCallback` (`PluginEditor.cpp:1271`) re-runs a full synchronous `detectTransients` decode whenever any of ~14 fields differ, including `embeddingStatus` and `tagConfidence`, which churn during a scan. One line: `if (file == currentFile) return;`
- **P1-13** `PluginProcessor.cpp:346` reads `namingStyleId` with no range check. A corrupt chunk yields `0`, which falls through every branch of `getFormattedFilename` to `return originalName` **while still relocating files into category folders**. `juce::jlimit(1, 9, …)`.
- **P1-14** `editorSearchText` is uncapped in the project chunk (`:322`/`:345`, written on every keystroke at `PluginEditor.cpp:121`). It is per-app UI state; move it to `AppSettings` and it stops inflating the DAW project on every save.
- **P1-15** `PluginEditor.cpp:1228` — the "FIFO fast path" is defeated by its own `samplesVersion` check, which bumps on every inference batch (`SampleManagerEngine.cpp:4939`), so `getSamples()` deep-copies every `SampleItem` **including its 512-float embedding** under `dbLock` ~6-7×/sec during a scan. Bump the version only for changes the FIFO cannot express.

**Group B — file-move safety**
- **P1-16** `sanitizePathComponent` (`:6534`) strips `/`, `\`, `:` and leading dots but **not `~`**. JUCE's `isAbsolutePath` (`juce_File.cpp:420`) returns true for a leading `~`, and `getChildFile` (`:432`) then discards the parent entirely: `return File (String (r));`. `parseAbsolutePath` calls `getpwnam()` and dereferences the NULL. This fires **inside the `File` constructor**, before the `isInsideDirectory` guard at `:7222` can run. Reachable from a WAV whose TXXX `InstrumentType` is `~foo` (read at `:6402`), or with no malice, a file named `~kick.wav` (paths at `:6914`, `:7188`). Also add a length bound (`File::createLegalFileName` truncates to 128 — a 300-byte tag currently fails the whole library with `ENAMETOOLONG`) and strip control characters, which also closes P0-4(3). **Add `~` cases to `test_path_traversal_main.cpp`.**
- **P1-17** `getCommonRootDirectory` (`:6748-6790`) takes the longest common *character* prefix, then walks up while it isn't a directory. Add `/Users/me/Music/Samples`, drop `/Users/me/Desktop/vox.wav` → prefix is `/Users/me/`, a directory, so the walk never runs and **the sort root is `/Users/me`** — every file lands outside both scanned roots. It only fails closed because `/` isn't writable. Carry the roots the user actually added via `addPathToQueue`; refuse to sort when there is more than one.
- **P1-18** `isInsideDirectory` (`:187`) is a pure string prefix test, and the sort destination directory is never checked for being a symlink. If `<root>/Kick` → `~/Desktop`, files leave the library. Symlinked *files* (`:2191`) and scan roots (`:2174`) are already rejected; only the destination is unguarded. Separately, `findChildFiles` at `:2192` recurses into symlinked *directories* (JUCE default is `noCycles`) and `f.isSymbolicLink()` only tests the last component.
- **P1-19** `lastSortJournalPath` (`SampleManagerEngine.h:1093`) is a plain `std::string` written from the sort worker without `dbLock` at `:7078` and read under it at `:7293` and from the message thread. Take the lock, or make it atomic.
- **P1-20** `getMostRecentSortJournal()` (`:7301`) recomputes the root from post-sort paths, which are one level deeper after a single-category sort, and searches non-recursively — so the journal is invisible and Undo is silently unavailable after closing the DAW. Store the journal path outside the library, or walk parents. `:7310`'s `modTime > bestTime` is strict, so two sorts in the same second resolve arbitrarily.
- **P1-21** `AbletonXmpWriter.cpp:107` uses `copyFileTo` (delete-then-copy) for the `.bak`, so after two operations the backup holds *SLO's own output*, not the user's sidecar. `:157` writes in place, so a crash mid-write leaves a corrupt sidecar. Timestamp the backups; write to a temp file and `rename()` into place.

**Group C — classifier correctness**
- **P1-22** `SampleManagerEngine.cpp:409` and `:415` — `addUniqueSecondaryTag(bassTimbre.label)` with no confidence floor. `BassTimbreClassifier::classify` returns a label whenever a centroid is merely *nearest*; an embedding at cosine 0.05 to both 808 and Reese is tagged `"808"` and **persisted**. **Threshold changes are an R8 approval item**: the 92.9% in the header is accuracy, not a separation point. First, compute the holdout similarity distribution and put the number in the report; then propose a threshold derived from it.
- **P1-23** `MlOverrideGate::Decision` (`:71-80`) cannot carry `isOod`. For OOD + `FILENAME`/`EMBEDDED_METADATA` evidence the abstention is dropped and the stale label kept — and `ClassificationPresentation::isMlOod` is the only gate the UI reads, so it is unrecoverable downstream. Either add the field, or — if the current behaviour is intended — say so in a comment next to `tagSource` so the next reader doesn't "fix" it. The parity test at `:126-131` pins it as intended, so decide deliberately.
- **P1-24** `PhysicalAcoustics.h:95`/`:419` — `harmonicToNoiseRatio` is `min(1, Σ normalised peak magnitudes)`, a saturating peak-count proxy, written to the cache as if it were a ratio. Either divide by a real noise-floor estimate or rename it. `:206` returns a magic `10.0f` for "no even harmonics", so zero even-harmonic energy gets badge **Closed Pipe (Cylindrical)** — use a named sentinel or `std::optional`.
- **P1-25** `PhysicalAcoustics.h:455` — `decayTimeSeconds` defaults to `0.0f` when unmeasurable, and `0.0 < 0.8` reads as impulsive → `HardMetal` → "Sharp Metal Impact". A missing measurement and a measured 0.5 ms metal click are indistinguishable, and `physicalClass` is persisted and user-filterable. Thread an explicit "decay measured" flag.
- **P1-26** `AudioSimilarity.h:42` — verified by compilation: `clamp01(NaN) == 1.0f`, so a NaN measurement scores as a *perfect* match and pulls `overall` up. `Record::isValid()` range-checks `Claim::confidence` but never `PhysicalMeasurement::value`. Latent only because `AudioSimilarity` has no production caller (see Phase 3). Fix alongside the deletion so it doesn't become a trap.
- **P1-27** The OOD gate — the actual production decision boundary — is unasserted. `TestAcousticClassifierParity.cpp:364` skips the class check whenever the gate says OOD, and 4 of 50 fixture cases come out OOD (one at cos 0.7513 vs threshold 0.7515). If the gate regressed to always-OOD, all 50 class assertions vanish and the test still passes. Block 2 (`:62-70`) never calls `AcousticClassifier` at all — it is arithmetic on two header constants, and its comment claims it "proves the gate is class-conditional". `:36-40` calls `V4H_CHECK(clapIdx >= 0, …)`, which records and continues, then indexes `centroids[clapIdx]` — a `-1` read on a routine model regeneration. Add `expected_is_ood` to the generator and assert unconditionally; route a real embedding through `classify()` in block 2.

**Group D — test suite integrity** (must land before or with Phase 0's exit)
- **P1-28** `test_search_lexicon_main.cpp` — 13 bare `assert()`s. `NDEBUG=1` is set for non-Debug (`CMakeLists.txt:436`) and **both qualification presets are `CMAKE_BUILD_TYPE: Release`** (`CMakePresets.json:32,43`). It prints "passed" and returns 0 regardless of `SearchLexicon.h`. Convert to the `failures`-counter pattern the other 40 files use.
- **P1-29** `test_production_cache_guard_main.cpp` is not in `CMakeLists.txt` — the *only* test of the `openCacheDb()` `std::abort()` guard is never compiled. Add it via `ssm_add_engine_test` and append to `SSM_TEST_TARGETS`.
- **P1-30** `test_licensing_main.cpp:125-155` tampers with and then deletes the **real** `~/Library/Application Support/SmartSampleManager/license.json`. `LicenseManager::appDataDir()` (`:49-53`) hardcodes `userApplicationDataDirectory` with **no test override hook** — mirror `setCacheDbDirectoryOverrideForTesting` and point it at a `juce::Uuid()` temp dir. This is the only test in `ssm_qual_ui` needing a live `uvicorn` server, so it is also the one most likely to be skipped and the one most likely to do damage.
- **P1-31** `TestCachedReclassification.cpp` prints `processedCount`, asserts nothing, `return 0` — yet it is a `DEPENDS` of `ssm_qual_fast_regression`. `test_map_clusters_main.cpp:33` likewise prints SUCCESS on any `computeMapClusters()` result. Assert the counts.
- **P1-32** Tests that assert the code against itself: `test_cache_version_enforcement_main.cpp:260` computes `expectedMl` by calling `AcousticClassifier::classify` — the function under test. `test_smart_collections_main.cpp:61,73` builds its query from the engine's own `physicalClass` output. `test_timbre_refinement_main.cpp` and `test_find_similar_weighted_main.cpp` only check "returned something", so they pass if the feature is ignored entirely — run the same query with two opposite weight values and assert the ranking inverts. `test_bass_timbre_main.cpp`/`test_hihat_type_main.cpp` compare a centroid to itself and assert a margin implied by the label check beside it.
- **P1-33** `test_kick_length_main.cpp:31`, `test_readonly_safety_qualification_main.cpp:59`, `test_rt_deadline_stress_main.cpp:75` resolve cache dirs from `getCurrentWorkingDirectory()`. Move them to `ScopedIsolatedCacheDb` so `ctest` can't change their meaning.

---

## 5. Phase 3 — Delete what has no caller

Verify each with a repo-wide grep before deleting, and record the count in the report. Per `AGENTS.md` ("Keep abstractions lean"), these are ~760 lines of shipped, compiled, **test-only** code:

- `Source/PhaseCorrelationMeter.h` (171 lines) — nothing in `Source/` constructs it.
- `Source/AudioSimilarity.h` (165 lines) — only `test_audio_similarity_main.cpp`.
- `Source/AudioEvidence.h` (160 lines) — only `test_audio_evidence_main.cpp`.
- `Source/PhysicalSynthesizer.h` (268 lines) — only `test_physical_acoustics_main.cpp`.
- `PhysicalAcoustics::evaluateMixCollision` (`:675-745`) and `ClassificationPresentation::isNeutral`.

Keep the tests, delete the code, and delete the tests that then have nothing left to exercise. Also clean up:

- `ResultsPanel`'s aspect-weight strip — 6 sliders, 6 labels, a heading, a reset button, laid out in `resized()`. `Row::AspectScores` duplicates `SloAudioSimilarity::AspectScores`, **no production code ever writes `row.aspects`** so both render branches (`:126-128`, `:348-358`) are unreachable, and `setAspectWeightsChangedCallback` is never called at all.
- `AbletonTaxonomy`'s two `detectLoopVsOneShot` overloads, which **disagree at exactly 1.5 s** (`:66` `>= 1.5f` vs `:101` `> 1.5f`). The 2-arg one has no production caller and exists only to be tested — delete it and its three tests.
- `fadeOutRequested` (`PluginProcessor.h:157`) — write-never; declared, read once at `:136`, never set, and it makes the `||` look like it has two producers.
- `customTargetDir` (`SampleManagerEngine.h:699`, `:822`) — a defaulted parameter no caller supplies.
- The two `inline std::atomic<bool>` feature flags (`MlOverrideGate.h:37`, `AbletonTaxonomy.h:27`) are written only by their own test binaries, so permanently `false` in production — which also makes ~35 lines unreachable, and would silently invalidate cached rows the moment a UI toggle is wired, since `kTaxonomyVersion` wouldn't change. Delete the flags and gated branches, or make them `constexpr`.
- Comment corruption from a bad find/replace: `MlOverrideGate.h:31-34` (a dangling `"_FILENAME evidence weight cap:"` fragment), `AbletonTaxonomy.cpp:83-84` (a duplicated comment line).
- `playSample`'s quantised and immediate branches are byte-identical (`PluginProcessor.cpp:167-180`) — the only difference is a 15-line comment. Collapse to one call.

**Do not touch** (R8): `AcousticClassifierWeights.h`, `AcousticClassifierCentroids.h`, and the ~20 undocumented thresholds in `PhysicalAcoustics.h`. For the thresholds, the deliverable is a comment block recording the corpus and CV accuracy for the tree as a whole — or, if they were hand-tuned, saying so plainly. Contrast `AbletonTaxonomy.h:141-179`, which documents 649 by-ear labels, 5-fold CV and 96.4% held-out. `AbletonTaxonomy.cpp:70`'s `4.0f` is the one exception in an otherwise exemplary file.

---

## 6. Phase 4 — Propose, do not execute (needs owner sign-off)

1. **CSV → JSONL sort journal** (P0-4(3)). Closes the injection properly; invalidates every existing journal on user disks. `CorrectionLog.h` already does JSONL correctly.
2. **Audio-thread ownership of `transportSource`** (P1-10). Highest-risk change in the document. Needs a real host soak, not just the stress binary.
3. **Bass/hi-hat confidence floors** (P1-22) and any other threshold change. Blocked on a holdout similarity distribution that is not in the repo.
4. **A `ctest`-equivalent for the six `ssm_qual_*` groups.** `ctest` (R1) is the real fix; decide whether the custom targets stay as build-only gates or become run gates.
5. **`test_licensing_main.cpp` needs a live `uvicorn` + a real key** to be meaningful. Either stand up a local server in CI, or mark it explicitly as a manual soak so nobody runs it casually against a real licence.
6. **`getTailLengthSeconds()` returns 0.0** (`PluginProcessor.h:26`) while the processor is writing audio. If that truncates audition playback in a host with the transport stopped, it needs the remaining reader length. Needs a host soak to confirm — mark it unknown until then.

---

## 7. Deliverables

1. **Baseline table** (Phase 0): binary | runs? | pass/fail | seconds.
2. **Per-finding log**: finding ID | fixed/deferred | test that failed then passed | commit SHA. Every entry in §3–§5 appears here, with deferrals carrying a written reason.
3. **Before → after table**: `ctest` pass count, RT `deadline_misses`, RT `callback_max_ms`, and the source line count before and after Phase 3.
4. **Dead-code ledger**: item | grep evidence | lines removed | kept-or-deleted decision.
5. **Corrections to the review itself** — anything you found wrong, with evidence. The review is a document, not scripture, and saying so in it is more valuable than quietly working around it.
6. **New findings** logged, not fixed (R4).
7. **What you deliberately did not touch**, and why.

**Final commit discipline:** single-line plain commit messages stating what changed and why it matters. **Never** `Co-Authored-By:` or any AI attribution trailer. Nothing pushed.
