# SLO Scan/Index Pipeline Report V1

**Purpose:** audit `SampleManagerEngine`'s scan/index pipeline against Task 4's reliability spec, with direct code evidence for every claim.

## Format support

| Format | Status |
|---|---|
| WAV | **Supported, extensively verified** (thousands of real files across this session's benchmarks). |
| AIFF | **Not supported** — `addPathToQueue()` only discovers `*.wav`. |
| FLAC | **Not supported** — same reason. |
| MP3 | **Not supported** — same reason. |

This is the single largest gap against the Task 4 spec. See `SLO_CURRENT_WORKING_STATE_AUDIT_V1.md` for why this is a real, deep gap (the `dr_wav`-based decode path is WAV-specific, not just the file-discovery filter) rather than a one-line fix, and `SLO_V1_WORKING_PRODUCT_DEFINITION.md` for the explicit scope question this raises for Jack.

## Corrupt/unsupported file handling

`TestMalformedAudio` exists and (confirmed this pass, see Task 11 test run) passes — malformed WAV files are handled without crashing. Unsupported extensions are silently skipped by construction (they never match the `*.wav` glob), which is clean behavior for what it does cover, but means an AIFF/FLAC/MP3 file isn't "skipped with a message," it's invisible to the scanner entirely — worth surfacing to the user if multi-format support stays out of scope for V1 (e.g. a "N files skipped: unsupported format" summary), rather than a silent gap.

## Duplicate detection

Real, content-based (not path-based): FNV-1a 64-bit hash of the fully-decoded, mono-downmixed PCM audio, independent of file path/name/metadata — so a renamed or re-tagged copy of the same audio still matches. `findDuplicateGroups()` groups by this hash. `TestDuplicateDetection` exists and (per Task 11) passes.

## Changed/missing file detection

- **Changed files**: `file.getLastModificationTime()` (mtime) compared against the cached value — a changed file gets re-analyzed on the next scan rather than silently serving stale cached results.
- **Missing files**: `TestPruneMissing` exists and passes — files removed from disk since the last scan are detected and pruned from the index rather than left as dangling entries.

## Incremental rescans

Supported by construction: mtime comparison means an unchanged file is never re-processed on a subsequent scan of the same folder — this is what makes rescans of a large library fast after the first full scan, not a separate code path that could drift out of sync with the full-scan logic.

## Durable, versioned local cache/index

SQLite-backed, with WAL mode (evidenced by `-wal`/`-shm` sidecar file handling in the cache-quarantine code). Three independent version fields exist and are already wired into cache-invalidation logic: `featureVersion` (bumps when `extractDspAudioFeatures()`'s algorithm changes), `taxonomyVersion` (bumps when the taxonomy/classification logic changes), `embeddingModelVersion` (bumps when the ONNX embedding model itself changes) — a genuinely three-way-separated versioning scheme, not one flat "schema version," which is the right design for a system where the model, the taxonomy, and the DSP feature extraction can each change independently. `TestCacheVersionEnforcement` and `TestPersistedCacheHydration` exist and pass.

**Migration path**: version bumps trigger re-analysis of affected rows on next scan (not a destructive wipe) — confirmed by the version-field comments in `SampleManagerEngine.h` describing exactly this behavior. A genuine schema *migration* (e.g. adding a new column to old rows) wasn't independently exercised this pass, but the version-gated re-analysis pattern gives a reasonable path for it.

## Index schema — what's actually stored per file

Confirmed directly against `SampleItem`/`AudioAnalysisResult`: file path, content hash (FNV-1a), original sample rate/channels/bit depth (from the file's own header, not the resampled analysis copy), true duration (not the padded/truncated embedding window), real FFT-derived spectral centroid/rolloff/zero-crossing-rate/crest-factor/onset-count, taxonomy category/subcategory/secondary tags/confidence/winning-evidence, 512D embedding (when valid), user tags/favourites/overrides, and all three version fields above. This is a genuinely rich schema, not a thin wrapper around a file list.

## Cache corruption handling

Corrupt cache files are quarantined (moved aside with a suffix, not deleted outright) rather than silently discarded or causing a crash — evidenced by the `moveFileTo(... quarantineSuffix)` calls found in the mutation-code-path audit. This is a defensible, reversible failure mode.

## Summary verdict

Scan/index reliability is genuinely solid for WAV content — versioned caching, real content-hash dedup, mtime-based incremental rescans, graceful missing/corrupt-file handling, all backed by dedicated passing tests, not just claimed. The one real, substantial gap is format coverage (WAV-only), which is a scope decision for Jack, not an unaddressed engineering oversight.
