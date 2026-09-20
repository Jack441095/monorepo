# SLO REFACTOR BRANCH — FULL VERIFICATION PROMPT (F-01 → F-04)

> Run from `/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP`. Read-only except: you may build into existing `_build/` dirs and run test binaries. NO source edits, NO commits, NO pushes, NO installs.

## 0. Target
Branch `refactor/slo-next-level-v1` in repo `Nite-DSP-Operations/monorepo/products/slo` (remote `github.com/Nite-DSP/slo`), expected stack on top of `main` @ `edd205c`:
1. `c6a5be5` F-01 UNKNOWN review queue (PluginEditor.h/.cpp, ResultsPanel.cpp)
2. `cdd9e26` F-02 engine AudioOnlyView (SampleManagerEngine.h/.cpp)
3. `dc6c0d2` F-02 inspector audio-model badge (PluginEditor.h/.cpp)
4. `69dcdf9` F-03 engine ScanReceipt (SampleManagerEngine.h/.cpp)
5. `5ba5f66` F-03 UI receipt/completion dialog (PluginEditor.h/.cpp)
6. `935dffd` F-04 engine buildDiagnosticsBundle (SampleManagerEngine.h/.cpp)
7. `85dad75` F-04 UI export + TestDiagnosticsBundle (PluginEditor.h/.cpp, MainMenuModel.h/.cpp, test_diagnostics_bundle_main.cpp [new], CMakeLists.txt)

First: `git -C Nite-DSP-Operations/monorepo/products/slo log --oneline -8` and `git status --short | grep -v '^??'`. FAIL the run if the stack differs or any tracked file is dirty (untracked files are expected: 380+ research/docs + build outputs).

## 1. Environment (known-good, do not deviate)
- MUST use arm64 `/opt/homebrew/bin/cmake` — NOT `/usr/local/bin/cmake` (Intel x86_64, fails against arm64 CLT libxcrun; this is a verified environment quirk, not a code bug).
- Preset `ssm-dev`, existing build dir `products/slo/_build/ssm-dev` (rebuild incrementally; full configure took ~300s, full build longer — reuse it).
- ONNX Runtime 1.29.0 expected (headers `/opt/homebrew/Cellar/onnxruntime/1.29.0/`, lib `/usr/local/opt/onnxruntime/`).

## 2. Build gate
`/opt/homebrew/bin/cmake --build --preset ssm-dev -j 10` from `SmartSampleManager/`. Must reach 100% with ZERO `error:` lines. Record all NEW warnings vs baseline (`SortPreviewPanel` unused-param / `SmartCollectionsPanel` float-conversion / ONNX mismatched-tag warnings are pre-existing — anything mentioning `AudioOnlyView`, `ScanReceipt`, `DiagnosticsBundle`, `UnknownQueue`, `audioModel`, `Receipt`, `formatScanReceipt`, `noteSkippedDrops` is NEW and must be listed verbatim).

## 3. Automated sweep (must be 52/52)
Run every executable `../_build/ssm-dev/Test*` directly (there is NO ctest preset — that is expected, not a failure). `TestLicensing` bare prints usage and exits nonzero BY DESIGN — run it as `TestLicensing --url-policy` (must print ALL LICENSING URL POLICY TESTS PASSED). Full-key licensing needs `localhost:8420` (known B-03 gap — record as ENV-DEFERRED, not a failure).
- Expected: 52 PASS, 0 FAIL (51 original incl. licensing-via-flag + new TestDiagnosticsBundle with 18/18 checks).
- Any other failure: capture the last 40 log lines, mark REGRESSION, stop that section and continue the rest.

## 4. Safety invariants (each must be explicitly re-verified, not assumed)
1. `TestReadOnlySafetyQualification` — ALL PASSED, SHA-256 byte-identical, file count unchanged.
2. `TestRtDeadlineStress` — 0/2000 misses, 0 allocs; record mean/max/p99 (baseline max was 0.777ms; flag if max > 2ms).
3. `TestPruneMissing` — exit 0, disk untouched, HNSW invalidation assertions hold.
4. `TestCacheVersionEnforcement`, `TestPersistedCacheHydration`, `TestFormatAwareScan`, `TestMalformedAudio`, `TestInferenceBatchFlush`, `TestPathIndexIntegrity` — all exit 0 (these pin the exact code paths F-03 touched: admission, commit, hydration, prune).
5. `TestClassificationPresentation` + `TestCorrectionLog` + `TestAcousticClassifierParity` — exit 0 (these pin the semantics F-01/F-02 reuse: ml_ood→"Unknown Other", evidenceLabel strings, uncertaintyReason thresholds, no-op correction rejection).

