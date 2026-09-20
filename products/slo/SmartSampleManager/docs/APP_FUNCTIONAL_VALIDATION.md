# App Functional Validation

Master Functional / Release Testing phase ("Prove the App Actually Works"). This is the
canonical record of what was **actually run**, against the real built artifacts, with runtime
evidence — not a re-statement of the static release-guard checks already covered in
`docs/MACOS_RELEASE_PIPELINE.md`, `docs/PRIVATE_BETA_RC.md`, and
`docs/RELEASE_CANDIDATE_VALIDATION.md`. Per this phase's own mandate, an item below is marked
**EXECUTED** only when it was genuinely run and produced observable evidence (screenshot, log
line, process/file state) this session; everything else is marked **NOT EXECUTED** or
**BLOCKED**, honestly, rather than inferred from adjacent passing checks.

Environment: macOS (this dev machine), Release build (`build-release`), Standalone/AU formats
built and exercised directly; VST3 built but no validator tool available on this machine.
Test data: KSHMR Vol.3 sample pack (user-owned, real commercial content) at
`sample_pack_testing/Sounds of KSHMR Vol.3/KSHMR_Drums/`.

## 1. Build & baseline suites — EXECUTED

- Fresh `cmake --build build-release`: succeeded.
- Native test suite: 12/12 passed, zero leaks (reconfirmed this phase).
- Backend commercial E2E suite: 11/11 passed.
- Release guards: identity manifest, release manifest, Homebrew dependency graph, and the new
  `check_missing_deps` (every `@loader_path`/`@rpath` reference resolves to a real file) all
  PASS across all 3 formats, both `build/` and `build-release/` trees.

## 2. Critical packaging bug found and fixed this phase — EXECUTED

Full writeup: `docs/CRITICAL_FINDING_LAUNCH_BLOCKING_BUG.md`. Summary: a symlink-resolution
mismatch in `scripts/bundle_apple_deps.py` caused the Standalone build to crash on launch
(`dyld: Library not loaded`) despite every prior static check passing. Found only because the
app was actually launched. Fixed; a new automated check now closes the gap. Verified by direct
launch, screenshot, and a real `auval` PASS.

## 3. Standalone launch stability — EXECUTED

10/10 clean launch → visible window → clean shutdown cycles, zero crashes.

## 4. AU / VST3 validation — PARTIAL

- `auval -v aufx AtSm NDSP` against the real built component: **AU VALIDATION SUCCEEDED**
  (reconfirmed twice this phase, including after a full rebuild).
