# SLO CLASSIFICATION QUICK-CHECK — ONE-SHOT READ-ONLY PROMPT (V1)

> **Use:** paste to any repo-aware agent. Read-only. No branch, no edits, no installs. ~15–30 min.
> **Run from:** `/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP`
> **Instruction to agent:** *"Execute `SLO_CLASSIFICATION_QUICKCHECK_PROMPT_V1.md`. Read-only. Produce the §3 report inline."*
> **Owner:** NITE DSP (Jack) · **Created:** 2026-09-18
> **Roots:** `Nite-DSP-Operations/monorepo/products/slo/SmartSampleManager/` (source of truth — VERIFY) · `Nite-DSP-Operations/monorepo/products/slo/` (docs/receipts) · `tools/classification_benchmark/` (harness)

## 0. Role

You are a **DSP/ML reviewer** doing a fast, evidence-backed health check of SLO's classifier. Prove what works, flag what lies, rank what to fix. No code changes.

## 1. Rules

- Read-only. No edits, no `rm`, no `git checkout/push`, no installs. Builds/test runs only if already documented and cheap — otherwise record `TOOL_MISSING` / `SKIPPED (why)` and continue.
- Evidence or it doesn't exist: every claim needs `file:line` or `command + output`. Prior `SLO_*.md` reports are leads, not proof.
- Never echo secrets (paths only, values → `***REDACTED***`).
- Never load large files wholesale (`*.onnx/.wav/.dmg/.zip/.tgz`, `workspace/slo_main_scan*.json`, `benchmark_reports/*.json`, `clap_*`). Use `ls/wc/head/jq/grep` + streaming reads.
- Format: `OBSERVED:` → `INFERRED (HIGH/MED/LOW):` → `UNVERIFIED (what would settle it):`. Each finding gets a Claim Grade: **A**=ran it, **B**=read code, **C**=partial, **D**=claimed-only, **E**=contradicted, **F**=unknown.

## 2. Checks (in order, timebox ~3 min each)

1. **Path map (B-grade min).** Trace one file's journey: `SampleManagerEngine.h` → features (`PhysicalAcoustics.h`/`AudioEvidence.h`) → embedding (PANNs CNN10 512-D ONNX) → `AcousticClassifier.h`+`AcousticClassifierWeights.h` → `AcousticClassifierCentroids.h` OOD gate → fusion/filename evidence → `BetaDecisionPolicy.h`/`MlOverrideGate.h` → `ClassificationPresentation.h` → SQLite WAL → HNSW search. Output ASCII flow + file:line index. Flag v5-vs-v6 dupes, scattered fusion logic, magic thresholds.
2. **Accuracy truth.** Read (don't load fully — `jq`/head): `slo_classification_metrics_v1.json`, `slo_class_metrics_v1.json`, `SLO_CLASSIFICATION_ACCURACY_REPORT_V1.md`, `SLO_CLASS_BY_CLASS_REPORT_V1.md`. Report: dataset/n/seed, overall acc, worst 3 classes (P/R/F1), top confusion pairs. Grade each number A–F.
3. **OOD/UNKNOWN.** From `AcousticClassifier.h`, `MlOverrideGate.h`, `SLO_OOD_UNKNOWN_REPORT_V1.md`: thresholds, UNKNOWN rate in-vs-out-of-domain, false-accept/reject. Sensitivity noted? Grade it.
4. **Fusion & gates.** Is there an ablation (`ablation_suite.py`)? Audio-only vs +filename vs class-conditional gates (`audit_class_conditional_gates.py`) — quote lift or mark UNVERIFIED.
5. **Parity.** `parity_references.json` + `test_cpp_parity_standalone/` + `test_fusion_v2_main.cpp`: Python↔C++ agreement %, max abs diff. Divergences (windowing/norm/thresholds) with both-side file:lines.
6. **Robustness & safety.** Cite (don't run unless trivial): `test_malformed_audio`, `test_path_traversal`, `test_format_aware_scan`, `test_readonly_safety_qualification`, `SortFileSafety.h`, cache tests (`integrity/version/hydration/multi_instance`). WAV-only limit noted? Corrupt-SQLite behaviour? Any silent failure = P1+.
7. **Perf snapshot.** Cite or measure cheaply: model load, infer p50/p95, scan files/sec, HNSW query p95, peak RSS (`SLO_PERFORMANCE_REPORT_V1.md`, `slo_performance_v1.json`, `SLO_RT_THREADING_AUDIT_V1.md`). Anything allocating/locking on audio thread = P0/P1.
8. **Docs truth.** Mark CURRENT/STALE/CONTRADICTED (one line + evidence each): `SLO_ACCURACY_ROADMAP`, `SLO_CLASSIFICATION_ACCURACY_REPORT`, `SLO_CLASS_BY_CLASS_REPORT`, `SLO_OOD_UNKNOWN_REPORT`, `SLO_ENCODER_RESEARCH_DECISION_2026-09-15`, `SLO_SCAN_INDEX_PIPELINE_REPORT`, `SLO_SIMILARITY_SEARCH_REPORT`, `SLO_BETA_BLOCKER_REGISTER_V*`.
9. **AI-integration surface (propose, don't do).** List top 3 justified local-first wins only (e.g. fusion-weight tune, gate promotion, worst-class specialist, correction-log review queue, Ollama-local low-confidence explainer). Each: one line + expected lift + kill criterion. Encoder swap (CLAP etc.) = proposal + bake-off numbers only. Any cloud-audio-upload idea = flag P0-privacy, stop.
10. **Top fixes.** Rank top 5 by `(severity × blast radius)/effort`, each: `ID|P0-P3|Title|OBSERVED|Impact|Suggested fix|S/M/L|Grade`.

## 3. Output (inline, no new files)

```markdown
## SLO Quick-Check — <DATE> — <COMMIT>
### Verdict (1 line): HEALTHY / NEEDS WORK / BLOCKED + single biggest risk
### Accuracy (overall, worst-3, confusions, grades)
### OOD/UNKNOWN (thresholds, rates, grade)
### Fusion/Parity (lifts, agreement %, divergences)
### Safety/Robustness (pass/fail per gate + citations)
### Perf (6 numbers max + source)
### Docs truth (table: doc | CURRENT/STALE/CONTRADICTED | evidence)
### Top-5 fixes (ranked)
### AI next-steps (top 3 + kill criteria)
### Receipt (commands run, files read, skipped + why)
```

Self-check before finishing: every number has a citation · every grade justified · no edits made (`git status --short` quoted) · no secrets printed · UNVERIFIED items state what would settle them.

## 4. Cookbook

```bash
git -C "Nite-DSP-Operations/monorepo/products/slo/SmartSampleManager" status --short
git -C "Nite-DSP-Operations/monorepo/products/slo/SmartSampleManager" log --oneline -5
jq '{overall, unknown_rate} + {classes: (.per_class // {} | keys)}' "Nite-DSP-Operations/monorepo/products/slo/slo_classification_metrics_v1.json" 2>/dev/null || head -c 1500 "Nite-DSP-Operations/monorepo/products/slo/slo_classification_metrics_v1.json"
grep -rn "threshold\|UNKNOWN\|centroid" "Nite-DSP-Operations/monorepo/products/slo/SmartSampleManager/Source/AcousticClassifier.h" | head -20
grep -rln "URLSession\|upload\|telemetry\|analytics" "Nite-DSP-Operations/monorepo/products/slo/SmartSampleManager/Source/" | head
ls "Nite-DSP-Operations/monorepo/products/slo/SmartSampleManager/tools/classification_benchmark/" | head -40
```
