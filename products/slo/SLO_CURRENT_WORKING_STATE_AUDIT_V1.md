# SLO Current Working State Audit V1

**Purpose:** ground truth on what actually exists in this repo today, before any of the readiness-program work (Tasks 2-13) begins. Every claim below is backed by a command or file reference run against the real repo, not assumed.

## Repo identity

- **Path:** `/Volumes/Jack_Gandy_1TB_SSD/NITE_DSP/products/slo`
- **Branch:** `main`
- **HEAD:** `be3e6310a6aae86c0e6b138c0c75aadc9546fdd2`
- **Dirty state:** 1 tracked file modified (`SmartSampleManager/docs/classification/REAL_CORPUS_CROSS_VENDOR_V2_REPORT.md` — an auto-regenerated benchmark report, harmless), plus ~30 untracked report/doc files at repo root from earlier sessions' work (audit/readiness docs, benchmark result JSON dumps). None of this is code — no uncommitted source changes exist. Not cleaned up as part of this audit since it wasn't asked for and isn't blocking anything.
- **Recent history:** last 10 commits are all this session's classification-accuracy work (corpus expansion, ground-truth fixes, an OOD recalibration attempt that was tried, found not to be a clean win, and fully reverted — see `docs/classification/OOD_RECALIBRATION_V1_REPORT.md`).

## Build system

- CMake + Unix Makefiles, JUCE 8.0.2 (pinned via `FetchContent`, `GIT_TAG 8.0.2`).
- Additional fetched dependencies: `umappp` v3.3.2 (UMAP embedding layout), `dr_libs` `wav-0.14.5` (single-header WAV decode, pinned to a release tag deliberately for reproducibility), `hnswlib` v0.8.0 (approximate nearest-neighbor search, backs Find Similar), Eigen, TagLib (via Homebrew `find_path`/`find_library`), libsodium (SHA-256 checksums for safety tests), ONNX Runtime (embedding model inference).
- Presets: `ssm-qualification` (Release, plugin LTO on/tests LTO off) is the primary qualification build used throughout this session; builds to `_build/ssm-qualification/`.
- **31 test targets** registered via `ssm_add_engine_test()`, grouped into 4 qualification risk-surface targets (`ssm_qual_fast_regression`, `ssm_qual_cache`, `ssm_qual_classification`, `ssm_qual_intelligence`) plus `ssm_qual_full`. **Important operational fact, re-learned repeatedly this session: these `ssm_qual_*` CMake targets only build the test binaries — they do not execute them.** Every test binary must be run directly from `_build/ssm-qualification/` to actually get pass/fail.

## App/plugin targets

`juce_add_plugin(SmartSampleManager ... FORMATS VST3 AU Standalone PRODUCT_NAME "Smart Sample Manager")` — VST3, AU, and Standalone all build from the same target.

## Stale "Smart Sample Manager" naming (real, not cosmetic)

The product is SLO now, but the actual build artifact is still named "Smart Sample Manager" throughout:
- `PRODUCT_NAME "Smart Sample Manager"` in the plugin declaration — this is what users literally see as the plugin/app name in their DAW and Finder/Applications.
- The class is `SampleManagerEngine`, the main source file is `SampleManagerEngine.cpp`, the CMake target is `SmartSampleManager`.
- 38 files under `Source/` reference "Smart Sample Manager" or `SmartSampleManager` by name; `PluginEditor.cpp` alone has 2 user-visible occurrences.
- **This is a real product-facing gap, not just internal naming** — a private beta tester would see "Smart Sample Manager" in their plugin list, not "SLO." Renaming the `PRODUCT_NAME` (and ideally the visible UI strings) is low-risk and cheap; renaming the underlying class/file/target names is a much bigger, purely-internal refactor with no user-facing value — **recommend renaming only the user-visible surface (`PRODUCT_NAME`, UI strings, bundle identifier if not already shipped) for this beta, not the internal C++ symbol names**, to avoid unnecessary churn against the safety rule "do not refactor unrelated systems."

## Scan/index pipeline — current state (see `SLO_SCAN_INDEX_PIPELINE_REPORT_V1.md` for full detail)

