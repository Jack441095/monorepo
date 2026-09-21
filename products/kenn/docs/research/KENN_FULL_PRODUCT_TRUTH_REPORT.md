# KENN full product truth report

Audit date: 2026-09-21. Main checkout: `monorepo` at `3667e0e996c976e96110afa32e5e1f5a0163ffc7`, dirty and largely untracked before this audit. Adjacent evidence checkout: `monorepo-collab` at `f4a90d2c603b56f6088d7e0d2c8f2bd7f402c8f1`, also dirty; it was read only. Host: Apple M3, arm64, macOS 27.0, 16 GiB.

## Executive truth

KENN is a substantial offline prototype with a large tested safety layer, not yet a production Ableton coproducer. The canonical backend has 194 non-test Python modules (about 102k source lines), 169 Python test files, a Vue client, a JUCE VST3/AU, an OSC bridge, retrieval, session memory, DSP, typed SLO and AudioGen intake contracts, confirmation-gated mutations, readback receipts, and identity-bound undo paths. In a fresh dependency environment and detached checkout, 1,170 backend tests passed and 121 corpus/model-dependent tests skipped; scoped chat passed 38 tests and explicitly skipped its one approved-corpus integration case; 64 Mix Review tests and both 4-test AutoMix boundaries passed. A fresh frontend install had zero audit findings, passed 5 tests, and built 131 modules. A separate fresh JUCE configure/build passed all 9 Release plug-in tests.

The strongest working path is deterministic command parsing against a supplied Live snapshot, followed by an explicit proposal, expiring confirmation, fresh-precondition check, mutation, readback, receipt and inverse proposal. This is extensively simulated. The real-Live read-only qualification was blocked because AbletonOSC returned offline; therefore no mutation, readback, retry or undo is claimed against Live.

The product is not yet an LLM/GLM coproducer. The release-default experience is primarily deterministic routing plus retrieval/templates. The 111-case intent holdout scored 111/111, but it measures the parser's own bounded vocabulary, not open-ended musical intelligence. Current semantic embeddings are missing, causing explicit BM25-only fallback; the official Live manual has zero indexed chunks. Natural references, cross-turn object identity, arrangement interpretation and producer preference mechanisms exist in pieces, but have no broad end-to-end quality qualification.

## Runtime truth map

| Subsystem | Owner and entry | Actual state | Fallback/failure | Confidence |
|---|---|---|---|---|
| Default local HTTP | main checkout, `run_ux_backend.py` -> `kenn.server.Handler` | Reachable, tested, large `ThreadingHTTPServer` surface | Local-only defaults; many optional handlers return unavailable | High offline |
| Alternate ASGI | main, `kenn.routes.fastapi_app:app` | Reachable but much smaller than default server; not route-parity | Previously wildcard credentialed CORS; repaired to local allowlist | Medium |
| Chat/retrieval | main, `kenn.core.chat` / `chat_answer` | Wired and tested; template path active when LLM disabled | Missing `embeddings.npy` is exposed as machine-readable BM25-only/unavailable status | High for fallback, low for semantic production |
| Scoped chat service | tracked `products/kenn/chat` | Was broken by stale `Audio_Too` path; repaired and 39/39 passed | Explicit retrieval-only scope | High |
| Live intent | main, `core.live_intent.parse_request` | 111/111 deterministic holdout | Clarifies/refuses unsupported requests | High for corpus only |
| Live action loop | main, `core.live_action_service` and specialist services | Confirmation, precondition, idempotency, readback, receipt and undo implemented in simulation | Tokens/proposals are process-bound; restart recovery is fail-closed, not seamless | High simulated; unqualified real Live |
| OSC transport | main KENN bridge + vendored AbletonOSC | Bounded timeouts, circuit breaker, batch reads and exchange diagnostics | Real probe returned offline | Medium offline |
| Plugin | main, JUCE C++20 VST3/AU | Release builds/tests pass; universal artifacts present; direct Live writes disabled | Companion and read-only direct OSC fallback | High host build, no DAW-host proof this pass |
| DSP | main nanobind C++20 + Python reference | Opt-in Accelerate backend built, parity smoke passed, very large analysis speedup | Python remains default and diagnosed | High on this ARM64 host |
| Mix Review | main Python plus opt-in native loudness | 64 tests pass; native result parity exact in synthetic test | Native p50 gain only 1.13x, so no default promotion | Medium |
| AudioGen | KENN contract in main; producer source only in adjacent checkout | Typed bounded MIDI artifact/proposal path exists and is tested | `KENN_AUDIOGEN_ROOT` required; real model/Live insertion not qualified | Medium contract, low production |
| SLO | KENN typed manifest/intake in main; real C++ source in adjacent checkout | Read-only adapter and `kenn.slo_artifact_manifest.v1` validator exist | No production manifest/model handoff in main | Medium contract, blocked production |
| Memory | JSON/SQLite session stores and bounded receipts | Project/session preference features tested | No multi-user isolation/security qualification | Medium local-only |
| Frontend | Vue/Vite in main | Fresh `npm ci`, zero-vulnerability audit, 5/5 Vitest tests and production build pass with bundled arm64 Node | Browser E2E and remote workflow execution remain unqualified | High source/build confidence; medium browser confidence |

