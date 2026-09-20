# SmartSampleManager — Sort Library Background Workflow

Phase 2, Sections 24-25. Addresses `docs/COMMERCIAL_RELEASE_BLOCKERS.md` P1 #2 ("Sort Library"
freezes UI on large libraries) and the master prompt's file-operation transaction-model
requirements.

## What was there before

`reorganizeSamples()` ran synchronously on whichever thread called it — for the UI, that was the
message thread (`PluginEditor::performSortLibrary()` called it directly from a button click).
Per-file disk move/copy happened under `dbLock` for the whole library, with **no confirmation
dialog before modifying files on disk**, no progress indication, and no way to cancel.

## What was NOT changed

The actual reorganization logic in `reorganizeSamples()` — naming-style formatting, category
folder resolution, path-traversal defense-in-depth checks, content database sync — is untouched.
This pass only changes *how* and *from which thread* it runs, plus adds progress/cancel
plumbing. `docs/PRODUCT_READINESS_AUDIT.md`'s existing `TestPathTraversal` coverage was rerun
and still passes unchanged, confirming the security-relevant behavior wasn't touched.

## New API (`Source/SampleManagerEngine.h`/`.cpp`)

```cpp
void reorganizeSamples(int namingStyle, bool copyInsteadOfMove = false);  // unchanged, still synchronous
void reorganizeSamplesAsync(int namingStyle, bool copyInsteadOfMove,
                             std::function<void(int moved, int failed, bool cancelled)> onComplete);
void cancelSortLibrary();
struct SortLibraryProgress { bool inProgress; int done; int total; int failed; };
SortLibraryProgress getSortLibraryProgress() const;
```

`reorganizeSamples()` itself is kept as a public, synchronous method — the test suite
(`TestPathTraversal`) calls it directly and doesn't need async/progress semantics.
`reorganizeSamplesAsync()` runs the same function on a `juce::Thread::launch()` background
thread and wraps it with progress-counter updates and a cancellation check.

### Progress and cancellation

- `sortDone`/`sortTotal`/`sortFailed`/`sortInProgress`/`sortCancelRequested` are plain
  `std::atomic` counters — not locked, since they're progress indicators polled by the UI, not
  correctness-critical shared state.
