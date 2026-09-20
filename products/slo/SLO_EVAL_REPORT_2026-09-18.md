# SLO Evaluation Report — 2026-09-18
**Prompt executed:** `SLO_EVALUATION_FEATURES_AI_PERF_PROMPT_V1.md` · **Mode:** read-mostly (Phase 1 + proposals; no code edits anywhere, incl. no branch — Phase 4 EXECUTE declined, see §Perf) · **Commit:** `1102468` (ops/mirror-and-notes; SLO subtree clean; unrelated `kenn/` modifications pre-existing)

## Summary
SLO is an unusually honest, well-evidenced codebase with strong safety/RT/scale receipts — but its headline classification numbers are synthetic-era, its honest cross-vendor accuracy is 62.9% (full-evidence) / 30.2% (audio-only), OOD false-known reaches 72% cross-vendor, and it only scans WAV files. Overall 6.8/10, **NEEDS WORK**, driven by reach + accuracy honesty, not engineering quality.

## What changed
**Nothing in production code.** Deliverables written:
- `SLO_EVAL_SCORECARD_2026-09-18.md` (§2)
- `SLO_FEATURE_ROADMAP_2026-09-18.md` (§3)
- `SLO_AI_INFRA_PROPOSALS_2026-09-18.md` (§3b)
- `SLO_PERF_BEFORE_AFTER_2026-09-18.md` (§4)
- `SLO_EVAL_PRIORITIES_2026-09-18.md` (§5)
- `SLO_EVAL_BASELINES_2026-09-18.json` (§6.3)
- this file

## Key findings
1. **Perf speedup backlog is already spent.** Batching, ORT_ENABLE_ALL, CPU-count intra-op threads, CoreML EP, batch sweep (16/32), incremental rescan, WAL — all implemented with receipts: ~7–8× per-file gain, 10k cold = 292.9 s, rescan ~30 µs/file, search p99 0.11 ms. Remaining perf work is memory-shaping (RSS 2.19 GB @10k), not speed.
2. **The only accuracy lever that ever worked is by-ear corrections** (+3.29pp/500 per CorrectionLog.h). Nine encoders etc. produced nothing — which is why CLAP is deprioritised and correction-loop closure (F-03/A-04/A-05) ranks high.
3. **Biggest reach gap is format support** (WAV-only, deep not cosmetic) — the largest product decision on the table.
4. **Documentation truth discipline is excellent** — artifacts self-declare staleness; this audit honoured that by grading all accuracy/perf numbers as historical (D/B), never fresh (A).

## Failed experiments (this run)
- Two shell commands failed on `$S` expansion inside one command string (grep path); reran with explicit paths — no impact on evidence.
- One heredoc-based file write was interrupted; recovered and verified final files by re-read (all 7 verified by header grep + tail).

## Not touched & why
- **No branch created / no code edits:** Phase 4 EXECUTE requires a fresh recorded baseline (R2) and build/test gates; regenerating the full build + 3-scale benchmark receipts was out of scope for this session's timebox and would have produced unfresh claims mid-run. The three ready-to-run perf experiment designs (arena shaping, streaming decode, lazy/warm-up) are specified with exact gates in `SLO_PERF_BEFORE_AFTER_2026-09-18.md`.
- **Phases 2–3:** proposals only (R9). Feature and AI-infra items deliberately not implemented.
- **No secrets accessed; no large binaries loaded** (all JSON via jq/head, docs via head/grep).

## Handoff
- **Next engineering actions (in order):** (1) A-01 energy-based OOD experiment (S effort, end-to-end validation per Stage-2 lesson); (2) F-05 skip-summary + F-02 graduated confidence; (3) A-04 correction eval harness; (4) regenerate perf baseline, then P-01 arena shaping on `slo/eval-feat-ai-perf-v1`.
- **Jack decisions needed:** F-01 format scope; OOD threshold recalibration reauthorization (B-007, spec-frozen); F-07 taxonomy expansion posture; B-001..B-005 external blockers.
- **How to review:** read the scorecard first, then priorities table (§5 file) — each row carries grade + evidence citation. Re-run verification: `grep -c` checks in this repo's receipts show the cited docs exist as quoted.

