# SLO Next-Level Executive Summary — 2026-09-17

> Read-only audit. No source modified, no installs, no pushes. Canonical source verified as `Nite-DSP-Operations/monorepo/products/slo/` (repo `github.com/Nite-DSP/slo`, branch `main` @ `dc855be`), product code in `SmartSampleManager/` (no nested `.git`). Full evidence in sibling files.

## 1. Estate in one paragraph
SLO (Smart Sample Manager → SLO, `SmartSampleManager/CMakeLists.txt:476-493`, JUCE 8.0.2, C++20, arm64-only) is a real, working, WAV-scoped AI sample organizer: dr_wav → 32 kHz/160k-sample mono → PANNs CNN10 ONNX 512-D (`Models/panns_cnn10_embedding.onnx` + 24 MB `.data`) + 8 DSP dims → frozen 16-class ArcFace/linear head (`Source/AcousticClassifier.h:112`, `AcousticClassifierWeights.h:1`) + per-class nearest-centroid OOD gate (`AcousticClassifierCentroids.h:1`, e.g. FX threshold 0.8303564) → SQLite WAL cache (`SampleManagerEngine.cpp:1197,1254`) + HNSW 0.8.0 / UMAP 3.3.2 → JUCE AU/VST3/Standalone UI. ~113 Source files, ~55 test mains + ~20 executables via helpers, 122 docs files, 1619 fixtures, 38k files under `tools/` (benchmark outputs). Safety story is genuinely qualified (`TestReadOnlySafetyQualification` PASS, SHA-256 4/4 unchanged); RT path is sound-by-design with instrumented proof (0/2000 misses, 0 allocs, max 1.085→0.127 ms). The blocker to "next level" is NOT plumbing — it is **classification truth**: 96.5% benchmark accuracy collapses to 62.9% full / 30.2% audio-only on leakage-controlled cross-vendor corpus (B-006), OOD false-known 72% cross-vendor (B-007), Vocal Loop recall 7.5%, Bass/Synth Loop F1 0. CLAP+DSP beats PANNs+DSP +8.34pp/+9.29pp (73.86→82.20% acc) but is explicitly NOT beta-approved (744 MB, no C++ path, no OOD/license/latency work).

## 2. Product verdict
**HARDEN + CONTINUE RESEARCH — do not ship paid beta, do not swap encoder yet.** Verdict table:

| Product | Stage | Verdict | Score* |
|---|---|---|---|
| SLO classifier + app | Alpha (strong internals, unproven generalization) | HARDEN | 29/50 |

*D1 2, D2 3, D3 4, D4 3, D5 3, D6 3, D7 3, D8 1, D9 3, D10 4. Commercial/readiness (D8) and truth-alignment (D1) cap the score.

## 3. Top-10 risks (P0/P1 first)
1. P1 | Accuracy headline misuse — 96.5% leaky vs 30.2% audio-only vs 57% collection-held-out. Any external claim without split label is false. (`slo_classification_metrics_v1.json`, `SLO_CLASS_BY_CLASS_REPORT_V1.md`)
2. P1 | OOD false-known 72% cross-vendor (B-007) → silent mistags if auto-anything. Gate holds only because UI shows UNKNOWN + no auto-move.
3. P1 | Vocal Loop 0/22 cross-vendor, 7.5% recall; Bass/Synth Loop F1 0 — loop taxonomy broken for paid producer use. (`SLO_BETA_BLOCKER_REGISTER_V2.md` B-008 residual)
4. P1 | WAV-only discovery (`addPathToQueue` `*.wav`; `SampleManagerEngine.cpp:3348` dr_wav path). AIFF/FLAC/MP3 invisible with no message. Scope decision, but Ableton users will hit it day one.
5. P1 | 5 Jack-blocked beta gates open: B-001 signing, B-002 clean-mac, B-003 licensing HTTPS, B-004 Ableton matrix, B-005 blind AL-002. No revenue until closed.
6. P2 | B-014 fine-subcat half-done: bass timbre 92.9% leakage-free but 5 classes metadata-gated, 5 hash conflicts, CLAP advisory unmerged.
7. P2 | Perf evidence stale-split: 170-file 2.4 GB peak report (`SLO_PERFORMANCE_REPORT_V1.md`) vs B-009 100/1k/10k+soak clean — need single regenerated perf receipt before large-library claims.
8. P2 | `SampleManagerEngine.cpp/.h` ~4.9k-line TU god-object; prepareFile/decode/classify/cache/HNSW all coupled. Slows every future head/encoder change.
9. P2 | Dirty `slo` working tree (413 modified/untracked per `git status`) + 33 in monorepo — clean-release reproducibility at risk; immutable Release qual still required.
10. P2 | Licensing server ships `licensing.db` + `keys/` in tree; dev localhost HTTP only (B-003). Path refs only — needs secrets/ignore audit before distribution.

## 4. Top-10 opportunities (RICE in backlog file)
1. UNKNOWN review queue + confidence display (RICE 18.0) — turns weakest metric into UX trust.
2. Audio-only vs fused split reporting in UI (12.8) — ends the 96%-vs-30% confusion permanently.
3. Rescan-diff + prune messaging (12.0) — makes incremental story visible.
4. Filename-fusion v2 with adversarial audit (9.6) — keep 62.9% fusion win without 0%-adversarial collapse.
5. Taxonomy v2: loop/one-shot repair + multi-label (8.0) — fixes the 0-F1 loops.
6. "Find more like this" combined query (7.5) — similarity backend already 6/6 PASS, UX missing.
7. CLAP hybrid promotion track (gated, 6.0) — +8pp proven, needs C++/size/OOD/license gates.
8. Model registry + OTA invalidation via `embedding_model_version`/`classification_model_version` (6.0) — already schema-ready.
9. Correction-log training flywheel (5.3) — `CorrectionLog.h` append-only log exists, unused for training.
10. Format expansion AIFF/FLAC (4.8, scoped) — biggest reach unlock after accuracy.

## 5. The single most important decision this month
**Freeze PANNs+DSP for any beta; authorize the CLAP promotion gate list (C++ path + size budget + OOD recal + license + vendor-held-out + latency/memory) as a post-beta track — or kill CLAP now and invest the same budget in taxonomy+OOD on PANNs.** Per `SLO_ENCODER_RESEARCH_DECISION_2026-09-15.md`, the +8.34pp is real but row-stratified/leaky and unshippable at 744 MB with no prod path. Half-funding both tracks guarantees neither ships.
