# SLO Evaluation Scorecard — 2026-09-18
**Method:** read-mostly evaluation per `SLO_EVALUATION_FEATURES_AI_PERF_PROMPT_V1.md` §2. No builds/tests run; no edits on main. Grades: A=ran it, B=read code, C=partial, D=claimed-only, E=contradicted, F=unknown. All accuracy/perf numbers are repository-held historical evidence unless marked fresh.

## Verdict
**NEEDS WORK** — biggest single risk: **cross-vendor classification accuracy (30.2% audio-only / 62.9% full-evidence honest measured) combined with 41.6–72% OOD false-known**, against a product whose engineering, safety and performance discipline is otherwise genuinely strong. Read-only beta posture is correct and well-evidenced.

## Scorecard
| Area | Score | Grade | Top gap (evidence) |
|---|---|---|---|
| Discovery & scan | 6/10 | B | WAV-only discovery+decode; AIFF/FLAC/MP3 invisible (SLO_SCAN_INDEX_PIPELINE_REPORT_V1: `addPathToQueue()` globs `*.wav`; decode path is dr_wav-specific) |
| Classification quality | 5/10 | B/D | Synthetic 96.5% headline self-declared stale (`slo_classification_metrics_v1.json`: "REPOSITORY_HELD_HISTORICAL_NOT_FRESH"); honest cross-vendor 62.9% full / 30.2% audio-only (B-006 CLOSED reporting); golden-set audio-only 5.9% |
| Fusion & decision gates | 7/10 | B | Fusion lift real (71.5% vs 39.0%, V2 5,157-file benchmark, SLO_ACCURACY_ROADMAP_V1); but lift is filename-dominated (81.2%/77.9% when filename/folder wins) — DSP-only is the bottleneck; Stage-2 recalibration null result fully reverted, byte-identical |
| Similarity search | 8/10 | B | Best-evidenced area: TestFindSimilar/Weighted/NearDuplicates/EmbeddingQuality/TimeoutTimbre/ReferenceSearch 6/6 PASS on real decode→inference chain (SLO_SIMILARITY_SEARCH_REPORT_V1); combined similarity+filter query UX unexercised |
| UX & presentation | 6/10 | B | CorrectionLog.h exists (append-only JSONL, no-audio, captures original before overwrite); graduated-confidence bundle (category+subtype+attributes) missing — flagged in SLO_PRODUCER_TAXONOMY_REQUIREMENTS_V1; never-scanned vs Unknown text fix landed (B-007) |
| Robustness & safety | 9/10 | B | Read-only scan SHA-256-qualified (B-013, TestReadOnlySafetyQualification); sort move/copy/undo journal + cancellation (B-011); cache corrupt→quarantine; 3-way version gates (feature/taxonomy/embeddingModel); TestMalformedAudio PASS |
| Realtime safety | 9/10 | B | TestRtDeadlineStress: 0/2000 misses, 0 allocations; max callback 0.127 ms after BufferingAudioReader + atomics pass (RT audit 2026-09-16 update); B-004 real-DAW validation still open (Jack-blocked) |
| Performance | 7/10 | B | 7× per-file gain landed (222–236 → 25.5–28.6 ms/file Release @500, BATCH_SIZE_SWEEP + SCALE_TIER_RESULTS); 10k cold 292.9 s, rescan ~30 µs/file, search p99 0.11–0.15 ms; RSS 2.19 GB @10k (1.4 GB fixed + 70–90 KB/file marginal) |
| Code health | 7/10 | B | Working tree clean for SLO (only sibling `kenn/` files modified); 31 test/benchmark executables; SampleManagerEngine.cpp at 7,407 lines is the main debt concentration |
| Docs truth | 8/10 | B | Rare honesty culture: perf report self-supersedes with "do not quote 170-file numbers"; metrics JSONs self-declare staleness; every blocker register row carries evidence citations |
| **Overall** | **6.8/10** | — | **NEEDS WORK** |

## Per-area notes (compressed)
1. **Discovery/scan:** reliability excellent (content-hash dedup, mtime incremental, prune-missing, WAL cache) — reach is the gap, not robustness. Unsupported formats are silently invisible; "N skipped" summary is a cheap honest fix.
2. **Classification:** the 96.5% figure must never be quoted externally (self-declared stale, synthetic, single-vendor). Honest numbers: 62.9% full-evidence / 30.2% audio-only / 72.0% OOD false-known cross-vendor. Taxonomy is 16-class head / 17-class taxonomy; guitar/orchestral/world/spoken-word have no home (architectural, per roadmap §Why-100%-is-wrong).
3. **Fusion:** class-conditional gates + filename/folder evidence are the ship story; OOD gate recalibration is spec-frozen pending Jack authorization (B-007).
4. **Search:** hnswlib 0.8.0 + umappp 3.3.2, real and tested; open item is combined-query UX only.
5. **UX:** correction capture exists; the loop (log → eval → model impact) does not yet close.
6. **Safety:** best-in-class for this product stage. Nothing found that violates read-only or RT guarantees.
7. **Performance:** the naive wins (batching, graph opt, CoreML, intra-op threads, incremental rescan, WAL) are all already implemented and measured. Remaining candidates are memory-shaping, not speed.
8. **Docs:** B-014 shows the right pattern for in-progress work (evidence-gated, no imported decisions).
