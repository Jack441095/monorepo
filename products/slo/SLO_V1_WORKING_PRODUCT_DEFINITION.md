# SLO V1 Working Product Definition

**Purpose:** a concrete, checkable bar for "SLO works properly" as a private-beta product — not an aspiration, a checklist with a pass/fail per item, each backed by the evidence already gathered in `SLO_CURRENT_WORKING_STATE_AUDIT_V1.md` or a specific task report referenced below.

## The bar

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 1 | User can add a folder | **PASS** | `addPathToQueue()`, exercised by every test and this session's real-corpus benchmarks (thousands of real files scanned successfully). |
| 2 | SLO scans supported audio files | **PARTIAL** | WAV: yes, extensively verified. AIFF/FLAC/MP3: **no** — `addPathToQueue()` only discovers `*.wav` (see audit). Real gap, not a documentation error. |
| 3 | SLO extracts useful metadata and audio features | **PASS** | `AudioAnalysisResult` (peak/RMS/crest factor/spectral centroid/rolloff/ZCR/onset count, all real FFT-derived) plus taxonomy-only `AudioFeatures`. Real, not placeholder — see this session's decay-time bug fix, which found and fixed a genuine measurement defect, evidence the pipeline is scrutinized, not just assumed correct. |
| 4 | SLO stores a local durable index | **PASS** | SQLite-backed cache with WAL, version fields (`featureVersion`, `taxonomyVersion`, `embeddingModelVersion`), quarantine-on-corruption handling. See Task 4 report for full schema audit. |
| 5 | User can search by name/type/tag/attribute | **NEEDS UI VERIFICATION** | Backend fields exist (category/subcategory/secondaryTags/predicted tags); whether the UI actually exposes search across all of these is a Task 6 UI audit item, not re-litigated here. |
| 6 | User can filter by category/subtype | **NEEDS UI VERIFICATION** | Same as above — data model supports it, UI audit (Task 6) determines actual exposure. |
| 7 | User can preview audio quickly | **NOT INDEPENDENTLY VERIFIED THIS PASS** | Requires either UI code audit (Task 6) or a live run — see that report. |
| 8 | User can find similar samples | **PASS (backend)** | hnswlib-backed nearest-neighbor search over 512D embeddings, with dedicated tests (`TestFindSimilar`, `TestFindSimilarWeighted`, `TestNearDuplicates`, `TestEmbeddingQuality`, `TestReferenceSearch`, `TestTimbreRefinement`) — see Task 5 report for a fresh pass/fail run of each. |
| 9 | User can drag a sample into Ableton/DAW | **CANNOT BE VERIFIED FROM THIS SESSION** | Requires a live Ableton GUI session — this is exactly B-004 in the existing blocker register, already flagged as blocked on Jack. See `SLO_ABLETON_WORKFLOW_VALIDATION_V1.md` for what *can* be verified statically (file-path preservation logic, no unexpected copy/rename in the drag code path) versus what genuinely can't (the actual drag-and-drop UX in a real DAW). |
| 10 | User can favourite/tag/correct labels locally | **PASS (backend)** | `tagUserOverridden`, `tagSource=="user"`, dedicated `TestFavorites`/`TestHistory` tests exist. |
| 11 | App survives restart and reloads the library index | **PASS** | `TestPersistedCacheHydration`, `TestCacheVersionEnforcement` exist and (per Task 11's fresh run) pass. |
| 12 | App handles missing/moved files gracefully | **PASS** | `TestPruneMissing` exists and passes; version-mismatch and corrupt-cache quarantine logic reviewed in the audit. |
| 13 | App never mutates sample files in read-only mode | **PASS, independently verified with real evidence** | `TestReadOnlySafetyQualification` — real SHA-256 checksums, before/after a real scan of a disposable fixture library, exercising the actual production scan path (not a mock). This is B-013, already closed with evidence, not a claim. |

## What "working properly" means for V1, stated plainly

A private beta tester should be able to: point SLO at a real WAV-based sample library, get a durable, versioned index of it that survives restarts, search and filter by what SLO has classified, get genuinely useful "find similar" results backed by real embeddings, preview instantly, and trust — with actual evidence behind that trust, not a claim — that SLO will never touch their original files unless they explicitly opt into the one feature (Sort Library) that's designed to. Dragging into a DAW and multi-format (AIFF/FLAC/MP3) support are the two honest gaps: the first can't be verified without Jack's Ableton access, the second is a real, scoped engineering gap this program should decide whether to close before beta or explicitly defer.

## Explicit scope decision needed from Jack

**Is WAV-only acceptable for V1 private beta, or is AIFF/FLAC/MP3 support a launch blocker?** This audit found it's a real gap, not a documentation oversight, and closing it touches the decode pipeline (`dr_wav`-specific code), not just a file-discovery filter — a genuine scoped engineering task, not a one-line fix. Given most producer sample libraries are overwhelmingly WAV (per this session's own real-corpus survey of 28,330 real files), this may be an acceptable V1 limitation to document rather than block on — but that's a product-scope call, not an engineering one. Flagged here rather than assumed either way.