## Duplication and ownership

`apps/backend/src/kenn` is documented as canonical. `runtime/legacy/kenn`, `products/kenn/kenn`, and `standalone/apps/backend/src/kenn` are divergent copies, not aliases. The reviewed source is now captured in Git, the compatibility links resolve inside the product, and local migration/reference trees are excluded without deleting the user's local copies. Detached-checkout verification no longer depends on the sibling `Audio_Too` checkout.

AudioGen and SLO ownership must remain explicit. KENN contract changes made here belong to the main checkout. Producer/source evidence under `monorepo-collab/Audio_Too/...` and `monorepo-collab/products/slo/SmartSampleManager/Source` belongs to the adjacent checkout; no adjacent file was changed.

## Fresh evidence

- Backend: `1275 passed, 12 skipped` in 69.25 s after all audit changes.
- Scoped chat: initial import failure, then `39 passed` after repair.
- Mix Review: `64 passed` in 5.62 s.
- Plugin: Release build and 9/9 CTest pass; direct writes OFF; AU and VST3 are arm64+x86_64.
- Realtime plugin benchmark: 64–1024 frame blocks used 0.072%–0.112% of deadline in the isolated meter kernel; concurrent smoke saw no torn/non-finite reads. This was not a TSan build and is not a full plugin callback deadline proof.
- Ableton: deterministic mock passed; real read-only probe blocked with AbletonOSC offline. No real mutation claim.
- Retrieval: session-grounding simulation 6/6, but warned semantic embeddings are absent. Official-manual grounding status: `manual_not_indexed`, zero chunks.
- Native DSP: build hash matched the installed extension; native smoke/parity passed. See the bottleneck report and result JSON.
- Detached hardening checkout: `1170 passed, 121 skipped` backend; scoped chat `38 passed, 1 skipped`; Mix Review `64 passed`; AutoMix `4 + 4 passed`; frontend `npm ci`, zero-vulnerability audit, `5 passed`, and production build passed.

## Changes made

1. Repointed the scoped chat default engine and requirements include from removed `Audio_Too` paths to the canonical backend; added a regression test.
2. Added warmups and truthful build-type metadata to the audio benchmark; added regression assertions.
3. Replaced wildcard credentialed CORS on the alternate FastAPI app with an environment-controlled loopback allowlist; added a regression test.
4. Dropped invalid AudioGen MIDI notes instead of appending them after validation errors.
5. Repaired bounded idempotency pruning so it no longer clears the whole replay-protection window.
6. Made batch undo report partial restoration as failure rather than success.
7. Rejected direct MIDI-create proposals whose notes extend beyond the clip boundary.
8. Made the audio benchmark process exit non-zero when its qualification verdict fails.
9. Added bounded validation to the generative MIDI surface and repaired the frontend groove/bassline HTTP signature drift.
10. Rejected ambiguous same-address OSC batch replies instead of assigning by arrival order; mutation/topology snapshots now force refresh.
11. Bounded OSC packet size, bundle depth and element count; confirmation replay tracking now fails closed at capacity.
12. Treated client disconnects during HTTP body/stream writes as normal connection closure instead of uncaught server-thread errors.
13. Captured the canonical product boundary, repaired internal compatibility links, and proved fresh-checkout Python, frontend, native-kernel, and JUCE builds.
14. Added core and native CI definitions, upgraded the frontend test runner to remove audit findings, and made retrieval mode/fallback visible through health diagnostics.

## Independent audit addendum 2026-09-21 (second pass, no commits)

- Backend suite after fixes: `1271 passed, 5 skipped` in ~80 s (`python3 -m pytest src/kenn/tests -q -p no:cacheprovider` from `products/kenn/apps/backend`).
- Fixed 4 safety defects, all with regression tests in `src/kenn/tests/test_audit_p0_regressions.py` + updated `test_idempotency_bounds.py`: invalid-MIDI leak in `audiogen_artifacts._canonical_midi_notes` (KENN-020), idempotency `clear()` wiping replay protection (KENN-021), `undo_batch_action` ok-on-partial (KENN-022), `propose_create` missing clip-bound check (KENN-023). The benchmark exit-code fix is KENN-028.
- The destructive natural-language boundary remains intentionally open for design/qualification (KENN-024). KENN-025 through KENN-027 were repaired with offline regressions; KENN-026 still requires real-Live transport qualification under KENN-002.
- Fresh measurements: `live_intent.parse_request` p50 0.061 ms; native `analyze_wav` 6.9 ms vs Python 400 ms (58x) with 440 Hz peak agreement; machine JSON in `results/kenn_audit_benchmarks_2026-09-21.json`.
- New reports: `CPP_PLATFORM_AND_LIBRARY_RESEARCH.md`, `CPP_MIGRATION_OPPORTUNITY_MATRIX.md`, `CPP_SHARED_RUNTIME_ARCHITECTURE.md` (defer split), `KENN_TARGET_COPRODUCER_ARCHITECTURE.md`, `KENN_EXECUTION_ROADMAP.md`, `KENN_REMAINING_BLOCKERS.md`.

Local descriptive verification commits were created. Because older local-only history contains prohibited attribution trailers, that history will not be published; the reviewed tree is published from `origin/main` as a clean squashed review commit after metadata validation.