- VST3: no validator tool (`VST3PluginTestHost`/JUCE's `validator`) exists on this machine or in
  this checkout — **NOT EXECUTED**, correctly reported as unavailable rather than skipped
  silently.
- Ableton Live plugin discovery: attempted via GUI automation; automation proved unreliable
  (blind keystrokes triggered transport shortcuts and an unexpected modal) and was abandoned
  rather than risk further unintended side effects on the user's real Ableton install —
  **INCONCLUSIVE**, not claimed as PASS or FAIL.

## 5. Real library scan — EXECUTED

Launched the Standalone app, used the real "SCAN FOLDER" button and native `NSOpenPanel` file
picker (via Cmd+Shift+G "Go to Folder", not synthetic path injection) to scan
`KSHMR_Kicks` (289 real `.wav` files across 8 subfolders).

- Scan completed: UI counter progressed live (5 → 133 → 289 samples), visual map populated with
  one point per sample, real ONNX Runtime + CoreML inference log lines confirmed
  (`CoreMLExecutionProvider::GetCapability`, 38/45 nodes on CoreML).
- Peak resource usage during active scan: RSS ~2.0 GB, CPU ~335% (multi-threaded). Idle after
  completion: RSS ~1.3 GB, CPU ~2%.
- UI remained responsive throughout.

## 6. Database persistence — EXECUTED, with a clarified finding

- The on-disk cache DB (`~/Library/SmartSampleManager/sample_cache.sqlite3`, SQLite WAL mode) is
  real and does accumulate scanned data — confirmed via file size/mtime evidence (1.3 MB main
  file + active WAL, growing across the scan).
- **Note on path**: `SampleManagerEngine::getCacheDbFile()` builds the path from JUCE's
  `File::userApplicationDataDirectory`; on this machine/JUCE version that resolves to
  `~/Library/SmartSampleManager/`, not `~/Library/Application Support/SmartSampleManager/` as
  the more common macOS convention would suggest. Not a bug (JUCE's own resolution), but worth
  knowing when locating the file for support/debugging.
- **Rescanning the same folder is fast** (289 samples repopulated in ~2 seconds, vs. the original
  scan's sustained multi-second CPU-heavy embedding pass) — confirms the embedding/UMAP cache
  described in `docs/UMAP_PERSISTENCE.md` genuinely works cross-launch.
- **However**, a clean app relaunch shows "Map: 0 samples" — the library is *not* automatically
  reloaded on startup. Checked the source (`PluginEditor.cpp::openFolderScanner`): the saved
  `lastScanFolder` setting is used only as the file picker's starting directory, never to
  trigger an automatic re-scan/re-load on launch. This is existing, intentional behavior, not a
  regression — but it means a customer must manually reselect their folder every session (the
  reselect is fast thanks to the cache, but it is not automatic). Worth product consideration,
  not a functional defect.

## 7. Shutdown during active background work — EXECUTED, PASS

Triggered a scan of a fresh, previously-uncached folder (`KSHMR_Snares`, 111 files), then
`kill -9`'d the process mid-scan (at 3/111 samples committed, confirmed via screenshot). Result:

- Relaunch was clean — no crash, no error dialog, no hang.
- No new database corruption/quarantine event was produced by the kill (confirmed by file
  timestamps: the most recent `.corrupt-*` quarantine file predated this test).
- Rescanning the same folder afterward completed cleanly to the exact correct count (111/111),
  with no duplicate-key errors or stuck state.

## 8. Multiple concurrent Standalone instances — EXECUTED, PASS (with a caveat)

Launched 3 Standalone instances simultaneously; all 3 stayed alive and responsive. Triggered a
second scan (`KSHMR_Claps`, 158 files) on the original instance while the other two sat idle in
the background — it completed correctly (269 = 111 + 158, no corruption), and the two idle
instances remained unaffected throughout. All 3 terminated cleanly via `SIGTERM`.

**Caveat**: a true simultaneous-write test (two different instances scanning two different
folders at the same moment) was attempted but could not be reliably isolated — AppleScript/
System Events window targeting proved unreliable across multiple identically-titled
"Smart Sample Manager" windows (the same class of automation limitation documented for the
Ableton test above), so both scan triggers landed on the same instance instead of two different
ones. The core concurrency-safety result (multiple instances open + one actively writing while
others are open, no crash) is solid; the stricter two-simultaneous-writers case is **NOT
FULLY VERIFIED** and should not be claimed as tested.

## 9. Corruption quarantine mechanism — EXECUTED (via existing evidence), real and working

Found ~30 historical `sample_cache.sqlite3.corrupt-<timestamp>` files under
`~/Library/SmartSampleManager/` while investigating item 6. Traced to
`SampleManagerEngine.cpp:215` (`quarantineSuffix = ".corrupt-" + ...`) and the native
`TestResilience` executable (`Source/test_resilience_main.cpp`), which is part of the already-
passing 12/12 native suite and deliberately corrupts a cache DB copy to verify quarantine
behavior. This confirms the quarantine mechanism is real and exercised, not just present in
source. **Process note (minor, not a customer-facing bug)**: `TestResilience` writes its test
corruption directly at the same real path the production app uses, rather than an isolated temp
directory — harmless in CI/dev (no real library was ever affected; both are on this same dev
machine and the app's own data was never mistaken for corrupted), but worth an isolated test
fixture path if this test is ever run somewhere a real user library shares the machine.

## 10. Missing-file / corrupt-audio / disconnected-drive handling — COVERED BY EXISTING NATIVE TESTS

Per this phase's "avoid overlapping test docs" guidance: `TestMalformedAudio`, `TestPruneMissing`,
and `TestMultiInstance` are part of the already-reconfirmed 12/12 native suite (item 1) and
directly cover malformed-audio handling, pruning of missing files, and multi-instance DB access
at the engine level. Not re-derived from scratch here; cited as existing, current, passing
coverage rather than duplicated.

## 11. Not executed this phase (honest gap list)

The following remain **NOT EXECUTED** — no runtime evidence was produced for these, and none
should be inferred from the items above:

- Quantized audition/preview regression test
- Realtime-safety instrumentation (audio-thread allocation/lock checks under load)
- Find Similar against real audio (kick/snare/texture query samples)
- Find Similar behavior after underlying files change
- Embedding-model-failure / mid-inference-failure injection
- Small-library visual map edge cases (below the 5-sample UMAP short-circuit threshold)
- Duplicate detection against real files
- Sort/reorganize test (disposable data only — not run against the real KSHMR library)
- Drag/drop into Ableton
- Ableton XMP/taxonomy write-back (explicitly labeled experimental in the product itself)
- Database corruption recovery using a deliberately-corrupted *copy* (item 9 above covers the
  mechanism via existing test evidence, not a fresh manual corruption run this phase)
- Long-run soak test (30–60 min)
- Rapid UI stress test
- DAW-project-close-during-work test
- Licensing UI against staging backend; network-failure/tamper/wrong-product/wrong-machine
  cases; activation-limit concurrency re-run
- Account/backend UI walkthrough
- Download-authorization UI walkthrough
- Update-check (no client-side implementation exists yet, per
  `docs/RELEASE_CANDIDATE_VALIDATION.md`)
- No-localhost/secret scan of this session's exact rebuilt artifacts (last verified in the
  Critical Finding phase, not re-run against today's rebuild)
- Installer test — correctly **BLOCKED**, no installer exists (chained on code signing)
- Full explicit customer-journey walkthrough (purchase → download → activate → first scan) end
  to end against live infrastructure — chained on the same BLOCKED EXTERNAL items
  (`docs/PRIVATE_BETA_RC.md`: Apple signing, hosted backend, clean machine)

These are gaps to close in a follow-up pass, not claims of failure.
