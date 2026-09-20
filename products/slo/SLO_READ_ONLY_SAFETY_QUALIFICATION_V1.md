# SLO Read-Only Safety Qualification V1

**Purpose:** prove — with real evidence, not architectural claims — that SLO's automatic scan/classify path cannot damage a user's real sample library. Required before any private beta given the beta definition's "non-destructive... no automatic reorganisation" terms.

## Method

### 1. Code review: every file-mutating call site in the engine

Searched `SampleManagerEngine.cpp` for every `deleteFile()`/`moveFileTo()`/`copyFileTo()`/similar call. Result: exactly two categories exist, nothing else.

1. **The engine's own cache database** (lines ~287-301, 813-817, 1078-1080): legacy-cache migration, quarantine-and-rebuild on corruption, cache deletion. All operate on the engine's *own* SQLite cache files (`sample_cache.sqlite3` and its `-wal`/`-shm` journals) — never on the user's audio files.
2. **`reorganizeSamples()`** (line 4779 onward, the Sort Library feature): the only place `sourceFile.copyFileTo()`/`sourceFile.moveFileTo()` touch actual library audio files. This is:
   - Never called automatically — only from an explicit user button click (`PluginEditor.cpp`'s `performSortLibrary()`).
   - Gated behind a confirmation dialog stating exactly what will happen.
   - **Defaults to copy, not move** (fixed this session, see B-011 in the blocker register) — even the explicit, consent-gated path defaults to the non-destructive option.

**Conclusion from code review**: the automatic scan/classify path — the one with no per-file consent prompt, the one that runs the moment a folder is added — contains zero file-mutating code.

### 2. Real, automated proof (not just code review)

Code review alone is a claim. `TestReadOnlySafetyQualification` (new test, this session) makes it a measured fact:

1. Copies 4 real fixture audio files (from this repo's own test fixtures — never the owner's real library) into a disposable scratch directory.
2. Records real SHA-256 checksums (via libsodium's `crypto_hash_sha256`) and file sizes for every file — the **BEFORE** snapshot.
3. Constructs a real `SampleManagerEngine` (not a mock), points it at the fixture directory, and runs a full scan — the exact same code path a real user's automatic library scan uses.
4. Records SHA-256 + size again — the **AFTER** snapshot.
5. Asserts: same file count, and every single file's checksum and size byte-identical before vs. after.

**Result: PASS.** All 4 fixture files identical before/after, file count unchanged (4→4). Full receipt: `products/slo/SmartSampleManager/tools/classification_benchmark/results_readonly_safety_receipt.json` (not committed to git — regeneratable, same convention as this session's other `results_*.json` artifacts; the SHA-256 values themselves are reproduced below for durability).

| File | SHA-256 | Size | Identical |
|---|---|---|---|
| `real_kick_a.wav` | `eae5f39518f7df0719b0d14dd2daff270aa3eaea71c082d1c77bac2afb1a01f8` | 176,444 bytes | ✅ |
| `real_kick_b.wav` | `bcc198c55c4f2ebc399dac0c6721bb05861a8c7441c26898ac8eab42db0e2932` | 176,444 bytes | ✅ |
| `real_sustained_noise.wav` | `7eaacaa03e48809ec80038565ba4814fe971809cf496023214c5bd66581a8338` | 176,444 bytes | ✅ |
| `test_kick.wav` | `71b1dbbcc8a2a1e9989527df30f8620de2525da0d18ec62ea1ac7f63f2af5a51` | 89,348 bytes | ✅ |

## What this does and does not prove

**Proves**: the scan/classify path, exercised against a real engine and real audio files, does not delete, move, rename, or modify file contents. This is real, repeatable, machine-checked evidence.

**Does not prove**: behavior under abnormal conditions this test didn't exercise — e.g. a crash mid-scan, a permissions error partway through a large folder, or concurrent access from another process. Those are legitimate follow-up qualification targets, not covered by this pass.

## Sort Library (the one feature that DOES write to the library)

Separately qualified via B-011 (`NITE_DSP_SLO_MASTER_PLAN_V1.md` Phase 4): defaults to copy, not move; explicit confirmation dialog; text corrected to accurately describe the copy behavior. For beta, given the definition's "no automatic reorganisation of real sample libraries unless explicitly approved" requirement, this already satisfies "explicitly approved" (the confirmation dialog) — the remaining open item (not blocking, but worth doing before beta if time allows) is a genuinely reversible undo/rollback path beyond "copying leaves originals in place," which is still open per the blocker register.

## Fixture-only discipline

This test — and every other test in this codebase, verified by the same "isolate the cache DB" pattern appearing in every engine-touching `Test*` target — never runs against a real owner sample library. No test in this session's work, or in the pre-existing test suite, was run against real user data.
