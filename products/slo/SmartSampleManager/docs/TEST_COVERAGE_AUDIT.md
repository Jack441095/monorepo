# SmartSampleManager — Test Coverage Audit

Phase 1, Sections 25-26. All 9 regression targets were actually built and run during this audit (not just read) — see results below. Also covers CI isolation.

**Phase 3 update**: per Phase 3 Section 2's regression-safety requirement, the full 12-test
suite was rebuilt from a clean state and rerun before any Phase 3 commercial-architecture work
began — all 12 pass, exit code 0, zero leak warnings. Phase 3 made no source-code changes (design/
documentation only), so no new test coverage was needed; this note exists to confirm Phase 2's
hardening state was actually re-verified, not assumed, before building on top of it.

**Phase 2 update**: a 10th target, `TestResilience`, was added (`Source/test_resilience_main.cpp`)
covering two of Phase 2's hardening passes: missing/invalid ONNX model handling (no fake
pseudo-embedding, honest `FailedRetryable`/`FailedPermanent` status — see
`docs/ONNX_FAILURE_HANDLING.md`) and cache DB corruption detection/quarantine-and-rebuild (see
`docs/DATABASE_HARDENING.md`). Built and run this session — both checks pass, confirmed via real
log output (`"Sample cache DB failed integrity check -- quarantining..."`,
`"missing model handled honestly..."`), not just an exit code. Added to
`.github/workflows/smart-sample-manager.yml`'s explicit target whitelist alongside the other 9.

**Phase 2, second pass — 2 more targets added, closing two coverage gaps this document itself
had flagged**:

- **`TestMalformedAudio`** (`Source/test_malformed_audio_main.cpp`) — the "corrupt/malformed
  audio file handling" gap this document has listed since Phase 1 (Phase 15 of the master
  prompt). Exercises 4 distinct malformed WAV fixtures (garbage bytes, truncated header,
  zero-byte file, a header claiming far more data than the file actually contains) alongside one
  valid file in the same scan batch. All 4 are correctly rejected (never added to the library,
  cache not poisoned), and the valid file is still processed correctly. **A real finding during
  development**: the first version of the "lying data-chunk length" fixture left a few genuine
  trailing PCM bytes, and `dr_wav` correctly decoded it as a legitimate (if degenerate) 1-frame
  clip rather than rejecting it — not a product bug, a wrong test fixture, fixed by removing the
  trailing bytes so the file has zero real frames.
- **`TestMultiInstance`** (`Source/test_multi_instance_main.cpp`) — the multi-instance concurrent
  SQLite access gap flagged in `docs/DATABASE_HARDENING.md`. Two `SampleManagerEngine` instances
  scan concurrently (separate threads) into the same shared on-disk cache DB, proving the
  `busy_timeout` fix holds under real contention: no deadlock, no corruption
  (`checkCacheIntegrity()` still true afterward, on all three of two original + one freshly-
  constructed third instance), no cross-contamination between instances' in-memory sample lists.

Both added to `.github/workflows/smart-sample-manager.yml`'s target whitelist.

**Phase 2, fourth pass — `TestSortLibraryAsync`** (`Source/test_sort_library_async_main.cpp`)
closes the `reorganizeSamplesAsync()` progress/cancel/re-entrancy-guard test gap this document
previously flagged as open, and in writing it, a second real use-after-free bug — structurally
identical to the async-startup one — was found and fixed proactively (before any crash
triggered it) in `reorganizeSamplesAsync()` itself. See `docs/SORT_LIBRARY_BACKGROUND.md` for
the full detail. **12 regression targets total now.**

**Phase 2, third pass — `MessageManager` leak-detector noise eliminated.** Every test binary that
constructs a `SampleManagerEngine` (and therefore an ONNX session) previously printed `*** Leaked
objects detected: 1 instance(s) of class MessageManager` on exit — cosmetic (exit code stayed 0),
but flagged since Phase 1 as "worth a small cleanup... so future genuine leaks aren't lost in the
noise." Fixed by adding `juce::MessageManager::deleteInstance()` before each test's successful
exit (matching the pattern `test_main.cpp`/`test_licensing_main.cpp` already used correctly).
Verified: a full run of all 11 targets after the fix shows **zero** `Leaked objects` warnings
anywhere in the output.

## Test matrix (real execution results from this pass)