- The per-file loop in `reorganizeSamples()` checks `sortCancelRequested` once per file (not more
  granularly — an individual `juce::File::moveFileTo()`/`copyFileTo()` call is already atomic at
  the OS level, so there's no safe finer-grained cancellation point mid-file). Already-moved files
  stay moved; cancellation stops before the *next* file, not a rollback of prior ones.
- A file that fails to move/copy (disk full, permission denied, etc.) increments `sortFailed` and
  is simply left in its original location — `sample.filePath` is only updated on success, so the
  in-app database never points at a file that wasn't actually moved.

### Re-entrancy guard

`reorganizeSamplesAsync()` checks-and-sets `sortInProgress` atomically at the top; a second call
while one is already running is a no-op rather than starting an overlapping pass (which would
both contend for `dbLock` and reset the first pass's progress counters mid-flight).

## UI changes (`Source/PluginEditor.cpp`)

- **Confirmation dialog before any filesystem change** (`juce::AlertWindow::showOkCancelBox`) —
  states how many files will be moved/renamed before starting. This did not exist before this
  pass.
- **Sort button doubles as a cancel button** while running (`"Sorting 42/500 (click to cancel)"`,
  updated every editor timer tick from `getSortLibraryProgress()`) — click during a sort calls
  `cancelSortLibrary()` instead of starting a new one.
- **Completion summary** — on finish, an alert box reports moved/failed/cancelled counts when
  anything other than a clean full success occurred (silent on full success, matching the
  existing "SORTED!" button-text flash for the common case).

## Durable journal and rollback

The sort path now writes a durable `.slo_sort_journal_*.csv` before any file action and appends
planned, committed, and failed rows as it runs. The journal records the exact source→destination
mapping and is only considered undoable while it has not been marked `.undone`. The preview panel
offers an explicit Copy/Move/Cancel choice and an **Undo Previous Sort…** action; undo verifies the
recorded paths before restoring files and reports partial failures instead of silently claiming
success. This keeps the operation recoverable after a partial run while preserving the existing
path-traversal and copy-preservation guarantees.

### Remaining limitations

- **A disk-space preflight check** — `juce::File::moveFileTo()`/`copyFileTo()` already fail
  cleanly (return false, nothing partially written per JUCE's implementation) on a full disk,
  which surfaces as a normal per-file failure in the existing `sortFailed` counter/summary dialog.
  A preflight estimate-and-warn wasn't added.
- ~~**Automated regression test for the async path**~~ — **added later this session**:
  `TestSortLibraryAsync` (`Source/test_sort_library_async_main.cpp`). See below.

## A real use-after-free bug found and fixed after this doc was first written

`reorganizeSamplesAsync()` originally used the same unmanaged `juce::Thread::launch()` pattern
that caused a real, reproduced crash in the async-startup code (see `docs/ASYNC_STARTUP.md`).
The engine's destructor had **zero synchronization** with this thread — if the engine were
destroyed while a sort was still in flight (e.g. a host closing/removing the plugin mid-sort),
the background thread would go on touching `samples`/`dbLock`/`sortDone`/`sortFailed`/
`sortInProgress` on a destroyed object. Found by re-reading this code with the async-startup bug
fresh in mind (not by a crash this time — proactively, before it had a chance to be triggered the
same way), and fixed with the identical pattern: an engine-owned `std::thread sortThread`,
joined in `~SampleManagerEngine()`. The destructor also sets `sortCancelRequested` before
joining, so a fast destroy during a large in-progress sort doesn't have to block until every
remaining file is processed — it cancels first, then waits for the (now much shorter) remainder
to actually stop.

## New regression test: `TestSortLibraryAsync`

Covers what was previously untested:

- **Re-entrancy guard** — calling `reorganizeSamplesAsync()` a second time immediately after the
  first (same thread, so the `sortInProgress.exchange()` check is deterministic, not racy) must
  leave the engine in a state consistent with exactly one sort pass, not two overlapping ones.
  Verified via `getSortLibraryProgress()`'s `total`/`done` fields plus a direct check that no
  file was left un-sorted (still sitting in the flat scan root) or processed inconsistently.
- **Cancellation** — starting a sort on 150 real files, then calling `cancelSortLibrary()`
  immediately, must stop the operation before all 150 are visited. In the actual test run this
  landed at the earliest possible point (`0 of 150` files visited before the cancellation flag
  was observed) — still a valid pass of the underlying assertion (`done < total`), and a good
  sign the cancellation check is responsive rather than lagging.
- Both engine instances are allowed to go through a full construct → sort → **destruct** cycle,
  directly exercising the `sortThread` join-in-destructor fix rather than just asserting on it
  indirectly.

Deliberately polls `getSortLibraryProgress()` rather than waiting on the `onComplete` callback:
that callback is delivered via `juce::MessageManager::callAsync`, which needs a running dispatch
loop to fire — this test binary (like every other `Test*` target in this suite) has none, and
`JUCE_MODAL_LOOPS_PERMITTED` is off for this project (`runDispatchLoopUntil` isn't even
available), so relying on the callback would make the test hang regardless of whether the
underlying logic is correct.

## Verified this pass

Rebuilt `SmartSampleManager_Standalone`, `SmartSampleManager_VST3`, `SmartSampleManager_AU`, and
all 11 engine-linked regression test targets (including the new `TestSortLibraryAsync`) — clean
compile, all pass (exit 0), including `TestPathTraversal`'s explicit confirmation that
`reorganizeSamples()` still contains malicious metadata within the library root.