## Change log
| Version | Date | Change |
|---|---|---|
| 1 | 2026-09-18 | First full evaluation run per V1 prompt. |
| 2 | 2026-09-18 | **Autonomous continuation** (user: "work autonomously"): branch `slo/eval-feat-ai-perf-v1` created from `ops/mirror-and-notes` (nothing pushed, `main` untouched). F-05 verified ALREADY SHIPPED (roadmap + priorities corrected with citations). **A-04 promoted to EXECUTE and delivered:** `tools/classification_benchmark/correction_eval_harness.py`, commit `a4d8ccd` (1 file, +328 lines). Verification matrix: (1) standalone parse/summarise exact on known-answer fixture (6 parsed, 1 dedupe-collapsed, 1 malformed skipped, 1 schema warning, no-op detected, escape-rate 20%, confidence split 0.22-unknown vs 0.6725-known); (2) gate fail on no-op row → exit 1; (3) join-mode end-to-end accuracy 0.5 exact (scored 4, correct 2, corrections-without-sample 1, misses exact); (4) strict-taxonomy lint fail → exit 1; (5) receipt JSON valid; (6) missing file → exit 2; (7) clean fixture → GATE PASS exit 0; (8) `ruff check` clean. Deliberately NOT executed: A-01 OOD experiment (B-007 spec-freeze — needs Jack's reauthorization), P-01/P-02 arena+streaming work (gated on a fresh perf baseline per R2), all F-* features (R9 propose-only except the F-05 correction which proved unnecessary). Pre-existing `kenn/` working-tree modifications intentionally left untouched and uncommitted. |
| 3 | 2026-09-18 | **Fresh perf baseline recorded (Grade A)** after user re-authorized autonomous work ("im ready let keep going"): Release+LTO build from this branch, R6 gate set green first, 3× BenchmarkScan @500 fixtures. **Historical receipts validated** (25.85/26.58 ms-per-file vs documented 25.5–28.6). **P-01 trade-off quantified:** batch-16 env posture = −45% RSS peak (1406→770 MB median) at +64% scan time (26.6→43.6 ms-per-file median) — filed as DECIDE (env knob already exists, no code change). **Experiment 2 (arena disable): NULL RESULT, reverted** — speed unchanged, RSS median worse (1546 vs 1406); falsifies the CPU-arena hypothesis; RSS holder is CoreML/ANE-side + JUCE. 11 receipt files committed under `tools/classification_benchmark/receipts/perf_baseline_20260918/`. Baselines JSON upgraded to Grade-A perf. Still deliberately not executed: A-01 (B-007 spec-freeze), streaming decode (next candidate, requires hash-stability design), taxonomy/features (propose-only). |
| 4 | 2026-09-19 | **A-01 EXECUTED → KILLED (user reauthorized: "going with your recommendations"):** offline path first proven impossible (no persisted `diagMlLogitEnergy`, no DSP fields to rebuild 520-D inputs, 0/620 + 0/168 usable rows; zero-pad approximation rejected as invalid), so rebuilt corpora from on-disk packs: 60 KSHMR vocals/ethnic (known) + 39 Old-Movies noise/guitar-loops/pads (OOD), fresh end-to-end `ClassificationBenchmark scan` runs (full decode→ONNX→520-D head→gate). **Result: energy AUROC 0.56 vs centroid 0.50 — but the shipping gate itself scores ~0.50 here (vs 0.911 V4-G KSHMR holdout):** boundary set the taxonomy does not separate; promotion required ≥0.65 absolute + >0.05 margin, neither met. **Gate untouched per kill criterion.** Deliverable: `tools/classification_benchmark/analysis_ood_energy_v1.py` (ruff clean) + gitignored receipt `receipts/ood_energy_a01_20260919.json`. Docs updated: AI-infra A-01 row, priorities rank 4. Batch-16 beta guidance (from P-01 data) documented as the standing DECIDE recommendation. |

