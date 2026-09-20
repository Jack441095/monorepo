# SmartSampleManager — Commercial Release Blockers

Phase 1, Section 30, updated Phase 2, updated Phase 3. Every finding from this audit pass, classified. Cross-references the detailed docs where each item is explained in full.

## P0 — MUST FIX BEFORE ANY EXTERNAL BETA

| # | Item | Detail |
|---|---|---|
| 1 | ~~Audio-thread file I/O + allocation + locked deep copy in `processBlock`~~ | **FIXED Phase 1.** See `docs/REALTIME_SAFETY_AUDIT.md`. Reconfirmed still present/intact at the start of Phase 2. |
| 2 | ~~HNSW index desyncs from `samples` after `pruneMissingFiles()`, can silently return wrong "find similar" results~~ | **FIXED Phase 1**, with regression test. See `docs/SEARCH_QUALITY_AUDIT.md`. Reconfirmed still present/intact at the start of Phase 2. |
| 3 | ~~Runtime dependencies (TagLib, ONNX Runtime, libsodium) resolved via Homebrew at build time, not bundled~~ | **IMPLEMENTED this session**, locally verified but not yet clean-machine tested. All three dependencies are now dynamically bundled into each plugin format's `Contents/Frameworks/` via a new `cmake/BundleAppleDeps.cmake` `POST_BUILD` step, with binaries rewritten to load them via `@rpath`. Verified by temporarily hiding this machine's Homebrew `/usr/local/opt/{taglib,onnxruntime,libsodium}` paths and confirming the built app still launches and loads ONNX Runtime + CoreML correctly using only the bundled copies — a strong local proxy, not a substitute for the real clean-machine test still required before beta (`docs/HUMAN_COMMERCIAL_REQUIREMENTS.md`). See `docs/RUNTIME_DEPENDENCY_STRATEGY.md`. **A genuine, unrelated use-after-free bug in the async-startup code was found and fixed while doing this work** — see `docs/ASYNC_STARTUP.md`. |
| 4 | JUCE licensing — AGPLv3 vs. commercial license | Unchanged — business decision + cost, not a code fix. See `docs/THIRD_PARTY_LICENSES.md`, `docs/HUMAN_COMMERCIAL_REQUIREMENTS.md`. |
| 5 | No installer exists for either platform | **NOT YET BUILT.** Architecture fully designed this session (`docs/INSTALLER_ARCHITECTURE.md`, `docs/MACOS_RELEASE_PROCESS.md`) — `.pkg` via `pkgbuild`/`productbuild`. Deferred for the same reason as #3: signing/notarization require Apple Developer credentials that don't exist yet (`docs/HUMAN_COMMERCIAL_REQUIREMENTS.md`). |

## P1 — MUST FIX BEFORE PAID RELEASE

