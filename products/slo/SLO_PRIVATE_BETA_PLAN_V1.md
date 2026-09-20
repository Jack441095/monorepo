# SLO Private Beta Plan V1

**SLO** (formerly Smart Sample Manager — treated as the current name throughout this and future SLO docs). Local-first sample organisation, classification, search, and discovery for producers and audio engineers.

**Strategic position, unchanged**: Submit remains the active commercial launch lane. This document does not touch Submit, platform payment rails, Railway staging, Paddle, or licensing, and does not propose a public or paid launch for SLO. SLO stays parked behind Submit — this plan prepares it for a **future** private beta, it does not schedule one.

## 1. Current state (audit)

- **Repo**: `products/slo` (git submodule), branch `main`, up to date with `origin/main` as of this document (pushed through commit `28148c0` and this session's follow-on work).
- **Build**: clean. `ssm_qual_full` verified multiple times this session — zero duplicate-symbol errors, all plugin formats (VST3/AU/Standalone) build.
- **Naming**: canonical product name is now **SLO**; the CMake target/binary/bundle name (`SmartSampleManager`) is still the historical internal name. **Not renamed in this pass** — a rename touches build output paths, bundle IDs, and possibly signing identity later; flagged as a decision for Jack, not done unilaterally given B-001 (signing) isn't even started yet and a name-then-sign-once approach avoids redoing signing work.
- **Dependency status**: JUCE 8.0.2, ONNX Runtime, TagLib, libsodium, SQLite3 — all resolving cleanly via FetchContent, no known dependency issues.
- **Test inventory**: ~30+ `Test*`/`Benchmark*` targets across `ssm_qual_fast_regression`, `ssm_qual_cache`, `ssm_qual_classification`, `ssm_qual_intelligence`, `ssm_qual_ui` groups, all passing as of the last full qualification run.
- **Packaging state**: unsigned, ad-hoc only. No notarization. No installer. (B-001, blocked on Jack.)
- **Classification pipeline**: production linear head + per-class OOD threshold, spec-frozen. Real cross-vendor accuracy now measured and honestly reported (62.9%/30.2% full-evidence/audio-only). See `SLO_BETA_BLOCKER_REGISTER_V2.md`.
- **UI state**: functional (Standalone/VST3/AU all build and bundle). Not independently UX-audited in this pass — no live GUI-driving tool available from this session; see §6 for what that gap means for the beta gate.
- **Local database/index state**: SQLite-backed cache with `taxonomyVersion`/`featureVersion`/`embeddingVersion` fields already present and exercised (confirmed via code review and the read-only safety test). See `SLO_PRODUCER_TAXONOMY_REQUIREMENTS_V1.md` §Versioning for what's still missing.
- **Stale naming**: "Smart Sample Manager" still appears in build artifact paths, bundle names, and some doc titles. Cosmetic, not a functional blocker — a rename pass is a separate, low-risk task if wanted before beta.

## 2. Beta blockers

See `SLO_BETA_BLOCKER_REGISTER_V2.md` — the current source of truth. Summary: 6 items closed with real evidence this session, 2 closed-with-honestly-stated-residual-gap, 5 blocked on Jack directly, 1 (fine-grained taxonomy) in progress with methodology proven.

## 3. Read-only safety

See `SLO_READ_ONLY_SAFETY_QUALIFICATION_V1.md`. Headline: the automatic scan/classify path (the one that runs with no per-file consent prompt) has **zero source-file-mutating code** anywhere in it — verified by reading every `copyFileTo`/`moveFileTo`/`deleteFile` call site in the engine (all of them are either the engine's own cache-database management, or inside the already-consent-gated, copy-by-default Sort Library feature). This claim is now backed by a real, automated test with SHA-256 checksums, not just code review — see that doc for the receipt.

## 4. Classification and taxonomy

See `SLO_PRODUCER_TAXONOMY_REQUIREMENTS_V1.md` for the full four-layer design (primary type / subtype / attributes / confidence) and honest status of each layer. Headline: one real subtype shipped (808/Reese bass, 92.9% leakage-free holdout accuracy), a proven evidence-gated methodology for adding more, and a clear map of what's cheap vs. what needs new DSP feature work vs. what's a product decision for Jack.

## 5. Similarity and search readiness

- **Feature extraction / embeddings**: 512D PANNs embeddings, computed once per file, cached. Proven separative power reused across this session's work (OOD gate AUROC 0.911, bass timbre 92.9% holdout, golden-set 98.8% LOO).
- **Similarity search**: existing `TestFindSimilar`/`TestFindSimilarWeighted` targets pass in `ssm_qual_intelligence`. Not independently re-verified with new evidence this session — reusing existing test coverage as the current state of truth.
- **Duplicate/near-duplicate detection**: `TestDuplicateDetection`/`TestNearDuplicates` pass. Uses a separate, metadata-independent content hash (distinct from the SHA-256 file-integrity checksums used for safety qualification — see §3).
- **Performance at scale**: see §7 — real 100/1k/10k-file receipts already exist from B-009.
- **Rescan behaviour**: `taxonomyVersion`/`featureVersion` gate recomputation on cached rows; exercised by `TestCacheVersionEnforcement`/`TestPersistedCacheHydration`, both passing.

**Not independently re-verified in this pass**: this section reuses existing test results rather than re-running them, since nothing in this session's work touched the similarity/search code paths.

## 6. UI/UX beta requirements

**Not independently verified — flagged as a real gap, not silently assumed fine.** This session has no way to drive the actual GUI (no screen/interaction tool available), so claims about "feels useful immediately," empty states, error states, etc. cannot be honestly verified from here. What's confirmed: the app builds and bundles in all three formats, and specific UI logic (the Unknown/not-yet-classified distinction fixed in B-007, the Sort Library confirmation dialog text from B-011) was verified by direct code reading. **Recommendation**: before beta, someone needs to actually launch the built Standalone/VST3/AU and click through scan → results → search → filters → preview once, live. This is real, necessary work this session cannot do.

## 7. Performance qualification

Real, existing evidence from `NITE_DSP_SLO_MASTER_PLAN_V1.md` Phase 3 (B-009) and V2 Phase 8 (B-010):

| Metric | Result |
|---|---|
| Scan time (100 files) | cold 11.6s, cached 0.65s |
| Scan time (1k files) | cold 92.0s, cached 8.5s |
| Scan time (10k files) | cold 797.5s (~13.3min), cached 83.5s |
| Peak RSS (100/1k/10k) | 2.69GB / 3.02GB / 4.21GB (sub-linear — mostly fixed ONNX-runtime overhead) |
| Soak (30 repeated scans) | flat after warm-up, no leak |
| processBlock deadline misses | 0/2000 |
| processBlock allocations | 0/2000 tracked callbacks |

**Not measured** (needs a live app session, not scriptable from here): preview playback latency specifically, index load time on app restart, crash recovery behavior. Flagged, not fabricated.

## 8. Packaging and distribution plan (private beta only)

- Exact build SHA: capture at freeze time (not frozen yet — no beta candidate has been cut).
- Version number: needs a decision (SLO has no version scheme yet, unlike Submit's `0.2.0`).
- Artifact checksum: the same `juce::SHA256` pattern already proven in this session's read-only safety test can produce this trivially once a candidate build exists.
- Release receipt, install instructions, known issues, rollback instructions, tester feedback form: **not yet written** — templates exist for Submit (`NITE_DSP_SUBMIT_BETA_LAUNCH_CHECKLIST_V1.md`'s tester-pack step) that SLO's version should follow rather than reinvent.
- Explicitly: no public release, no paid claims, matching every instruction this plan was written under.

## 9. Infrastructure plan

See `SLO_INFRASTRUCTURE_REQUIREMENTS_V1.md`. Headline: SLO is already local-first with no network calls in its scan/classify path (verified by direct code search, zero hits for URL/HTTP/socket code) — the privacy story for a beta is inherently strong. Everything else (entitlement, signed downloads, update channel, telemetry) is explicitly deferred past beta.

## 10. Beta gate

See `SLO_PRIVATE_BETA_READINESS_RECEIPT_V1.json` for the structured, per-area verdict. Narrative summary:

**READY ONLY AFTER SPECIFIC BLOCKERS.**

- **Engineering verdict**: strong. Build clean, tests passing, real performance/safety/RT evidence exists.
- **Safety verdict**: PASS, with real evidence (checksummed fixture test, code-reviewed absence of network calls).
- **Classification verdict**: PARTIAL. Honest accuracy numbers exist (better than before this session, still modest by absolute standard: 30.2% audio-only). One real fine-grained subtype shipped; the rest of the requested taxonomy breadth is still a multi-session build-out.
- **Packaging verdict**: NOT READY. No frozen build, no version scheme, no signing (B-001 blocked on Jack).
- **UX verdict**: UNVERIFIED. Needs a real, live click-through this session cannot perform.
- **Infrastructure verdict**: fine for beta as scoped (local-first, no network dependency) — nothing blocking specifically for a beta at this stage.
- **Owner approval required** for: naming the private-beta tester cohort, deciding the SLO/Smart-Sample-Manager rename question, Apple Developer ID enrollment start, and — separately, most importantly — **authorizing whether to reopen the spec-frozen OOD threshold recalibration**, since that's the single highest-leverage remaining accuracy lever and this session has deliberately not touched it without sign-off.
