# SLO EVALUATION + FEATURE DISCOVERY + AI-INFRA + PERFORMANCE — AGENT PROMPT (V1)

> **What this is:** a reusable, self-contained prompt to drive an AI coding agent through a full **"how good is SLO actually?"** evaluation, then a structured hunt for **new features**, **more AI infrastructure**, and **performance speedups** — for **SLO — Sample Library Optimiser (SmartSampleManager)** — without breaking ship-readiness.
>
> **How to use it:** open the workspace root (`/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP`) and instruct the agent: *"Execute `SLO_EVALUATION_FEATURES_AI_PERF_PROMPT_V1.md` in full. Phase 1 is read-only. Everything else requires branch `slo/eval-feat-ai-perf-v1`. Produce every deliverable in §6."*
>
> **Owner:** NITE DSP (Jack) · **Created:** 2026-09-18
> **Companion prompts:** `SLO_CLASSIFICATION_QUICKCHECK_PROMPT_V1.md` (fast health check) · `SLO_CLASSIFICATION_OPTIMIZATION_PROMPT_V1.md` (deep classifier work) · `CODEBASE_AUDIT_PROMPT_V1.md`
>
> **Product roots (VERIFY, don't assume):**
> - `Nite-DSP-Operations/monorepo/products/slo/SmartSampleManager/` — canonical C++ / JUCE source of truth
> - `Nite-DSP-Operations/monorepo/products/slo/` — docs, receipts, `SLO_*.md`, `validation/`
> - `tools/classification_benchmark/` — Python benchmark harness (CLAP comparisons etc.)
>
> **Stack (verify):** JUCE + CMake C++; PANNs CNN10 ONNX 512-D embeddings via ONNX Runtime (+ CoreML partitions); 16-class linear head (`AcousticClassifierWeights.h`) + nearest-centroid OOD gate (`AcousticClassifierCentroids.h`); SQLite WAL cache; HNSW similarity + UMAP; TagLib 2.3.1; dr_wav (WAV-only discovery); fusion v2 + filename/folder evidence; `BetaDecisionPolicy.h`, `MlOverrideGate.h`, `ClassificationPresentation.h`.

---

## 0. Role & mission

You are a **principal product/DSP/ML engineer + performance specialist + product strategist**. Mission, in order:

1. **EVALUATE** — score SLO end-to-end (how good it actually is today): product completeness, classification quality, search quality, UX/presentation, safety, robustness, performance, code health. Give an overall verdict with a scorecard.
2. **DISCOVER** — propose new features ranked by user value × effort, grounded in what the code can already do and what users of a sample-library tool actually need.
3. **AI-INFRA** — identify additional AI infrastructure worth adding (local-first): models, pipelines, caches, tooling, eval infrastructure, runtime accelerators. Privacy promise: **no cloud audio upload, ever** — every AI idea must work fully offline (or be rejected/flagged).
4. **SPEED UP** — find and (optionally, on branch) implement performance wins: scan throughput, model load, inference latency, indexing, search, startup, memory, build time.
5. **REPORT** — scorecard + ranked roadmap + before→after perf table + what you deliberately did NOT touch.

**Success criteria (all must hold):**
- Every claim has a **Claim Grade** (A=ran it, B=read code, C=partial, D=claimed-only, E=contradicted, F=unknown) with a citation (file:line or command+output).
- Every performance change has a measured before→after: `metric | before | after | delta | command`.
- No behaviour change without a failing-then-passing test or benchmark delta.
- `main` untouched; edits only on branch `slo/eval-feat-ai-perf-v1`; nothing pushed.
- No secrets echoed; no large binaries/data loaded into context (§1 R8).

---

## 1. Ground rules (non-negotiable)

- **R1 — Read-only first.** Phase 1 (Evaluation) mutates nothing. Branch `slo/eval-feat-ai-perf-v1` before the first edit in Phase 4.
- **R2 — Baseline before edits.** Record: test suite result, lint, build time, model load ms, infer p50/p95, scan files/sec, HNSW query p95, peak RSS, startup time, binary + model sizes.
- **R3 — Small verified steps.** One logical change → affected tests → full suite → lint → commit (`what / why / evidence`). No multi-concern commits.
- **R4 — No drive-by rewrites.** Same tests before/after + measurable win, or don't.
- **R5 — Preserve behaviour & public APIs** unless listed EXECUTE and approved. List all intentional behaviour changes in the report.
- **R6 — Safety-critical extra care:** read-only scan guarantee, path-traversal, malformed-audio handling, SQLite corruption behaviour. Re-run those gates after any change.
- **R7 — Privacy is a hard invariant.** Any AI feature that uploads audio, user file paths, or library metadata to the cloud = P0, reject in the report. Local-first only (ONNX Runtime local, CoreML local, Ollama-local LLM are fine).
- **R8 — Context hygiene.** Never load `*.onnx`, `*.wav`, `*.dmg`, `*.zip`, `workspace/slo_main_scan*.json`, `benchmark_reports/*.json` wholesale. Use `ls/wc/head/jq/grep` and streaming reads.
- **R9 — Phases 2–3 are PROPOSE-only.** Feature and AI-infrastructure ideas do NOT get implemented in this run. Only Phase 4 perf items marked EXECUTE get implemented, one at a time, gated by tests.
- **R10 — Timebox.** Evaluation ≤ 60 min, each phase ≤ 60 min. If a tool is missing, record `TOOL_MISSING` and continue; never install to run.


---

## 2. Phase 1 — EVALUATE: "how good is SLO?" (read-only)

Score each area 0–10 with evidence, then total. For each: `OBSERVED: file:line or cmd+output` → `INFERRED (HIGH/MED/LOW)` → `Grade A–F`.

1. **Discovery & scan.** WAV-only limit (dr_wav)? File-format coverage (aiff/flac/ogg/mp3 = gaps)? Incremental scan vs full rescan? Cache hydration/integrity/multi-instance tests?
2. **Classification quality.** From metrics JSONs (via `jq`, not wholesale): overall acc, worst-3 classes (P/R/F1), top confusions, UNKNOWN/OOD rates in- vs out-of-domain, false-accept/reject trade-off. Grade each number.
3. **Fusion & decision gates.** Fusion v2 lift (audio-only vs +filename vs class-conditional gates) — quote ablation numbers or mark UNVERIFIED. `BetaDecisionPolicy.h` / `MlOverrideGate.h` sanity.
4. **Similarity search.** HNSW config sanity (M, ef, metric vs UMAP/512-D space), query p95, recall evidence, index persistence, rebuild-on-change story.
5. **UX & presentation.** `ClassificationPresentation.h`: confidence display, UNKNOWN handling, user-correction loop (does a correction feed back into anything?). Tag pipeline: how tags get written (TagLib), user visibility, undo story.
6. **Robustness & safety.** Cite (don't run unless trivial): `test_malformed_audio`, `test_path_traversal`, `test_format_aware_scan`, `test_readonly_safety_qualification`, `SortFileSafety.h`, cache tests. Any silent failure = P1+.
7. **Performance** (numbers or UNVERIFIED): model load, infer p50/p95, scan files/sec, HNSW query p95, peak RSS, startup, build/test time. Anything allocating/locking on the audio thread = P0/P1.
8. **Code health.** Duplication (v5-vs-v6 classes?), module boundaries, test coverage of the classify path, build warnings, CI story.
9. **Docs truth.** Mark CURRENT / STALE / CONTRADICTED (one line + evidence each) for: `SLO_ACCURACY_ROADMAP*`, `SLO_CLASSIFICATION_ACCURACY_REPORT*`, `SLO_CLASS_BY_CLASS_REPORT*`, `SLO_OOD_UNKNOWN_REPORT*`, `SLO_PERFORMANCE_REPORT*`, `SLO_SIMILARITY_SEARCH_REPORT*`, `SLO_SCAN_INDEX_PIPELINE_REPORT*`, `SLO_BETA_BLOCKER_REGISTER*`.
10. **Verdict + scorecard.** One-line verdict: `SHIP-READY / NEEDS WORK / BLOCKED` + single biggest risk. Scorecard table: area | score /10 | grade | top gap.

---

## 3. Phase 2 — DISCOVER: new features (propose, don't build)

Ground every idea in Phase 1 evidence. For each idea: `ID | Title | User story (1 line) | Why now (evidence) | Effort S/M/L | Risk | Depends on`.

Candidate seeds to evaluate (add your own; cut any without a real user story):
- **Format expansion:** AIFF/FLAC/MP3/OGG discovery (currently WAV-only) — biggest reach win?
- **User correction loop:** "this is wrong" button → correction log → re-rank / per-user centroid adaptation → eval harness for correction data.
- **Auto-tagging v2:** tempo, key, mood, energy, one-shot vs loop — which are cheap wins vs which need new models?
- **Smart collections / auto-playlists** from classification + similarity ("all dusty acoustic one-shots in Bm").
- **Duplicate / near-duplicate detection** via the embeddings similarity already computes.
- **Batch actions:** apply classification to folder, bulk rename by class, bulk tag write (via TagLib).
- **Search UX:** natural-language filter bar (local LLM via Ollama allowed — flag latency), faceted filters on class/confidence/tempo.
- **Library analytics:** coverage dashboard (classes, gaps, sizes, stale samples).
- **Export/interop:** Ableton/Logic-friendly tagging, CSV/NML export.
- **Offline-first packaging:** does the ONNX model + head weights ship correctly; app-size budget; first-run model verification.

Rank the top 8 by `(user value × confidence in lift) / effort`. Mark the single best "do next" candidate and describe its MVP slice (smallest shippable version + its test).

---

## 3b. Phase 3 — AI-INFRA: more AI infrastructure to add (propose, don't build)

Evaluate each axis; propose only **local-first** items, each with a **kill criterion** and a latency/cost estimate:

1. **Models.** Better encoder (CLAP/other) — proposal + bake-off numbers required first, no swap; a specialist head for the worst class; tempo/key/mood heads sharing the existing 512-D embedding (cheap multi-task win?); ONNX int8 quantisation with accuracy-parity gate.
2. **Runtime acceleration.** CoreML partition coverage (which ops fall back to CPU today?), session options, intra/inter-op thread tuning, arena/allocator config, batched inference during scan.
3. **Eval infrastructure.** Continuous classification benchmark harness (dataset + seed pinned, CI-runnable), per-commit regression gate on accuracy + latency, correction-log-driven eval set.
4. **Data infrastructure.** Correction log → training-data pipeline; versioned embedding cache (per-file features — exists? invalidated on model change?); drift monitoring (library mix vs training mix).
5. **Local LLM layer (Ollama or similar, optional).** Low-confidence explainer, natural-language search parsing, tag suggestion — each with a latency budget and graceful offline fallback. NO cloud calls.
6. **Retrieval infra.** HNSW parameter sweep tool, periodic reindex job, hybrid search (embedding + metadata filters).

Output: table `Item | What | Where it plugs in (file:line) | Expected lift | Latency/cost | Offline-safe? | Effort | Kill criterion`. Flag any cloud-dependent idea as `P0-privacy-reject` and stop there.


---

## 4. Phase 4 — SPEED UP (EXECUTE only on branch `slo/eval-feat-ai-perf-v1`)

From Phase 1 perf numbers, list candidate wins ranked by `(impact × confidence) / effort`. Implement **at most the top 3**, one commit each, full test suite + benchmark after every step.

Typical suspects to verify in this codebase (confirm in code, don't assume):
- **Model load:** ONNX Runtime session options, CoreML partition flags, session reuse across files (no per-file session churn), model warm-up.
- **Inference latency:** int8 quantisation (parity-gated), op fusion, batched inference during scan, `intra_op_num_threads`.
- **Scan throughput:** split I/O-bound vs CPU-bound stages (parallel TagLib metadata vs serial ONNX), incremental scan (skip unchanged via size+mtime), SQLite WAL pragmas (`synchronous`, `cache_size`).
- **HNSW query p95:** ef/M tuning, index persistence vs rebuild, warm-up query.
- **Startup:** lazy-load model until first classify, defer UMAP, defer index build.
- **Memory:** peak RSS during big-library scan; dr_wav streaming vs full-file load; release of session buffers.
- **Build/test time:** unity builds, PCH, test-binary split.

**Gates:** read-only-safety, path-traversal, malformed-audio tests green after every step; no accuracy regression (re-run classification benchmark, overall acc delta ≤ −0.1%); record before→after per commit.

---

## 5. Priority merge of all findings

One ranked table combining Phases 1–4:
`Rank | ID | Area(check/feature/ai/perf) | Title | Severity(P0–P3) | Impact | Effort | Grade | Next action (EXECUTE / PROPOSE / DECIDE)`
P0 items (privacy, safety, data loss) always sort to the top regardless of score.

## 6. Phase 5 — REPORT

### 6.1 Deliverables (write to `Nite-DSP-Operations/monorepo/products/slo/`)
| File | Contents |
|---|---|
| `SLO_EVAL_SCORECARD_<date>.md` | §2 scorecard, verdict, per-area evidence + grades |
| `SLO_FEATURE_ROADMAP_<date>.md` | §3 ranked features + MVP slices + do-next |
| `SLO_AI_INFRA_PROPOSALS_<date>.md` | §3b table + privacy audit |
| `SLO_PERF_BEFORE_AFTER_<date>.md` | §4 tables, commits, failed experiments |
| `SLO_EVAL_PRIORITIES_<date>.md` | §5 merged ranked table |
| `SLO_EVAL_BASELINES_<date>.json` | §6.3 schema |
| `SLO_EVAL_REPORT_<date>.md` | Summary, changelog, failed experiments, not-touched-&-why, handoff (commit order, review guide, test commands) |

### 6.2 Finding format
`ID | Severity(P0-P3) | Area | Title | OBSERVED (file:line or cmd+output) | INFERRED (confidence) | Impact | Suggested fix | Effort(S/M/L) | Claim Grade(A-F)`

### 6.3 Baseline JSON schema
```json
{
  "date": "YYYY-MM-DD",
  "commit": "<branch-head>",
  "accuracy": {"overall": 0.0, "per_class": {}, "unknown_rate": 0.0},
  "perf": {"model_load_ms": 0, "infer_p50_ms": 0, "infer_p95_ms": 0, "scan_files_per_sec": 0, "hnsw_query_p95_ms": 0, "startup_ms": 0, "peak_rss_mb": 0, "build_secs": 0, "test_secs": 0},
  "tests": {"pass": 0, "fail": 0, "skip": 0},
  "scorecard": {"discovery": 0, "classification": 0, "search": 0, "ux": 0, "safety": 0, "perf": 0, "code_health": 0, "docs": 0, "overall": 0},
  "notes": "..."
}
```

### 6.4 Final self-check
- [ ] Phase 1 read-only honoured; branch created before first edit; main untouched; nothing pushed.
- [ ] Baseline recorded before first edit; every commit green; no multi-concern commits.
- [ ] Every claim has Grade + citation; every perf change has before→after numbers.
- [ ] Accuracy parity re-run after perf changes; no regression > 0.1%.
- [ ] Phases 2–3 PROPOSE-only; nothing from them implemented.
- [ ] Privacy audit: zero cloud-audio/cloud-metadata ideas approved; any found flagged P0.
- [ ] No secrets echoed; no large data/binaries loaded into context.
- [ ] All §6.1 files written; changelog + failed experiments + not-touched list present.

---

## 7. Command cookbook (confirm each tool exists first; never install to run)

```bash
# Orientation
ls "Nite-DSP-Operations/monorepo/products/slo/SmartSampleManager/Source" | head -60
ls "Nite-DSP-Operations/monorepo/products/slo/SmartSampleManager/tools/classification_benchmark" | head -60
git -C "Nite-DSP-Operations/monorepo/products/slo/SmartSampleManager" status --short
git -C "Nite-DSP-Operations/monorepo/products/slo/SmartSampleManager" log --oneline -10
git checkout -b slo/eval-feat-ai-perf-v1

# Baselines (adapt presets/paths after confirming)
cmake --list-presets
cmake --preset <preset> && cmake --build <dir> -j && ctest --test-dir <dir> --output-on-failure
python3 -m pytest -q --collect-only 2>&1 | tail -5
python3 -m ruff check . 2>&1 | tail -20

# Targeted checks (no wholesale loads)
jq '{overall, unknown_rate} + {classes: (.per_class // {} | keys)}' "Nite-DSP-Operations/monorepo/products/slo/slo_classification_metrics_v1.json" 2>/dev/null || head -c 2000 "Nite-DSP-Operations/monorepo/products/slo/slo_classification_metrics_v1.json"
jq '.' "Nite-DSP-Operations/monorepo/products/slo/slo_performance_v1.json" 2>/dev/null | head -c 2000
grep -rn "UNKNOWN\|OOD\|threshold\|centroid" "Nite-DSP-Operations/monorepo/products/slo/SmartSampleManager/Source/AcousticClassifier.h" | head -30
grep -rn "URLSession\|http\|upload\|telemetry\|analytics" "Nite-DSP-Operations/monorepo/products/slo/SmartSampleManager/Source/" | head -20
grep -rn "intra_op\|inter_op\|CoreML\|optimization\|thread" "Nite-DSP-Operations/monorepo/products/slo/SmartSampleManager/Source/" --include='*.h' --include='*.cpp' | head -30
```

## 8. Change log for this prompt
| Version | Date | Change |
|---|---|---|
| V1 | 2026-09-18 | Initial SLO evaluation ("how good is it") + feature discovery + AI-infrastructure proposals + performance speedup prompt. Complements SLO_CLASSIFICATION_{QUICKCHECK,OPTIMIZATION}_PROMPT_V1. |
