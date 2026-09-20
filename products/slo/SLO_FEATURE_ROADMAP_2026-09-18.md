# SLO Feature Roadmap — 2026-09-18 (PROPOSALS ONLY — nothing implemented)
Ranked by `(user value × confidence in lift) / effort`, grounded in Phase 1 evidence. Cut: anything already shipped.

## Already shipped (do NOT re-propose) — verified this pass
Favorites/history/user-tags/overrides (SQLite), duplicate detection (FNV-1a content hash), Find Similar + near-duplicates + weighted/timbre refinement, Smart Collections panel, Sort Library with preview/copy/move/undo/cancellation, Ableton XMP writer, bass-timbre subtype tag (92.9% holdout, B-014), acoustic tempo estimator v5 (experimental), key/BPM/energy/decay DSP features.

## Correction to the original ranking (post-execution verification)
- **F-05 "N files skipped" summary: ALREADY SHIPPED.** `PluginEditor.cpp:26–49` (`formatScanReceipt`/`formatScanReceiptLong` → "N skipped (non-audio)" status line + Scan Complete alert), `PluginEditor.cpp:1167–1168` (UI-side drops credited via `noteSkippedDrops`), engine `ScanReceipt.skippedNonAudio` (`SampleManagerEngine.h:746–766`), diagnostics bundle exports `skipped_non_audio` (`SampleManagerEngine.cpp:2487`). No action needed.
- The engine also already has a rescan-diff receipt (`added/changed/failed`, "F-03 rescan-diff receipt" per `SampleManagerEngine.h:743`) — richer than assumed when ranking.

## Ranked proposals
| # | ID | Feature | User story | Why now (evidence) | Effort | Risk | Depends on |
|---|---|---|---|---|---|---|---|
| 1 | F-01 | **Multi-format support (AIFF/FLAC/MP3/OGG)** | "I drop my actual sample library in and nothing happens" — every non-WAV producer | SLO_SCAN_INDEX_PIPELINE_REPORT_V1: discovery globs `*.wav` AND decode is dr_wav-specific — deep gap, not a glob fix; largest reach win | L | Med (decode + resample + hash paths all format-aware; TagLib already present) | Format-scope decision (V1 definition) |
| 2 | F-02 | **Graduated-confidence result bundle** | "Show me what it knows and how sure it is" instead of guess-or-Unknown binary | SLO_ACCURACY_ROADMAP_V1 Stage 3: signals mostly exist; UX gap flagged in SLO_PRODUCER_TAXONOMY_REQUIREMENTS_V1; no model work needed | S/M | Low | Per-class confidence instrumentation (A-02) |
| 3 | F-03 | **Correction-loop closure** | "I fix a tag, the app gets smarter — and I can see it" | CorrectionLog.h captures corrections (no-audio JSONL) but nothing consumes them; by-ear labels = only proven +3.29pp/500 intervention | M | Low (eval-only first step) | A-04 eval harness |
| 4 | F-04 | **Combined query UX (similarity + taxonomy/attribute filters)** | "Show me darker impacts, shorter versions" | SLO_SIMILARITY_SEARCH_REPORT_V1: backend pieces tested separately, never together; needs running UI pass | S/M | Low | None |
| 5 | F-05 | **"N files skipped: unsupported format" scan summary** | "Why didn't my AIFFs show up?" — honesty instead of silence | Scan/index report flags silent invisibility as the cheap fix while F-01 is scoped | S | Very low | None |
| 6 | F-06 | **Library analytics dashboard** | "What's in my library? where are my gaps?" | Rich per-file schema already stored (centroid/rolloff/onsets/tags/classes) — read-only aggregation | M | Low | None |
| 7 | F-07 | **Taxonomy expansion decision packet** | "Guitar/orchestral/world samples get real homes" | Roadmap Stage 4: product decision, needs usage data; 16-class head has no room — architectural | M (packet) / L (impl) | Med | Usage data from beta |
| 8 | F-08 | **Non-Ableton interop export (CSV/NML/Logic tags)** | "Use SLO's tags in Logic/Bitwig/Reaper" | AbletonXmpWriter proves the write path; other DAWs are format mapping only | S/M | Low | None |

## Do next
**F-05 + F-02** (small, model-untouching, immediately honest) while **F-01 is scoped** as the single biggest reach decision. F-01 MVP slice: FLAC discovery + decode only (most common non-WAV lossless; libFLAC or JUCE AudioFormatReader), behind a format-aware featureVersion bump, with TestFormatAwareScan extended — success test: 100-file mixed FLAC/WAV fixture scans, hashes, classifies, rescans incrementally at cache-hit speed.
