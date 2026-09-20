# SLO Eval Priorities (Merged) — 2026-09-18
Combining Phases 1–4. Areas: check / feature / ai / perf. Next actions: EXECUTE / PROPOSE / DECIDE (DECIDE = Jack's call, spec-frozen or product decision).

| Rank | ID | Area | Title | Sev | Impact | Effort | Grade | Next action |
|---|---|---|---|---|---|---|---|---|
| 1 | B-001/2/3/4/5 | check | Apple Developer ID / clean-machine / prod licensing / Ableton matrix / blind AL-002 review | P0–P1 | Ship-blocking | — | B | **DECIDE (Jack)** — already tracked in Beta Blocker Register V2; not engineering tasks |
| 2 | P-01 | perf | RSS shaping: ONNX arena trim + CoreML cache + mmap audit (2.19 GB @10k) | P1 | Big-library DAW coexistence | M | **A (fresh)** | **Data delivered:** batch-16 = −45% RSS / +64% scan time (DECIDE, env knob exists); arena-disable probe = NULL RESULT, reverted. Remaining: streaming decode. |
| 3 | F-01 | feature | Multi-format support (FLAC first, then AIFF/MP3) | P1 | Largest reach win | L | B | **DECIDE scope** → EXECUTE MVP (FLAC discovery+decode, featureVersion bump, extended TestFormatAwareScan) |
| 4 | A-01 | ai | Energy-based OOD signal (end-to-end validated) | P1 | OOD false-known 41.6–72% → target <30% | S | **A (fresh)** | **EXECUTED 2026-09-19 → KILLED (no lift):** `analysis_ood_energy_v1.py`, 60-known/39-OOD fresh scans, energy AUROC 0.56 vs centroid 0.50 on a boundary set where the ship gate itself scores 0.50 (vs 0.911 V4-G holdout). Gate untouched. |
| 5 | F-02/A-02 | feature/ai | Graduated-confidence bundle + per-class confidence instrumentation | P1 | Trustworthy ambiguous-content UX | S/M | B | PROPOSE (no model work) |
| 6 | A-04/A-05 | ai | Correction→eval harness + opt-in embedding capture | P1 | Closes the only proven accuracy lever | S/M | B | PROPOSE (CorrectionLog plumbing exists) |
| 7 | F-05 | feature | "N files skipped: unsupported format" summary | P2 | Honesty, cheap | S | B | **ALREADY SHIPPED** — `PluginEditor.cpp:26–49,1167–1168,1406–1418`, engine `SampleManagerEngine.h:746–766`, diagnostics `SampleManagerEngine.cpp:2487`; roadmap corrected post-verification |
| 8 | F-04 | feature | Combined similarity + taxonomy/attribute query UX | P2 | Creative-search value already built | S/M | B | PROPOSE (needs live UI pass) |
| 9 | F-03 | feature | Correction-loop user visibility ("you corrected X") | P2 | Engagement + data inflow | M | B | PROPOSE — engine rescan-diff receipt already exists (`SampleManagerEngine.h:743`); remaining work is user-facing loop closure |
| 10 | P-02 | perf | Streaming/segmented decode for scan RSS on long files | P2 | Scan memory on real libraries | M/L | B | PROPOSE (hash-stability gate required) |
| 11 | A-03 | ai | int8 quantisation (parity-gated) | P2 | RSS/size win, CoreML unaffected | M | B | PROPOSE |
| 12 | F-06 | feature | Library analytics dashboard | P2 | Producer value | M | B | PROPOSE |
| 13 | F-07 | feature | Taxonomy expansion decision packet | P2 | Long-term coverage | M | B | DECIDE (needs beta usage data) |
| 14 | A-06 | ai | CI accuracy+latency regression gate | P2 | Prevents the stale-metrics class of drift | M | B | PROPOSE |
| 15 | P-03 | perf | Session lazy-load/warm-up audit | P3 | Startup polish | S | B | PROPOSE |
| 16 | A-07 | ai | HNSW ef/M sweep tool | P3 | Marginal (already sub-ms) | S | B | PROPOSE |
| 17 | F-08 | feature | Non-Ableton export (CSV/NML/Logic) | P3 | Broadens DAW reach | S/M | B | PROPOSE |
| 18 | A-08 | ai | Local LLM (Ollama) explainer + NL filters | P3 | Nice-to-have UX | M | B | PROPOSE (off by default) |
| 19 | A-09 | ai | CLAP bake-off | P3 | Deprioritised (9-encoder graveyard) | L | B | PROPOSE (research-only, strict kill criterion) |

**Notes:** No P0 engineering defects found in privacy/safety/RT. The stale-metrics honesty issue is handled by the repo's own supersession discipline; A-06 makes it structural.