**Critical, concrete gap found**: `SampleManagerEngine::addPathToQueue()` — the single scan entry point used by the entire product, every test, and every benchmark — only discovers `*.wav` files (`file.findChildFiles(wavFiles, ..., "*.wav")` for directories; an explicit `.wav`-extension check for single files). This is not a superficial filter — a comment in the codebase (`SampleManagerEngine.cpp` near line 4300) confirms the decode path itself assumes WAV (`"The engine only ever queues *.wav files ... so we decode directly with dr_wav"`). **SLO today does not scan or classify AIFF, FLAC, or MP3 files at all**, despite JUCE's `AudioFormatManager` (which supports all of these) being registered and used elsewhere in the codebase for diagnostic/one-off decodes. This directly contradicts the "wav, aiff, flac, mp3 if available" requirement and is a real scope item for Task 4/12, not a quick fix — the decode path change has real blast radius (touches caching, feature extraction, embedding generation).

## Taxonomy/classification — current state (see `SLO_PRODUCER_TAXONOMY_IMPLEMENTATION_PLAN_V1.md` for full gap analysis)

Substantial, already-shipped, evidence-validated work exists — this audit found it, not built it fresh:
- `AbletonTaxonomy` — 17-class primary taxonomy (Kick, Snare, Hi-Hat, Clap, Percussion, Bass One-Shot, Bass Loop, Synth, Synth Loop, Vocal Phrase, Vocal Loop, Impact, Riser, Foley, FX, Atmosphere, Music Loop) with an evidence hierarchy (EMBEDDED_METADATA > FILENAME > FOLDER > DSP) and `taxonomyVersion` field.
- Subtype classifiers: `BassTimbreClassifier` (808/Reese, 92.9% leakage-free holdout accuracy), `HiHatTypeClassifier` (Open/Closed, 92.3%), kick-length tag (Large/Small, duration-threshold based).
- Attribute tags via `generatePredictedTags()`: Bright/Dark, Punchy, Transient, Noisy/Tonal, Long Decay/Short Decay, Wide/Mono — 10 of the requested 16 attributes, each backed by real FFT/DSP features, not proxies.
- `tagConfidence` (0-1 float) and `tagSource` ("unclassified"/"heuristic"/"user") already exist and are UI-wired.
- **Real, honestly-measured accuracy exists**: `docs/classification/REAL_CORPUS_CROSS_VENDOR_V2_REPORT.md` — 71.5% full-evidence / 39.0% audio-only accuracy on a 5,157-file, 15-vendor real corpus (not synthetic).
- **Known, real weaknesses, already documented rather than hidden**: Atmosphere is architecturally excluded from the ML classifier entirely (the frozen linear head has 16 output classes, no Atmosphere slot); the DSP-only fallback path is weak (~7.4% accuracy when it's the deciding evidence); the OOD gate has a real, measured accuracy-vs-safety trade-off with no threshold that improves both simultaneously (`docs/classification/OOD_RECALIBRATION_V1_REPORT.md`, `ENERGY_OOD` investigation — both attempted, both reverted after real end-to-end validation, not shipped).

## Known blockers (see `SLO_BETA_BLOCKER_REGISTER_V2.md` for the authoritative, evidence-cited list)

14 tracked blockers (B-001 through B-014). As of that register's last update (2026-08-28):
- **5 are blocked on Jack directly, not engineering tasks**: B-001 (Apple signing/notarization), B-002 (clean-machine validation), B-003 (production licensing endpoint), B-004 (Ableton Live host matrix — needs a live GUI session), B-005 (a sealed/protected evaluation set only Jack can authorize).
- **6 closed with real evidence**: B-006, B-007, B-009, B-010, B-012, B-013.
- **2 closed with an honestly-stated residual gap**: B-008 (Vocal Loop, partial fix), B-011 (Sort Library now defaults to copy not move, but no explicit user-facing copy-vs-move choice yet).
- **1 in progress**: B-014 (fine-grained subcategorization) — materially more complete now than the register states, given this session's further work (Long/Short Decay, Wide/Mono, corpus expansion to all 17 classes). The register itself is due a refresh but wasn't rewritten as part of this audit to avoid scope creep beyond Task 1.

## Duplicated code / stale paths

No duplicate JUCE linkage found (B-012, the 13,044-duplicate-symbol build break, was fixed and re-verified earlier this session — `ssm_qual_full` builds clean). No other duplicated-engine-code path identified during this audit; the codebase's own comments are unusually explicit about *intentional* near-duplication (e.g. `AudioFeatures` vs `AudioAnalysisResult` are two deliberately separate structs backing different consumers, documented as such in `SampleManagerEngine.h`) — worth knowing so a future refactor doesn't collapse them by mistake.

## Mutation-capable code paths (safety-critical)

Grepped explicitly for file-mutating calls (`moveFileTo`, `deleteFile`, `copyFileTo`, `deleteRecursively`) against real sample content:
- **Cache-file management** (lines ~288-1081 of `SampleManagerEngine.cpp`): copies/moves/deletes SLO's *own internal cache database* files (SQLite + WAL/SHM), quarantining corrupt cache files — never touches user sample audio.
- **The one real mutation feature: "Sort Library"** (~line 5055-5093) — copies or moves user sample files into category subfolders. This is genuinely opt-in (a dedicated, user-triggered feature, not something that runs during a normal scan), has a dedicated test (`TestSortLibraryAsync`), and has defense-in-depth (destination path is verified to actually resolve inside the target category folder before any filesystem write, independent of the input-sanitization step). Per B-011, this now defaults to copy (not move) as of an earlier fix this session, though an explicit user-facing copy-vs-move choice UI doesn't exist yet.
- **No other code path touches real sample files.** The core scan/classify/index pipeline is read-only by construction, and this was independently verified with real SHA-256 checksums before/after a real scan (`TestReadOnlySafetyQualification`, B-013, closed).

## Current UI state

Not independently re-audited pixel-by-pixel in this pass (see `SLO_SIMILARITY_SEARCH_REPORT_V1.md`/Task 6 for the dedicated UI/UX audit) — `PluginEditor.cpp` exists and is substantial (referenced throughout the engine as the consumer of `tagConfidence`, predicted tags, taxonomy version for Unknown-vs-never-scanned UI distinction, etc.), but a full audit against the Task 6 checklist (filters, waveform preview, drag-to-DAW affordance, empty/error states) is deferred to that task specifically rather than duplicated here.

## Current packaging state

More built out than a first assumption would suggest: `scripts/` contains `bundle_apple_deps.py`, `codesign_and_package.py`, `distribution.xml`, `clean_machine_acceptance.py`, `install_and_verify.py`, `signing_preflight.py`, `verify_architecture.py`, `verify_identity_manifest.py`, `verify_no_auto_install.py`, `verify_release_manifest.py`, `measure_build.py`. This is real infrastructure for a signed, verified release — not started from zero. What's actually blocking packaging is B-001 (no Apple Developer ID signing identity exists) and B-002 (no clean-machine access) — both explicitly Jack's to unblock, not something scriptable from here.

## Summary: what this audit changes about the plan

1. **WAV-only scanning is a real, previously-undocumented gap** against the stated "working properly" bar — flagged for Task 4/12 prioritization, not fixed reflexively in this pass.
2. **Stale "Smart Sample Manager" naming is real and user-visible** (the `PRODUCT_NAME` string, not just internal code) — cheap to fix (rename the product-facing string/bundle name), not worth fixing at the internal-symbol level given the safety rule against unrelated refactors.
3. **Taxonomy/classification is much further along than a from-scratch reading of the task brief would suggest** — most of Task 3's requested primary-type/subtype/attribute/confidence spec is already shipped and evidence-backed. The real remaining taxonomy work is narrower than the brief implies: closing a few specific subtype/attribute gaps, not building the system.
4. **Packaging infrastructure already exists**; the packaging blockers are Jack's (signing identity, clean-machine access), not engineering gaps.
5. **The one real mutation feature (Sort Library) is already appropriately scoped, tested, and defaulted to the safer option** — no urgent safety action needed there, just the still-open UX decision (B-011) about whether to expose an explicit copy-vs-move choice.