| # | Item | Detail |
|---|---|---|
| 1 | ~~Synchronous ONNX + SQLite init blocks DAW project load~~ | **FIXED this session.** `initAsync()` + explicit `EngineInitState` state machine. SQLite open remains synchronous (not a measured problem). See `docs/ASYNC_STARTUP.md` — also documents a real SIGSEGV regression this change introduced and fixed before landing. |
| 2 | ~~"Sort Library" freezes UI on large libraries~~ | **FIXED this session.** Backgrounded via `reorganizeSamplesAsync()`, added a confirmation dialog (didn't exist before), progress display, cancellation. See `docs/SORT_LIBRARY_BACKGROUND.md`. |
| 3 | ~~UMAP 2D layout not persisted — full recompute on every app launch~~ | **FIXED this session.** Persisted `umap_x`/`umap_y` columns, skip-if-unchanged logic, version-based invalidation. Also fixed the documented small-library UMAP internal-error log. See `docs/UMAP_PERSISTENCE.md`. |
| 4 | ~~`getStateInformation`/`setStateInformation` are empty stubs~~ | **FIXED this session.** Versioned `juce::ValueTree` state (search text, naming style), malformed-state-safe. See `docs/PLUGIN_STATE_ARCHITECTURE.md`. |
| 5 | ~~Missing/corrupt ONNX model degrades to filename-hash pseudo-embeddings with no strong user-facing signal~~ | **FIXED this session.** Fake pseudo-embedding generation removed entirely; honest `EmbeddingStatus` (Valid/FailedRetryable/FailedPermanent). See `docs/ONNX_FAILURE_HANDLING.md`. |
| 6 | ~~Mid-batch ONNX exception permanently caches a zero-embedding~~ | **FIXED this session.** Failed embeddings are never cached with a fake value; retryable failures aren't cached at all (natural retry next scan), permanent failures are cached honestly with `embedding_status`. See `docs/ONNX_FAILURE_HANDLING.md`. |
| 7 | Licensing production infrastructure entirely dev/test | **NOT YET BUILT** (deployment work, not architecture) — production architecture now fully specified: `docs/PRODUCTION_LICENSING_ARCHITECTURE.md` (deployment gap analysis, verified against real `server.py`), `docs/LICENSE_KEY_LIFECYCLE.md` (key generation/rotation design). TLS hosting, production keypair, real DB, admin auth, rate limiting still missing — all correctly gated on production hosting credentials. |
| 8 | No payment provider integration anywhere in the repository | **NOT YET BUILT** — provider chosen (`docs/COMMERCE_PROVIDER_DECISION.md`: Paddle, reconfirmed Phase 3), full purchase/webhook/refund/chargeback flow designed (`docs/PAYMENT_FLOW.md`), commerce abstraction interface specified. No live or sandbox integration exists — no Merchant of Record account exists yet (human action). |
| 9 | No customer account/download infrastructure | **NOT YET BUILT** — NITE DSP Account architecture (`docs/NITE_DSP_ACCOUNT_ARCHITECTURE.md`: passwordless auth, session security, minimal account UI) and download/update architecture (`docs/DOWNLOAD_ARCHITECTURE.md`: signed URLs, release immutability, client update-check design) both fully specified this phase. Still not built — correctly deferred to actual implementation once hosting exists. |
| 10 | ~~Memory footprint at scale unverified~~ | **RESOLVED (measured, not just fixed) this session.** Real profiler run across 0/100/500/1,000/5,000(partial) tiers found the ~1.97 GB Phase 1 figure was a mostly-fixed working-set cost (thread pool/ONNX arena/CoreML), not a per-file leak — genuine per-sample retention is ~2-4 KB. See `docs/MEMORY_PROFILE.md`. Caveat: only clean through 1,000 files; 5,000+ needs a longer profiling run. |
| 11 | Windows build/test status entirely unverified | **STILL UNVERIFIED** — this session was also macOS-only. Explicitly documented (not just noted) this session in `docs/WINDOWS_READINESS.md`, including exactly what code paths are unaudited and what's required to change status. |
| 12 | ~~No automated corruption detection for the SQLite cache~~ | **FIXED this session.** `PRAGMA quick_check` on every open, quarantine-and-rebuild on failure, regression-tested (`TestResilience`). See `docs/DATABASE_HARDENING.md`. |
| 13 | ~~No `busy_timeout` for concurrent multi-instance cache writes~~ | **FIXED this session.** `PRAGMA busy_timeout=5000`. See `docs/DATABASE_HARDENING.md`. Note: a dedicated multi-instance concurrent-access regression test was not written (flagged as a further follow-up in that doc). |

## P2 — STRONGLY DESIRABLE

| # | Item |
|---|---|
| 1 | ~~Small (<~5 sample) libraries hit a UMAP internal error~~ — **FIXED this session**, deterministic circle placement below `kMinSamplesForUmapProjection`. See `docs/UMAP_PERSISTENCE.md`. |
| 2 | Residual audio-thread cost in `startPreparedPlayback` (old-reader disposal, `AudioTransportSource::setSource` internals) — bounded, not eliminated. Not touched this session (out of scope for Phase 2's priorities; still low-severity per Phase 1's assessment). |
| 3 | Small race window between prune completing and the forced HNSW rebuild finishing — not touched this session. |
| 4 | Missing `COPYRIGHT`/`COMPANY_WEBSITE`/`COMPANY_EMAIL` plugin metadata fields — addressed in the `docs/NITE_DSP_PRODUCT_IDENTITY.md` proposal (not yet applied to `CMakeLists.txt`, awaiting sign-off). |
| 5 | ~~JUCE `MessageManager` leak warning printed by most test binaries on exit~~ — **FIXED this session**. `deleteInstance()` added before each affected test's exit; verified zero leak warnings across all 11 targets. |
| 6 | No hash-collision fallback verification for duplicate detection (acknowledged non-cryptographic by design; low real-world risk) — not touched. |
| 7 | No size cap on in-memory decode for duplicate-hash computation on very large audio files — not touched. |
| 8 | ~~Multi-instance concurrent SQLite access has no dedicated regression test~~ — **FIXED this session**, new `TestMultiInstance` target: two engines scanning concurrently into the same shared cache DB, no deadlock/corruption/cross-contamination. See `docs/DATABASE_HARDENING.md`. |
| 9 | `reorganizeSamplesAsync()`'s progress/cancel/re-entrancy-guard behavior has no dedicated automated test (the underlying `reorganizeSamples()` logic is covered by `TestPathTraversal`, but the new async wrapper isn't) — still not touched. |

