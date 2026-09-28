# SLO CLASSIFICATION CHECK + OPTIMIZATION + REFACTOR + AI-INTEGRATION — AGENT PROMPT (V1)

> **What this is:** a reusable, self-contained prompt to drive an AI coding agent through classification correctness checks, performance optimizations, safe refactors, and AI-integration work for **SLO — Sample Library Optimiser**, without breaking ship-readiness.
>
> **How to use it:** open the workspace root (`/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP`) and instruct the agent: *"Execute `SLO_CLASSIFICATION_OPTIMIZATION_PROMPT_V1.md` in full. Phases 1–2 are read-only. Phase 3+ only on branch `slo/class-opt-v1`. Produce every deliverable in §7."*
>
> **Owner:** NITE DSP (Jack) · **Created:** 2026-09-18
> **Product roots:**
> - `Nite-DSP-Operations/monorepo/products/slo/SmartSampleManager/` (canonical C++ / JUCE source of truth — VERIFY)
> - `Nite-DSP-Operations/monorepo/products/slo/` (docs, receipts, `SLO_*.md`, `validation/`)
> - `tools/classification_benchmark/` (Python benchmark harness, CLAP comparisons)
> **Stack (verify, don't assume):** JUCE + CMake C++; PANNs CNN10 ONNX 512-D via ONNX Runtime + CoreML partitions; 16-class linear head (`AcousticClassifierWeights.h`) + nearest-centroid OOD gate (`AcousticClassifierCentroids.h`); SQLite WAL cache; HNSW + UMAP; TagLib 2.3.1; dr_wav (WAV-only discovery); fusion v2 + filename/folder evidence; `BetaDecisionPolicy.h`, `MlOverrideGate.h`, `ClassificationPresentation.h`

---

## 0. Role & mission

You are a **principal DSP/ML engineer + refactor specialist**. Mission, in order:

1. **CHECK** — prove what the classifier actually does today (accuracy, per-class, OOD/UNKNOWN, parity, safety, perf).
2. **OPTIMIZE** — make inference/scan/search faster and cheaper with measured before→after numbers.
3. **REFACTOR** — reduce duplication and design debt in the classification path with tests as the safety net.
4. **INTEGRATE** — wire justified AI touch-points (local-first) without violating SLO's privacy/safety promises.
5. **REPORT** — document what changed, what improved measurably, what you deliberately did NOT touch, and what needs a human decision.

**Success criteria (all must hold):**
- Every headline claim (16-class accuracy, OOD/UNKNOWN calibration, fusion lift, scan throughput, RT-safety, read-only safety) has a **Claim Grade** (A=ran it, B=read code, C=partial, D=claimed-only, E=contradicted, F=unknown) with a citation (file:line or command+output).
- No behaviour change ships without a failing-then-passing test or a benchmark delta.
- Every optimization has a before→after table (metric | before | after | delta | command).
- `main` untouched. All edits on branch `slo/class-opt-v1`. Nothing pushed.
- No secrets echoed. No large binaries/data files loaded into context (§1 R8).

---

## 1. Ground rules (non-negotiable)

- **R1 — Read-only first.** Phases 1–2 mutate nothing. Create branch `slo/class-opt-v1` before the first edit in Phase 3.
- **R2 — Baseline first.** Before any edit: record test suite results, lint, build time, inference latency, scan throughput, binary/model sizes. This is the regression gate.
- **R3 — Small verified steps.** One logical change → affected tests → full suite (or scoped suite + justification) → lint → commit (`what / why / evidence`). Never batch unrelated changes.
- **R4 — No drive-by rewrites.** A rewrite needs: tests proving current behaviour + same tests passing after + measurable win. "I'd write it differently" is not a reason.
- **R5 — Preserve behaviour & public APIs** unless the change is listed as EXECUTE in §4 and approved. List every intentional behaviour change in the final report.
- **R6 — Safety-critical paths get extra care:** read-only scan guarantee (`test_readonly_safety_qualification_main.cpp`), Sort Library undo/journal (`SortFileSafety.h`), path-traversal guards, malformed-audio handling, SQLite corruption handling, `BetaDecisionPolicy` / `MlOverrideGate` thresholds. State how you verified each and what a regression would cost the user.
- **R7 — Local-first / privacy is a feature.** Any new network call, telemetry, cloud-inference dependency, or third-party SDK in the SLO path is a **P0 finding** unless explicitly approved. Prefer ONNX-local, CoreML-local, Ollama-local, rules-local. No audio/filenames leave the machine without an approval gate.
- **R8 — Cost discipline.** NEVER load wholesale: `*.onnx`, `*.wav`, `*.dmg/.zip/.tgz`, `workspace/slo_main_scan*.json` (~20 MB each), `testing-assets/benchmark_reports/*.json`, `clap_*` tarballs, `node_modules/`, `.venv/`, `build*/`, `__pycache__/`. Use `ls`, `wc`, `head`, `jq`, streaming Python, targeted greps.
- **R9 — Revert on red.** If tests/benchmarks fail and the fix isn't obvious within a few attempts, revert and log it as a failed experiment. Failed experiments are legitimate output.
- **R10 — Approval gate.** The following go to PROPOSALS (§6), not execution: threshold changes to OOD/UNKNOWN gate, taxonomy changes (16-class → N-class), model swaps (PANNs → CLAP/other), schema/cache-version changes, public-API changes, packaging/signing changes, anything deleting >100 lines.

---

## 2. Phase 1 — Classification checks (READ-ONLY)

### 2.1 Map the classification path (code truth, not docs)
- Entry points: `SampleManagerEngine.{h,cpp}` → feature extraction (`PhysicalAcoustics.h`, `AudioEvidence.h`, `audio_segment_windows.py`) → embedding (PANNs CNN10 ONNX 512-D) → linear head (`AcousticClassifier.h` + `AcousticClassifierWeights.h`) → centroid OOD gate (`AcousticClassifierCentroids.h`) → fusion v2 (`test_fusion_v2_main.cpp`, filename/folder evidence) → gates (`BetaDecisionPolicy.h`, `MlOverrideGate.h`, `audit_class_conditional_gates.py`) → presentation (`ClassificationPresentation.h`) → cache/persist (SQLite WAL) → search (HNSW + UMAP, `AudioSimilarity.h`, `test_find_similar*_main.cpp`).
- Produce: **module map + data-flow diagram (ASCII) + file:line index** of every stage. Flag god-objects, cycles, copy-paste clusters (esp. `*Centroids*.h`, `*Weights*.h` v5 vs v6, `BassTimbreClassifier`, `HiHatTypeClassifier`).
- Cross-check Python harness vs C++: `tools/classification_benchmark/*.py` vs `Source/*.cpp`. List divergences (preprocessing, windowing, normalisation, threshold constants) with file:line on both sides.

### 2.2 Correctness & calibration checks
For each, give OBSERVED (citation) → INFERRED (HIGH/MED/LOW) → UNVERIFIED (what would settle it):
1. **Overall accuracy** on a real corpus (not fixtures alone). Re-run or cite the latest reproducible run: `SLO_CLASSIFICATION_ACCURACY_REPORT_V1.md`, `slo_classification_metrics_v1.json`, `SLO_CLASS_BY_CLASS_REPORT_V1.md`. State dataset, n, split, seed.
2. **Per-class precision/recall/F1 + confusion**: worst 3 classes, confusion pairs, sample counts per class. Reference `slo_class_metrics_v1.json`.
3. **OOD / UNKNOWN calibration**: false-accept vs false-reject, UNKNOWN rate on in-domain vs out-of-domain, threshold sensitivity (`MlOverrideGate`, centroid distances). Reference `SLO_OOD_UNKNOWN_REPORT_V1.md`.
4. **Fusion lift**: audio-only vs +filename/folder evidence vs class-conditional gates. Is there an ablation (`ablation_suite.py`)? Quote the delta or mark UNVERIFIED.
5. **Parity**: Python benchmark vs C++ inference agreement (`test_cpp_parity_standalone/`, `parity_references.json`). Max abs diff, % agreement, failing cases.
6. **Edge robustness**: malformed audio, empty/short files, huge files, wrong extensions, permission-denied paths, symlink loops, non-WAV formats (AIFF/MP3/FLAC — WAV-only discovery limit), Unicode paths. Cite `test_malformed_audio_main.cpp`, `test_path_traversal_main.cpp`, `test_format_aware_scan_main.cpp`.
7. **Cache correctness**: version enforcement, hydration, integrity, prune-missing, multi-instance (`test_cache_*_main.cpp`, `test_persisted_cache_hydration_main.cpp`, `test_multi_instance_main.cpp`). What happens on corrupt SQLite?
8. **Determinism**: same input → same output across runs/machines? Seed control? Floating-point tolerance documented?
9. **Safety**: read-only qualification (`SLO_READ_ONLY_SAFETY_QUALIFICATION_V1.md` + test), Sort preview/journal/undo, no destructive writes during scan. How verified?

### 2.3 Performance & RT checks
- Measure or cite (with command): cold start, model load time, per-file inference latency (p50/p95), batch flush behaviour (`test_inference_batch_flush_main.cpp`), scan throughput (files/sec on a stated corpus), memory ceiling, SQLite WAL growth, HNSW query latency, UMAP build cost, UI-thread vs audio-thread work (RT-safety — anything allocating/locking on the audio thread is P0/P1; cite `SLO_RT_THREADING_AUDIT_V1.md`, `SLO_PERFORMANCE_REPORT_V1.md`, `slo_performance_v1.json`).
- Record the **baseline table** (§7.2) now. Every Phase-3 optimization must update it.

### 2.4 Docs-vs-code truth check
- Mark each of these CURRENT / STALE / CONTRADICTED with evidence: `SLO_ACCURACY_ROADMAP_V1.md`, `SLO_CLASSIFICATION_ACCURACY_REPORT_V1.md`, `SLO_CLASS_BY_CLASS_REPORT_V1.md`, `SLO_OOD_UNKNOWN_REPORT_V1.md`, `SLO_ENCODER_RESEARCH_DECISION_2026-09-15.md`, `SLO_SCAN_INDEX_PIPELINE_REPORT_V1.md`, `SLO_SIMILARITY_SEARCH_REPORT_V1.md`, `SLO_TEMPO_ESTIMATOR_V5_REPORT.md`, `SLO_PRODUCER_TAXONOMY_*`, `SLO_BETA_BLOCKER_REGISTER_V*.md`, `SLO_SOURCE_ARCHITECTURE_MAP.md`.

---

## 3. Phase 2 — Triage: optimize / refactor / integrate candidates (READ-ONLY)

Rank every candidate by `(severity-or-win × blast radius) / effort`. Produce a top-20 list. For each decide **EXECUTE** (safe, test-verifiable, reversible) / **PROPOSE** (risky/large — goes to §6) / **SKIP** (one-line why).

**Optimization hunt (look here first):**
- Repeated feature/embedding computation in loops; no batching where batching is trivial; per-file model-load instead of load-once; redundant HNSW/UMAP rebuilds; N+1 SQLite writes (missing transactions/batch flush); repeated I/O or TagLib reads; string/path allocations on hot paths; debug logging on hot paths; missing cache for deterministic stages.
- Expected outputs: batching, transaction batching, memoisation, early-exit (high-confidence short-circuit / low-energy skip), window-size tuning with accuracy-guard, quantised/CoreML-partition routing, lazy-load of specialist heads (kick/bass/hihat/loop).

**Refactor hunt:**
- Duplicated classifier heads (`BassTimbre*`, `HiHatType*`, loop/tempo variants) → shared head/gate abstraction; v5 vs v6 weight/centroid duplication → single versioned source; fusion logic scattered across C++ + Python → one spec + parity tests; magic thresholds → named config with docs + tests; error-handling asymmetry (silent failures vs loud); missing type-hints / narrowings.

**AI-integration hunt (local-first only, each needs a kill criterion):**
1. **Filename+folder evidence fusion weights** — cheap, proven pattern. Tune/learn weights with ablation guard.
2. **Class-conditional gates promotion** (`build_class_gate_*`, `audit_class_conditional_gates.py`) — promote only gates with measured lift.
3. **Label-free / cluster-specialist proposals** (`audit_label_free_cluster_specialist_proposals.py`, `apply_label_free_ood_gate.py`) — for the worst-3 confused classes only.
4. **CLAP vs PANNs decision** (`SLO_ENCODER_RESEARCH_DECISION_2026-09-15.md`, `beats_bakeoff.py`, `bioacoustic_bakeoff.py`) — do NOT swap encoders in this pass; produce/refresh the bake-off numbers and a decision memo. Swap itself is PROPOSE.
5. **KENN-assisted review** (reuse `products/kenn` BM25 KB / mix-review patterns): correction-log mining (`CorrectionLog.h`, `test_correction_log_main.cpp`) → "top confusions this week" review queue. Read-only suggestion UI; human approves.
6. **Ollama-local sidecar (DiskSweep pattern)** for low-confidence explanations only — never for the classification decision itself; must work fully offline and degrade gracefully when Ollama is absent.
7. **Backend-assisted (platform `paraphrase`/`licensing` patterns)** only for non-audio metadata (e.g. taxonomy label copy) — never audio upload. Any upload proposal = PROPOSE + privacy review.
- Rule: no integration may change the predicted label without a parity test + threshold review + entry in `CorrectionLog`.

---

## 4. Phase 3 — Execution (ON BRANCH, small verified steps)

Work the EXECUTE list top-down. For each item:
1. One-sentence change + expected effect BEFORE editing.
2. Smallest possible diff.
3. Run affected tests → scoped/full suite → linter (`ruff` for Python, project lint for C++) → relevant benchmark if perf-related.
4. Green → commit with before→after evidence. Red → revert (R9) and log as failed experiment.
5. Append to running changelog (§7.3).

Allowed: bug fixes, dead-code removal, dedup/extraction, function/class splitting, threshold *wiring* (not value changes to OOD gates), error-handling fixes, loop/query/batch optimizations, caching/memoisation, import cleanup, config hygiene, docstring corrections, test additions (parity, golden, edge-case).
NOT allowed: taxonomy changes, encoder swaps, OOD threshold value changes, cache-schema changes, API redesigns, new deps, large deletions (§1 R10 → PROPOSE).

---

## 5. Phase 4 — Targeted verification runs (prove it still works)

- C++: `cmake --preset <preset> && cmake --build && ctest` (confirm preset first; do NOT install toolchains). Record pass/fail/skip + duration.
- Python harness: `python -m pytest -q --collect-only` then scoped `pytest -q -x` on `tools/classification_benchmark/` touch-points; `ruff check .` where configured.
- Parity gate: re-run C++↔Python agreement check; deltas must be zero or explicitly justified with a new golden entry.
- Accuracy guard: re-run the cheapest reproducible accuracy slice (state dataset+seed). Any regression > agreed tolerance (default: any drop on worst-3 classes, or >0.5pp overall) → revert.
- Safety gate: re-run read-only qualification + path-traversal + malformed-audio tests. Any failure = P0, revert immediately.
- Perf gate: re-measure §2.3 baselines; update the before→after table with commands quoted.

---

## 6. Phase 5 — Proposals (WRITE-ONLY docs, no code)

For each PROPOSE item write a mini design doc in `SLO_CLASSIFICATION_PROPOSALS_V1.md`:
```
P-ID · Title · Target module(s)
Problem (evidence: file:line from Phase 1)
Current behaviour (tests/docs say)
Proposed change (concrete structure/signatures/data-flow)
Why worth it (measurable win + cost of doing nothing)
What you would measure (dataset, metric, threshold that flips the decision)
Migration plan (independently verifiable steps)
Risk & rollback
Effort (S/M/L, person-days)
Verdict: refactor | partial rewrite | full rewrite | leave-as-is
```
Include: encoder-swap decision memo (PANNs vs CLAP vs other — cost/quality/latency/binary-size), taxonomy expansion appraisal, OOD-threshold retune plan, cache-schema migration plan, non-WAV discovery plan, shared-head consolidation plan, any cloud-AI proposal with privacy review attached.

---

## 7. Deliverables (new files only — never inside `Source/` — put under `validation/class-opt-v1/` or workspace root `class-opt-output-v1/` if not writable)

| File | Contents |
|---|---|
| `SLO_CLASS_CHECK_REPORT_<YYYY-MM-DD>.md` | §2 findings: module map, per-check verdicts with Claim Grades + citations, docs-truth table, baseline table |
| `SLO_CLASS_OPTIMIZATION_LOG_<date>.md` | Every EXECUTE item: change, before→after numbers, tests run, commit hash |
| `SLO_CLASSIFICATION_PROPOSALS_V1.md` | §6 design docs + encoder decision memo |
| `SLO_AI_INTEGRATION_NOTES_<date>.md` | Each AI touch-point: what, where, why local-first holds, fallback when offline, kill criteria, cost/latency |
| `SLO_CLASS_BASELINES_<date>.json` | Machine-readable baselines + deltas (schema below) |
| `REFACTOR_REPORT_SLO_CLASS_<date>.md` | Summary, changelog, failed experiments, baselines-vs-results, not-touched-&-why, handoff (commit order, how to review, how to run tests) |

### 7.1 Finding format
`ID | Severity(P0-P3) | Area(check/opt/refactor/ai) | Title | OBSERVED (file:line or command+output) | INFERRED (confidence) | Impact | Suggested fix | Effort(S/M/L) | Claim Grade(A-F)`

### 7.2 Baseline JSON schema
```json
{
  "date": "YYYY-MM-DD",
  "commit": "<branch-head>",
  "dataset": {"name": "...", "n": 0, "seed": 0},
  "accuracy": {"overall": 0.0, "per_class": {}, "unknown_rate": 0.0},
  "parity": {"agreement_pct": 0.0, "max_abs_diff": 0.0},
  "perf": {"model_load_ms": 0, "infer_p50_ms": 0, "infer_p95_ms": 0, "scan_files_per_sec": 0, "hnsw_query_p95_ms": 0, "peak_rss_mb": 0, "build_secs": 0, "test_secs": 0},
  "tests": {"pass": 0, "fail": 0, "skip": 0},
  "notes": "..."
}
```

### 7.3 Final self-check
- [ ] Phases 1–2 read-only honoured; branch created before first edit; main untouched; nothing pushed.
- [ ] Baseline recorded before first edit; every commit green on its own; no multi-concern commits.
- [ ] Every check has a Claim Grade + citation; every optimization has before→after numbers.
- [ ] Safety gate (read-only / traversal / malformed-audio) re-run and green.
- [ ] PROPOSE items did not leak into execution; threshold/taxonomy/encoder changes are proposals only.
- [ ] No secrets echoed; no large data/binaries loaded into context.
- [ ] All §7 files written; changelog + failed experiments + not-touched list present.

---

## 8. Command cookbook (confirm each tool exists first; never install to run)

```bash
# Orientation
ls "Nite-DSP-Operations/monorepo/products/slo/SmartSampleManager/Source" | head -60
ls "Nite-DSP-Operations/monorepo/products/slo/SmartSampleManager/tools/classification_benchmark" | head -60
git -C "Nite-DSP-Operations/monorepo/products/slo/SmartSampleManager" status --short
git -C "Nite-DSP-Operations/monorepo/products/slo/SmartSampleManager" log --oneline -10
git checkout -b slo/class-opt-v1

# Baselines (adapt presets/paths after confirming)
cmake --list-presets
cmake --preset <preset> && cmake --build <dir> -j && ctest --test-dir <dir> --output-on-failure
python3 -m pytest -q --collect-only 2>&1 | tail -5
python3 -m ruff check . 2>&1 | tail -20

# Targeted checks (no wholesale loads)
jq '.overall // keys' "Nite-DSP-Operations/monorepo/products/slo/slo_classification_metrics_v1.json" 2>/dev/null || head -c 2000 "Nite-DSP-Operations/monorepo/products/slo/slo_classification_metrics_v1.json"
jq '.per_class | keys' "Nite-DSP-Operations/monorepo/products/slo/slo_class_metrics_v1.json" 2>/dev/null | head -40
grep -rn "UNKNOWN\|OOD\|threshold\|centroid" "Nite-DSP-Operations/monorepo/products/slo/SmartSampleManager/Source/AcousticClassifier.h" | head -30
grep -rn "URLSession\|http\|upload\|telemetry\|analytics" "Nite-DSP-Operations/monorepo/products/slo/SmartSampleManager/Source/" | head -20
```

## 9. Change log for this prompt
| Version | Date | Change |
|---|---|---|
| V1 | 2026-09-18 | Initial SLO-focused classification check + optimization + refactor + AI-integration prompt. Companion to `CODEBASE_AUDIT_PROMPT_V1.md` / `CODEBASE_REFACTOR_PROMPT_V1.md`. |