| Test | What it protects | Result | Gaps |
|---|---|---|---|
| `TestSampleEngine` | Core engine integration — scan, TagLib metadata read/write round-trip | PASS | — |
| `TestPathTraversal` | `reorganizeSamples()` cannot be tricked via malicious metadata into writing outside the library root | PASS | Security-relevant; good that this exists as a dedicated test |
| `TestDuplicateDetection` | Content-hash grouping survives metadata retagging | PASS | Doesn't test the "huge file" memory-growth concern noted in the data-stack audit, or hash-collision handling (acknowledged non-cryptographic by design) |
| `TestPruneMissing` | Pruning removes exactly the deleted sample, leaves others untouched, never touches disk; **extended this pass** with a regression case for the HNSW/prune desync bug found and fixed during this audit | PASS (both original + new case) | — |
| `TestEmbeddingQuality` | Real ONNX pipeline (dr_wav → resample → PANNs Cnn10) produces acoustically meaningful, separable embeddings | PASS (kick_a↔kick_b: 0.989 similarity; kick↔noise: ~0.67) | Doesn't test missing-model or corrupt-model fallback paths (those exist in code per the data-stack audit but aren't test-covered) |
| `TestFindSimilar` | HNSW "find similar" ranks correctly, excludes the query itself, handles unknown paths gracefully | PASS | Didn't cover the prune-desync case before this audit — now covered via `TestPruneMissing`'s extension instead |
| `TestTaxonomy` | Ableton category/subcategory/loop-vs-one-shot classification | PASS | — |
| `TestXmpWriter` | XMP sidecar writing, backup-before-overwrite, never touches source audio | PASS | — |
| `TestLicensing` | Full activate → reload → revalidate → tamper-rejection → deactivate flow against the dev licensing server | **Not run interactively during this audit** — requires a running `licensing_server` instance and a live license key; starting a local network server was blocked by this session's sandbox policy. CI runs this exact flow on every push (see `smart-sample-manager.yml`) and its own configuration was reviewed and confirmed correct (ephemeral per-run keypair, explicit endpoint sequence matching the client's expectations) | Confidence comes from source-code audit (see `docs/LICENSING_PRODUCTION_GAP.md`) plus CI's automated coverage, not a fresh local run this session |

**8 of 9 tests independently re-run and confirmed passing in this session, both before and after the two fixes applied (realtime-thread bug, HNSW/prune desync bug) — no regressions.** All 9 tests are exercised automatically by CI on every push.

## Known non-blocking noise — RESOLVED in Phase 2

~~Every test except `TestSampleEngine`, `TestTaxonomy`, and `TestXmpWriter` prints `*** Leaked objects detected: 1 instance(s) of class MessageManager` on exit~~. **Fixed this session** —
`juce::MessageManager::deleteInstance()` added before each affected test's successful exit.
Verified: zero `Leaked objects` warnings across all 11 targets as of this session's final full
run.

## CI isolation (`.github/workflows/smart-sample-manager.yml`)

Reviewed directly — this is well-built:

- **Path-filtered**: only triggers on changes under `studio/vst3_plugins/SmartSampleManager/**` or the workflow file itself — won't run for unrelated repo changes, and won't accidentally couple to sibling-plugin changes.
- **Explicit target whitelist**: the build step lists exact CMake targets (`SmartSampleManager_Standalone SmartSampleManager_VST3 SmartSampleManager_AU Test*`) — no wildcard/bare `cmake --build .` that could pull in `AudioToo_Reverb`, `KENNMixAssistant`, or `MidiGenerator` from the shared umbrella project.
- **Ephemeral licensing keys**: generates a throwaway Ed25519 keypair per CI run and patches it into the source before building, rather than relying on committed key material — correct, matches the "private key never touches the repo" rule.
- **Real licensing integration test**: starts the dev server, mints a license via the admin endpoint, runs `TestLicensing` against it, tears down — this is exactly the flow this audit could not run locally due to sandbox restrictions, and CI already proves it works on a clean runner.
- **Launch smoke test**: confirms the Standalone app doesn't crash within 5 seconds of launch — a real (if basic) end-to-end sanity check beyond unit tests.

~~**Gap**: this is CI (build + test), not yet a release/publish pipeline... a future release workflow should add an explicit assertion that no sibling-plugin artifact ends up in the packaged output~~ — **CLOSED this session**: `scripts/verify_release_manifest.py` + a new `Verify release manifest` CI step now automatically fail the build if any unexpected file, or specifically a sibling-plugin artifact by name, appears in any of the three built bundles. This is still CI, not a deliberate-tag-triggered release/publish pipeline (`docs/MACOS_RELEASE_PROCESS.md` still describes that as future work) — but the actual artifact-purity assertion this note was about is done and enforced on every push.

## Coverage gaps worth adding (not blockers, P2/P3)

- ~~Missing/corrupt ONNX model fallback behavior... isn't test-covered~~ — **CLOSED this session**, see `TestResilience`.
- ~~Malformed/corrupt audio file handling... not present~~ — **CLOSED this session**, see `TestMalformedAudio`.
- ~~Multi-instance concurrent SQLite access... `busy_timeout` gap~~ — **CLOSED this session**, see `TestMultiInstance`.
- Very small library UMAP edge case (surfaced during this audit's new test — see `docs/SEARCH_QUALITY_AUDIT.md`) — covered incidentally by `TestPruneMissing`/`TestFindSimilar`'s small-fixture-count logs (`docs/UMAP_PERSISTENCE.md`), not a dedicated assertion-based test.