## P3 — POST-LAUNCH

| # | Item |
|---|---|
| 1 | Directory enumeration briefly runs on the message thread before pool dispatch |
| 2 | Each plugin bundle (VST3/AU/Standalone) embeds its own full copy of the ONNX model rather than sharing one location |
| 3 | ~~Corrupt/malformed-audio dedicated test coverage (Phase 15 of the master prompt) not yet present~~ — **FIXED this session**, new `TestMalformedAudio` target covering 4 distinct malformed-WAV cases. See `docs/TEST_COVERAGE_AUDIT.md`. |

## OUT OF SCOPE for this phase

Payment provider selection, Merchant-of-Record decision, live checkout, website copy/design, semantic/text search, and anything touching KENN/Thursday/AutoMix/other sibling projects — all correctly untouched, per `docs/COMMERCIAL_SCOPE.md`.

## Phase 4 update

Items #4 (JUCE licensing) and #5 (installer) are unchanged — both remain business/credential
decisions, not code work. What changed: the commercial infrastructure that #3's dependency
bundling and the whole plugin exist to serve is now real, running, and verified
(`docs/NITE_DSP_BACKEND_IMPLEMENTATION.md`, `docs/STAGING_E2E_RESULTS.md`) rather than only
designed. This doesn't remove any P0/P1 item from this list — every one of them was already
either a code fix (done) or a credential/business blocker (still blocked); Phase 4 didn't touch
the plugin itself at all, by design (`docs/PHASE_4_PLAN.md`'s identity section).

## Phase 5 update

Re-running both suites this phase found and fixed a real, genuine regression: `build-release/`
was stale (predated Phase 2's dependency-bundling `POST_BUILD` step), so all three release
bundle formats (VST3/AU/Standalone) failed `verify_release_manifest.py` -- missing
`Frameworks/*.dylib`, `Resources/THIRD_PARTY_NOTICES.txt`, and (for AU/Standalone) the executable
itself. Rebuilt fresh; all three formats now pass the manifest check again (12 files/vst3, 11/au,
11/standalone, all accounted for). This is exactly the kind of drift the manifest check exists
to catch -- it did.

Two new automated guards added this phase: an identity-drift regression check
(`scripts/verify_identity_manifest.py`, wired into CI) and a config-leak/no-localhost scan of
shipped artifacts (found zero leaks in the release VST3 binary and the website's client bundle).
Item #3's dependency bundling is otherwise unchanged -- still a strong local proxy, still not the
real clean-machine test (`docs/CLEAN_MACHINE_VALIDATION.md`, BLOCKED). #4 and #5 remain
unchanged, still business/credential blockers.

## Phase 5.5 update

**#3 (dependency bundling) materially improved, not just re-verified.** Found and fixed a real
gap this phase: `libonnxruntime.dylib`'s own transitive Homebrew dependencies (~85 abseil/
protobuf/re2 dylibs) were never bundled by the original `cmake/BundleAppleDeps.cmake` -- only
the three top-level libraries were. A customer machine without Homebrew installed would have
failed to load the plugin despite the top-level libs being "bundled." Replaced with
`scripts/bundle_apple_deps.py`, which walks the full transitive dependency graph via `otool -L`.
All three release formats now pass `scripts/check_homebrew_dependencies.py` (new this phase)
with zero forbidden dependency paths across 88-90 Mach-O binaries each. Still not the real
clean-machine test (still BLOCKED, `docs/CLEAN_MACHINE_VALIDATION.md`), but the actual dependency
graph bundled is now correct, which the local proxy test alone never actually verified (it only
hid 3 specific Homebrew package directories, not the ~85 transitive ones).

Identity (#1, implicitly) is now COMPLETE — approved and applied
(`docs/FINAL_PRODUCT_IDENTITY.md`). #4 (JUCE licensing) and #5 (installer, still blocked on
signing) unchanged.

## Phase 6 update

No new code-side blockers found or fixed this phase — the fresh baseline regression reconfirmed
everything Phase 5.6 established, unchanged. One new formally-tracked blocker:
**launch pricing approval** (`docs/HUMAN_COMMERCIAL_REQUIREMENTS.md`'s new item), since Phase
6's Section 38/95 explicitly requires it be tracked rather than silently decided. Phase 6's own
work was website design + documentation, not further backend/plugin engineering — see
`docs/PUBLIC_LAUNCH_CHECKLIST.md` for the consolidated gate list this phase produced.