## 5. Feature verification (static + behavioral)
For each feature, do (a) code review of the diff (`git show <sha> --stat` + read the hunks) against its contract, and (b) the behavioral check:
- **F-01**: contract = presentation-only; `showReviewQueue(bool=false)` default keeps old callers identical; unknown predicate = empty-cat OR `isMlOod`; no threshold/schema/API change. Behavioral: `TestClassificationPresentation` green (covers the pinned functions); review-queue sort/filter logic has no unit test — state that as UNVERIFIED-UI and list the manual script (open Standalone → SCAN LIBRARY on fixtures → R opens full queue, U opens unknown-only, row shows "UNKNOWN • OOD abstention", empty state reads "No unknown samples…").
- **F-02**: contract = `getAudioOnlyView()` never mutates (check: method is const, only reads under `ScopedLock`, classifies after release, linear scan not pathToIndex); inspector label display-only. Behavioral: no automated UI coverage exists — state UNVERIFIED-UI with manual script (select classified sample → "Audio model: X (N%)" line visible; filename-heuristic row shows "differs from shown label" in warning colour; heuristic-only row hides the line).
- **F-03**: contract = counters-only; admission/decode/cache paths behavior-identical (prove via §4 item 4 suite); reset-on-fresh-start / accumulate-on-overlap semantics. Behavioral: `TestDiagnosticsBundle` asserts `added==2, skipped>=1` end-to-end (this IS the automated proof of the skip path). Manual script: drop mixed folder → completion dialog shows "+A ~C · S skipped"; drop lone .txt → immediate "Drop Skipped" dialog, no scan starts.
- **F-04**: contract = export-only, `record_type: slo_diagnostics_bundle` distinct from evidence-packet import contract (prove: `test_label_free_evidence_packet` suite green + record_type string differs from `slo_label_free_evidence_packet`). Behavioral: `TestDiagnosticsBundle` 18/18 green. Manual script: EXPORT DIAGNOSTICS → save → JSON parses, contains app/models/ood_gate/library/evidence_splits/log_tail.

## 6. No-go checklist (any hit = BLOCKED, report file:line)
- Any change to `AcousticClassifier*.h` weights/thresholds, `MlOverrideGate` logic, `AbletonTaxonomy` classify path, SQLite schema (`CREATE TABLE`/`ADD COLUMN`), `reorganizeSamples`, license verification, or network/telemetry code. Verify with `git diff edd205c..HEAD --stat` — allowed files are ONLY: PluginEditor.h/.cpp, ResultsPanel.cpp, SampleManagerEngine.h/.cpp, MainMenuModel.h/.cpp, test_diagnostics_bundle_main.cpp (new), CMakeLists.txt (registration only). Any other file = BLOCKED.
- Any secret value (keys, tokens, paths under `licensing_server/keys/`, `.env`) in diffs or new files — paths-only is fine, values are P0.
- Any new dependency in CMakeLists beyond the test registration.

## 7. Deliverable
Write `Nite-DSP-Operations/monorepo/validation/audits/slo-next-level-v1/edit-pass-2026-09-17/VERIFY_<YYYY-MM-DD>.md` with: environment receipt, build result + new-warning list, 52-row test table (binary | pass/fail | notes), invariant results with numbers, per-feature contract verdict (VERIFIED / UNVERIFIED-UI + manual script), no-go checklist result, and a final GO / GO-WITH-NOTES / BLOCKED verdict for merging the branch. Machine-readable summary appended as `VERIFY_<date>.json` (`{branch, build, pass, fail, failures[], invariants{}, features{}, nogo, verdict}`).

## 8. Change log for this prompt
| Version | Date | Change |
|---|---|---|
| V1 | 2026-09-17 | Initial verification prompt for refactor/slo-next-level-v1 (F-01→F-04). |
