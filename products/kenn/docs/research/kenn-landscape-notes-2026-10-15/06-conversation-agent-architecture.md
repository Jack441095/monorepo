# 06 — Conversation-agent architecture: eval harnesses, memory, structured output, training tooling, retrieval deltas — 15 Oct 2026

Lane 06 notes. Target: KENN closed-source, local-first assistant for Ableton Live on M3 16 GB.
Scope: Q1 offline eval harnesses, Q2 memory-system patterns, Q3 structured output / tool calling, Q4 LoRA fine-tune tooling for the SEAL stack, Q5 retrieval deltas.
Two overlaps are deliberately not re-run: reranking (lane 02 KQ4) and the embedding-model refresh (lane 02 KQ5) stay in lane 02; the assistant-ecosystem survey stays in [KENN_COMPARABLE_PRODUCTS_AND_OPEN_SOURCE_RESEARCH_2026-10-14.md](../KENN_COMPARABLE_PRODUCTS_AND_OPEN_SOURCE_RESEARCH_2026-10-14.md) and is cited, not repeated.
Status legend: **[V]** verified against a primary source this run (URL + date inline) · **[R]** reproduced from this pass's earlier fetch log, not re-fetched · **[I]** inferred · **[?]** could not verify. All [V] items fetched 2026-10-15.
Licence policy: MIT/BSD/ISC/Apache-2.0 clean; MPL-2.0 test-only; GPL/AGPL/LGPL/BSL/PolyForm/non-commercial/unclear = problem. Weights count as much as code.

Headline claims (each verified in the sections below; URLs + dates inline):
- **H1.** promptfoo is the best-fit local eval harness for KENN: MIT, one npm package, first-class `ollama:chat:*` targets with Ollama usable as the *grading* provider too — and the one feature that decides the choice on a 16 GB box: `keep_alive: 0`, which unloads the model immediately after each request while Ableton also needs the memory. Its own docs warn serial execution does not by itself keep one model resident.
- **H2.** DeepEval is the Python-native second: Apache-2.0, pytest-style, Ollama judge via `deepeval set-ollama`; the hosted Confident AI platform is optional.
- **H3.** Inspect AI is the audit-grade third: MIT, UK-government (BEIS) provenance, Ollama + llama-cpp-python providers, and the strongest evidence trail of the three — a local log viewer on 127.0.0.1:7575, score filtering, and a static `inspect view bundle` export for sealed runs.
- **H4.** Ragas — the harness usually named for RAG metrics — is **dormant**: Apache-2.0, but last push 2026-02-24, last PyPI 2026-01-13, 637 open issues, repo now `vibrantlabsai/ragas`. Not a candidate for a gating harness.
- **H5.** Langfuse self-host is OSS (MIT outside `ee/`; enterprise licence inside, verbatim below) but costs five services. Annotation Queues — the human-review feature — sit outside `ee/`. Not justified at KENN's volume today.
- **H6.** mem0 (Apache-2.0) is the memory system whose April 2026 rewrite matches KENN's pattern: single-pass ADD-only extraction — "Memories accumulate; nothing is overwritten" — but its published scores are explicitly managed-platform numbers, and the OSS SDK still defaults to OpenAI models.
- **H7.** Graphiti (Apache-2.0) is the bitemporal alternative — facts carry validity windows; changed facts are "invalidated — not deleted" — but it needs Neo4j/FalkorDB/AWS infra, and its README warns extraction schemas break on smaller models, which is KENN's model class.
- **H8.** Letta's original repo is retired in place ("Historical source"); active development moved to `letta-code`, a coding-agent application, not an embeddable memory library.
- **H9.** KENN's existing memory schema already implements the conservative pattern (bounded rows, active/inactive supersede, keep/revise/reject verdicts, explicit exclusion of hidden reasoning and tool payloads). The adoptable delta from mem0/Graphiti is pattern validation, not a dependency.
- **H10.** Structured output on the local stack converges on **XGrammar** (Apache-2.0): KENN's current Ollama line contains an XGrammar-based constraint layer in the MLX runner (`mlxrunner/xgrammar/`), and the XGrammar paper reports "up to 100x speedup over existing solutions" with "near-zero overhead structure generation" in end-to-end serving. Lane 02's open question — does the MLX runner apply `format` schemas at all — is answered: yes, via XGrammar. Behavioural parity with the llama.cpp runner is still unmeasured.
- **H11.** Outlines (Apache-2.0) is the viable Python-side schema layer across backends but positions itself open-core; llguidance (MIT) is the second engine. Neither is needed while Ollama's `format` path works.
- **H12.** LoRA tooling: KENN's SEAL stack is already PEFT-based (`peft>=0.12` in `requirements-training.txt`). Stay there. Unsloth is **dual-licensed** — Apache-2.0 core, AGPL-3.0 Studio UI (verbatim README) — so a repo-level "Apache-2.0" statement is incomplete for a closed-source product. Axolotl is Apache-2.0 but declares NVIDIA Ampere+ (or AMD) hardware and defaults telemetry on; neither fits the SEAL harness as-is.
- **H13.** Q5 verdict: the biggest retrieval win is already shipped — hybrid RRF fusion, measured 24 Sept 2026 (253 questions: recall@4 0.966 → 0.983). The genuinely additive technique is pre-retrieval query rewriting (Rewrite-Retrieve-Read, EMNLP 2023), which KENN does not currently do on the follow-up path.

## Key Question 1 — Offline eval harnesses for C1/C4 runs (2026 state)

### Takeaway
Three harnesses are licence-clean and active; the choice is about runtime footprint and output format, not licence risk. **promptfoo** wins on the specific constraint that decides this: on a 16 GB machine that must coexist with Ableton, its docs are the only ones that name the residency problem and provide `keep_alive: 0` to solve it, plus assertion-concurrency control down to one grader call. **DeepEval** is the choice if the suite should live inside pytest. **Inspect AI** is the choice when the artefact must be audit-grade (sealed C4 runs, per-family scoring, a bundled viewer for a reviewer). Ragas is out on staleness alone.

### Cited Findings — promptfoo
- Licence and activity: MIT; 26,012★; pushed 2026-10-15T11:01Z. npm `promptfoo@0.124.1` published 2026-10-08, licence MIT. [GitHub API](https://api.github.com/repos/promptfoo/promptfoo); [npm registry](https://registry.npmjs.org/promptfoo) [V]
- Provider surface: `ollama:completion:*` and `ollama:chat:*` targets (e.g. `ollama:chat:qwen3`); `format` accepts `json` or a JSON schema to constrain output; on reasoning models combine `format` with `think: false`. [Ollama provider doc](https://raw.githubusercontent.com/promptfoo/promptfoo/main/site/docs/providers/ollama.md), fetched 2026-10-15 [V]
- Ollama as the **grading** provider: text assertions (`llm-rubric`, `answer-relevance`, `factuality`) and embedding assertions (`similar`) can each point at a different local Ollama model. [same doc, §"Using Ollama as a Local Grading Provider"] [V]
- The 16 GB feature: "Serial execution does **not** by itself keep only one model in memory. Ollama holds each model it has loaded for its own `keep_alive` window (5 minutes by default), so evaluating two providers serially can still leave both resident — confirm with `ollama ps`." The fix is documented: `keep_alive: 0 # unload immediately after each request`. [same doc] [V]
- Concurrency: `-j 1` serializes target calls; model-graded assertions run on a separate path — with grading grouping active, "up to `PROMPTFOO_ASSERTIONS_MAX_CONCURRENCY` grader calls (3 by default)"; grouping is disabled by a per-eval timeout or a conversation variable. The grouping feature is documented verbatim: "Promptfoo groups eligible model-graded assertion calls by grading provider ID to reduce local model switching. This is not request batching; each assertion call still runs separately." [same doc] [V]
- Human read-back: a browser-based setup flow (`promptfoo eval setup`) and a results Web UI exist. [Getting-started doc](https://raw.githubusercontent.com/promptfoo/promptfoo/main/site/docs/getting-started.md) [V]
- Test loading via CSV and `file://` suite directories, config as YAML with Python variable scripts. [R] (config-guide fetch earlier in this pass; not re-fetched)

### Cited Findings — DeepEval
- Licence and activity: Apache-2.0; 18,882★; pushed 2026-10-15T11:52Z; PyPI `deepeval@4.2.9` uploaded 2026-10-15. [GitHub API](https://api.github.com/repos/confident-ai/deepeval); [PyPI JSON](https://pypi.org/pypi/deepeval/json) [V]
- Ollama judge path: `deepeval set-ollama --model=… --save` writes `LOCAL_MODEL_API_KEY`, `LOCAL_MODEL_BASE_URL`, `OLLAMA_MODEL_NAME` for you; default base URL `http://localhost:11434`. [DeepEval Ollama integration](https://www.deepeval.com/integrations/models/ollama) [V]
- Pytest-native test style; G-Eval rubric metrics; the Confident AI platform is a separate optional commercial side. [R] (earlier fetch this pass)

### Cited Findings — Inspect AI
- Licence and activity: MIT; 3,008★; pushed 2026-10-15T12:09Z; PyPI `inspect-ai@0.3.280` uploaded 2026-10-14. [GitHub API](https://api.github.com/repos/UKGovernmentBEIS/inspect_ai); [PyPI JSON](https://pypi.org/pypi/inspect-ai/json) [V]
- Providers: `ollama/llama3.1` with `OLLAMA_BASE_URL` (default `http://localhost:11434/v1`); `llama-cpp-python/llama3` with `LLAMA_CPP_PYTHON_BASE_URL` (default `http://localhost:8000/v1`); tool emulation available for Ollama models via `-M emulate_tools`. [providers doc](https://raw.githubusercontent.com/UKGovernmentBEIS/inspect_ai/main/docs/providers.qmd) [V]
- Viewer: `inspect view` binds 127.0.0.1:7575 by default, live-updates as evals run; a **Scores** picker filters log entries by score; `--no-trust-content` renders all log content as plain text. `inspect view bundle` creates "a self contained directory with the log viewer and a set of logs" deployable to any static host (GitHub Pages, S3, Netlify) or Hugging Face Spaces; Python API `bundle_log_dir()`. [log-viewer doc](https://raw.githubusercontent.com/UKGovernmentBEIS/inspect_ai/main/docs/log-viewer.qmd) [V]

### Cited Findings — Ragas
- Repo now `vibrantlabsai/ragas` (not a fork; `parent=null`), Apache-2.0, 16,034★, **last push 2026-02-24**, 637 open issues; last PyPI release 0.4.3 on 2026-01-13. [GitHub API](https://api.github.com/repos/vibrantlabsai/ragas); [PyPI JSON](https://pypi.org/pypi/ragas/json) [V]

### Cited Findings — Langfuse (trace store, if ever needed)
- Composite licence: root LICENSE — "All content that resides under the 'ee/', 'web/src/ee/', and/or 'worker/src/ee/' directories of this repository, if these directories exist, is licensed under the license defined in 'ee/LICENSE'"; "Content outside of the above mentioned directories or restrictions above is available under the 'MIT Expat' license". `ee/LICENSE` — "Langfuse is an open core project. Langfuse's core is permissively licensed (MIT license). Certain parts of the periphery of Langfuse are commercially licensed and governed by this Enterprise License." (ClickHouse, Inc, 2023–2026). [root LICENSE](https://raw.githubusercontent.com/langfuse/langfuse/main/LICENSE); [ee/LICENSE](https://raw.githubusercontent.com/langfuse/langfuse/main/ee/LICENSE) [V]
- Activity: 35,857★, pushed 2026-10-15T12:10Z; API licence field reads NOASSERTION because the licence is composite. [GitHub API](https://api.github.com/repos/langfuse/langfuse) [V]
- Self-host footprint: Web + Worker containers, PostgreSQL, Redis/Valkey, ClickHouse, S3/blob. [R] (earlier fetch this pass)
- Annotation Queues (human-vs-AI review) code lives at `web/src/features/annotation-queues/…` — outside the `ee/` directories; docs carry no EE badge. [code path check + docs fetch earlier this pass] [R]

### Inferences
- For C1's 30-question repeat runs, promptfoo's cost of adoption is one npm package and one YAML file; its `keep_alive: 0` and `PROMPTFOO_ASSERTIONS_MAX_CONCURRENCY=1` settings directly implement the residency discipline C2 asks for. **[I]**
- Inspect AI's viewer answers C4's evidence-trail requirement better than promptfoo's UI (score filtering + static bundle), but its evals are Python task files: more setup than KENN needs for C1, well-fitted for sealed C4 sets. **[I]**
- A Langfuse deployment on this machine would compete with Ableton for the same RAM through ClickHouse; for a single-owner product the trace volume does not exist yet. **[I]**
- Whatever the harness, C1's existing `llm_enhanced`/count conventions (documented in KENN plan) should be mirrored 1:1 into suite rows so historical 30-question receipts stay comparable. **[I]**

### Gaps
- No harness has been run on the M3; per-call overhead, memory during grading, and UI behaviour are unmeasured.
- promptfoo's `--filter-metadata` flag is unverified this run (CSV and `file://` loading are [R]).
- DeepEval G-Eval scoring quality with a 4B-class local judge is unknown; no source publishes judge-agreement rates for small local judges.
- Whether promptfoo's grading-grouping optimisation fully serialises grader calls at `--max-concurrency 1` on all assertion types was read from docs, not run.

## Key Question 2 — Memory-system patterns (mem0, Letta, Zep/Graphiti) vs KENN's existing memory

### Takeaway
Nothing surveyed beats KENN's in-repo memory for this product, and nothing surveyed should be adopted as a dependency today. mem0 validates the pattern KENN already uses (append-only, bounded, supersede-not-edit) and is the closest to embeddable, but its marketing numbers are managed-platform numbers and its defaults are cloud models. Graphiti's validity-window model is the one conceptual upgrade worth stealing later, but its runtime prerequisites (graph DB) and its own small-model warning disqualify it now. Letta's active project is a coding agent, not a memory library.

### Cited Findings — mem0
- Licence and activity: Apache-2.0; 67,227★; pushed 2026-10-14T15:40Z; PyPI `mem0ai@2.2.1` uploaded 2026-09-25. [GitHub API](https://api.github.com/repos/mem0ai/mem0); [PyPI JSON](https://pypi.org/pypi/mem0ai/json) [V]
- April 2026 algorithm, verbatim: "**Single-pass ADD-only extraction** -- one LLM call, no UPDATE/DELETE. Memories accumulate; nothing is overwritten." Plus: entity linking ("entities are extracted, embedded, and linked across memories for retrieval boosting"); "Multi-signal retrieval -- semantic, BM25 keyword, and entity matching scored in parallel and fused"; temporal reasoning. [README](https://raw.githubusercontent.com/mem0ai/mem0/main/README.md) [V]
- The caveat that kills naive benchmarking: "Scores reflect Mem0's managed platform, which includes proprietary optimizations not available in the open-source SDK; open-source users should expect directionally similar gains but not identical numbers." Published table: LoCoMo 71.4 → 92.5, LongMemEval 67.8 → 94.4, BEAM-1M 64.1. [same README] [V]
- Defaults: OpenAI for LLM and embeddings per the project's own docs. [R] (earlier fetch this pass)

### Cited Findings — Letta
- `letta-ai/letta`: Apache-2.0, 25,151★, last push 2026-09-10; README: "## Historical source — The `archive` branch contains the retired Letta V1 API server. Existing tags and releases remain available for reproducibility, but active projects should use the current source." [README](https://raw.githubusercontent.com/letta-ai/letta/main/README.md); [GitHub API](https://api.github.com/repos/letta-ai/letta) [V]
- Active successor `letta-ai/letta-code`: Apache-2.0, 3,619★, pushed 2026-10-15T11:11Z; npm `@letta-ai/letta-code@0.34.15` (2026-10-15, Apache-2.0). [GitHub API](https://api.github.com/repos/letta-ai/letta-code); [npm registry](https://registry.npmjs.org/@letta-ai/letta-code) [V]
- Reading: letta-code is an agent application (installable coding agent), not a library surface KENN would embed. **[I]**

### Cited Findings — Zep / Graphiti
- `getzep/zep` (Apache-2.0, 4,960★, pushed 2026-10-14) is now "Examples, Integrations, & More"; the engine work lives in `getzep/graphiti` (Apache-2.0, 31,779★, pushed 2026-10-15T00:19Z). The managed Zep service is a proprietary Context Graph Engine. [GitHub API: zep](https://api.github.com/repos/getzep/zep); [graphiti](https://api.github.com/repos/getzep/graphiti) [V]
- Core model, verbatim: "Facts have validity windows. When information changes, old facts are invalidated — not deleted. Query what's true now, or what was true at any point in time." And: "Episodes & Provenance: Every entity and relationship traces back to the episodes (raw data) that produced it." [README](https://raw.githubusercontent.com/getzep/graphiti/main/README.md) [V]
- Requirements: Python 3.10+; Neo4j 5.26 / FalkorDB 1.1.2 / Amazon Neptune + OpenSearch Serverless / Kuzu 0.11.2 "(**deprecated**)"; defaults to OpenAI for inference and embeddings. [same README] [V]
- The warning that matters for a local-first product: "Graphiti works best with LLM services that support Structured Output (such as OpenAI, Anthropic, and Gemini). Using other services may result in incorrect output schemas and ingestion failures. This is particularly problematic when using smaller models." [same README] [V]
- Telemetry is on by default with opt-out env `GRAPHITI_TELEMETRY_ENABLED=false`. [R] (earlier fetch this pass)

### Cited Findings — KENN's existing memory (the incumbent to beat)
- `apps/backend/src/kenn/core/assistant_profile_memory.py`: schema `kenn.producer_preference.v1`, `MAX_PREFERENCES = 32`, `MAX_EPISODES = 64`, `VERDICTS = frozenset({"keep", "revise", "reject"})`, 11 preference keys (arrangement_preference, communication_style, creative_direction, genre, mix_priority, monitoring, preferred_device, reference_track, skill_level, sound_palette, workflow), and an active/inactive supersede pattern (`UPDATE … SET active = 0 …` before insert). [repo, read 2026-10-15] [V]
- `apps/backend/src/kenn/core/assistant_task_memory.py`: schema `kenn.assistant_task.v1`; module docstring, verbatim: "It stores validated inert plans and compact evidence identities, never hidden reasoning, arbitrary tool payloads, confirmation tokens, or raw audio." [repo, read 2026-10-15] [V]
- `session_memory.py` keeps conversational session summaries in local SQLite; preferences/tasks are separate tables by design. [R] (earlier read this pass)

### Inferences
- mem0's ADD-only discipline is the same shape as KENN's supersede pattern, with one difference: KENN keeps at most 32 preferences and 64 episodes per session, mem0 accumulates without bound. If KENN ever wants unbounded accumulation, mem0's retrieval-side design (semantic + BM25 + entity fusion) is the reference, and KENN already runs a dense+BM25 hybrid in retrieval — the fusion pattern is native. **[I]**
- Graphiti's validity windows would map cleanly onto KENN's `active` flag and `created_at` ordering if a temporal question ("what was my monitoring preference in March?") ever becomes a product requirement. Until then it is a schema idea, not a dependency. **[I]**
- Given the Graphiti small-model warning and KENN's pinned 4B local model, any Graphiti trial would need a structured-output-capable local extractor first — the XGrammar/Ollama `format` path (KQ3) is a prerequisite, and success is not guaranteed. **[I]**

### Gaps
- No source compares mem0-style memory against a bounded-supersede approach on a single-owner DAW-assistant workload; all published numbers are long-conversation benchmarks.
- KENN's preference schema has not been evaluated against mem0 or Graphiti schemas row-by-row in this pass; the mapping above is structural.
- mem0's OSS reproduction of its published numbers was not attempted.
- Whether Graphiti works acceptably with Ollama + structured outputs under KENN's model class is untested anywhere this pass.

## Key Question 3 — Structured output / tool calling status (local stack)

### Takeaway
The local stack has settled: XGrammar is the de-facto grammar engine, and — new this pass — it is already inside the runtime KENN uses. Ollama's MLX runner contains an XGrammar constraint layer (`mlxrunner/xgrammar/`), which closes lane 02's open question about whether MLX-path models honour `format` schemas. Outlines remains the Python-side option if schema objects ever need to be composed outside Ollama, and llguidance is the second engine. The `tool_choice` gap on the OpenAI-compatible surface is unchanged and still separate from constrained decoding.

### Cited Findings
- **XGrammar**: Apache-2.0; 1,960★; pushed 2026-10-14T16:20Z; PyPI `xgrammar@0.2.8` (2026-09-24). Paper (MLSys 2025): "Evaluation results show that XGrammar can achieve up to 100x speedup over existing solutions. Combined with an LLM inference engine, it can generate near-zero overhead structure generation in end-to-end low-LLM serving." [GitHub API](https://api.github.com/repos/mlc-ai/xgrammar); [arXiv 2411.15100](https://arxiv.org/abs/2411.15100) [V]
- **XGrammar inside Ollama's MLX runner** (resolves lane 02's open item): the runner carries `mlxrunner/xgrammar/native/xgrammar.cpp` (includes `<xgrammar/xgrammar.h>`, error-sanitising wrapper) and `mlxrunner/xgrammar/dynamic.c` (runtime symbol loading via `dlsym` with `compiler_new`/`matcher_new`/`matcher_fill`/`matcher_accept`/`matcher_rollback`/`matcher_is_terminated` entry points), plus `dynamic.h`. [ollama/ollama source, paths verified via code search 2026-10-15] [V]
  Implication: schema-constrained decoding exists on both Ollama runners (llama.cpp path via its own grammar engine, MLX path via XGrammar); exact acceptance/rejection parity between runners is still unmeasured **[?]** — but "does the MLX runner support `format` at all" is now answered yes.
- **Outlines**: Apache-2.0 (repo); 15,935★; pushed 2026-09-21; `outlines-core@0.2.14` PyPI (2026-01-09). Docs: "Microseconds of overhead vs seconds of retries. Compilation happens once, not every request." Open-core positioning, verbatim: "Our commercially-licensed libraries ensure 100% compliance with JSON Schema, regular expressions and context-free grammars while adding only microseconds of latency." Backends: vLLM, Transformers, llama.cpp, Ollama, MLX-LM, SgLang, TGI. [GitHub API](https://api.github.com/repos/dottxt-ai/outlines); [docs index](https://raw.githubusercontent.com/dottxt-ai/outlines/main/docs/index.md) [V]
- **llguidance**: MIT; 888★; pushed 2026-10-14 — the constraint engine embedded by several serving stacks; WATCH only. [GitHub API](https://api.github.com/repos/guidance-ai/llguidance) [V]
- **The tool_choice gap is unchanged**: Ollama's OpenAI-compatible surface does not accept `tool_choice` (lane 02 KQ2 finding); XGrammar-based constraint decoding does not change that. Schema-constrained generation ≠ forced tool selection. [lane 02 KQ2; not re-tested] [R]

### Inferences
- The practical recommendation is zero new dependencies: keep Ollama `format` as the enforcement point, and treat XGrammar's presence as the insurance that the MLX runner migration (lane 02 H5) does not silently drop schema enforcement. A single A/B that sends one required-schema request per runner and compares acceptance/failure behaviour would close the remaining [?] in under an hour. **[I]**
- If KENN ever needs grammar objects composed in Python (multi-stage planner contracts), Outlines is the drop-in; its open-core split only matters if the Dottxt paid libraries are used. **[I]**

### Gaps
- No measured schema-adherence rates for small models on KENN's runtime (same gap lane 02 recorded).
- MLX-vs-llama.cpp parity for `format` behaviour unmeasured (the layer's existence is verified, its behavioural equivalence is not).
- Whether Ollama's dynamic loading means XGrammar ships bundled or must be present on the system for the MLX runner path was not verified (loader structure implies a bundled/native build; not confirmed). **[?]**

## Key Question 4 — LoRA fine-tune tooling for the SEAL stack (S2–S6)

### Takeaway
The SEAL stack already sits on the right foundation: PEFT and the plain PyTorch stack, pinned in `requirements-training.txt`. Nothing surveyed justifies adding Unsloth or Axolotl now. The load-bearing finding is a licence: Unsloth is Apache-2.0 core + AGPL-3.0 Studio UI, so any evaluation of it must name which artefact is being used. Axolotl remains a reasonable later candidate for the GPU 0/1 training environment, but it declares NVIDIA Ampere+ / AMD hardware and defaults telemetry on — two facts that must be explicit in any trial request.

### Cited Findings
- KENN's current harness is PEFT-based (verbatim from `apps/backend/requirements-training.txt`, comments included): "# Optional offline command-model experiment dependencies." / "# Keep these out of the lightweight KENN/Ableton runtime environment." — pins: `torch>=2.1,<3`, `transformers>=4.45,<5`, `peft>=0.12,<1`, `safetensors>=0.4,<1`. [repo, read 2026-10-15] [V]
- **PEFT**: Apache-2.0, PyPI 0.21.2 (2026-10-01). **TRL**: Apache-2.0, PyPI 1.15.0 (2026-10-08). [PyPI JSON: peft, trl] [V]
- **Unsloth**: GitHub API reports licence Apache-2.0 (78,042★, pushed 2026-10-15T12:10Z; PyPI 2026.10.5, 2026-10-13, "Apache-2.0"). But the README, verbatim: "Unsloth uses a dual-licensing model of Apache 2.0 and AGPL-3.0. The core Unsloth package remains licensed under Apache 2.0, while certain optional components, such as the Unsloth Studio UI are licensed under the open-source license AGPL-3.0." [GitHub API](https://api.github.com/repos/unslothai/unsloth); [README](https://raw.githubusercontent.com/unslothai/unsloth/main/README.md); [PyPI JSON](https://pypi.org/pypi/unsloth/json) [V]
- Unsloth docs claim macOS support (training, MLX, GGUF inference) and "2× faster with 70% less VRAM" — marketing claims, not reproduced. [R] (docs fetch earlier this pass); no KENN measurement **[?]**
- **Axolotl**: Apache-2.0 (12,571★, pushed 2026-10-15T08:20Z), PyPI 0.20.0 (2026-09-30) — note the PyPI metadata carries no licence field; repo licence is the verified source. GPU requirement as published: "NVIDIA GPU (Ampere or newer…) or AMD GPU". Telemetry opt-out: `AXOLOTL_DO_NOT_TRACK=1`. [GitHub API](https://api.github.com/repos/axolotl-ai-cloud/axolotl); [PyPI JSON](https://pypi.org/pypi/axolotl/json) [V for API/PyPI; requirement + telemetry [R]]
- KENN's measured SEAL baseline (runbook, verbatim): "Ordinary SFT then completed four steps on four approved targets, with 176 training tokens, 96 target tokens, 18.06 s operation wall time and 8.55 GB peak reserved GPU memory." [KENN_SEAL_OFFLINE_EXPERIMENT.md](../../runbooks/KENN_SEAL_OFFLINE_EXPERIMENT.md) [V]

### Inferences
- At 4-step, 176-token scale, Unsloth's speed claims are irrelevant — the bottleneck is review, not training throughput; the bounded-packet design (S2/S3) fixes that. **[I]**
- Should S3/S5 grow to the 200–400-target packet, Unsloth's memory saving becomes interesting on the GPU 0/1 nodes; the honest next step is a same-hardware A/B against PEFT on one packet, pinning the PyPI wheel (core, Apache-2.0) and never installing the Studio UI (AGPL-3.0). **[I]**
- Axolotl's config-driven pipeline overlaps TRL's trainers without changing outcomes for this corpus size; it stays a candidate for later, not a swap. **[I]**

### Gaps
- No measured Unsloth-on-M3 or Unsloth-vs-PEFT numbers; no KENN run used anything but the PEFT stack.
- Whether the Unsloth PyPI wheel ever contains AGPL-3.0 Studio components was not resolved this pass (the README separates core vs Studio; the wheel boundary is [R]-level only). **[?]**
- Axolotl's exact licensing of third-party components inside its training pipeline was not audited.

## Key Question 5 — Retrieval deltas beyond lane 02 (no reranking, no embeddings here)

### Takeaway
Hybrid fusion is done: KENN already ships BM25+dense RRF, with a measured improvement recorded in the code comment. The only genuinely additive retrieval technique in this lane's scope is pre-retrieval **query rewriting** — generating the retrieval query from a follow-up before searching — which KENN currently routes (history-aware router) but does not rewrite. That is a C3/L2 experiment, not a dependency; the canonical citation is Rewrite-Retrieve-Read.

### Cited Findings
- KENN hybrid fusion, verbatim code comment (`apps/backend/src/kenn/retrieval/retrieval.py`): "# Hybrid fusion (measured 24 Sept 2026 on 253 questions: recall@4 0.966 -> 0.983 on the original fixture, 0.616 -> 0.736 on device-purpose questions that never name the device)." Constants: `HYBRID_RRF_K = 60`, `HYBRID_DENSE_WEIGHT = 2.0`, `HYBRID_DENSE_CANDIDATES = 60`; fusion at lines ~415–416 (weighted RRF sum). [repo, read 2026-10-15] [V]
- KENN does per-task model routing on the answer path — `llm_rewrite.py` header: "Multi-model routing by task: route, rewrite, paraphrase, followups" — but no pre-retrieval follow-up rewriting was found in the code paths touched this pass. [repo read + earlier grep this pass] [V]
- The technique: "Rewrite-Retrieve-Read" (Ma et al., EMNLP 2023, arXiv 2305.14283) — "We first prompt an LLM to generate the query, then use a web search engine to retrieve contexts"; "there is inevitably a gap between the input text and the needed knowledge in retrieval"; experiments "show consistent performance improvement". A trainable small rewriter is the paper's refinement; KENN would start with a prompt-only rewrite using the existing local model. [arXiv 2305.14283](https://arxiv.org/abs/2305.14283) [V]
- C3 context: corrections already dispatch to the history-aware router rather than the Live translator, and history boundaries are tested (plan receipts); the missing piece for follow-ups is rewriting the *retrieval query* from the resolved context, not the routing. [KENN_PLAN.md, C3 section, lines ~1454ff](../../../KENN_PLAN.md) [V]
- Cross-encoder reranking and embedding swaps stay in lane 02 KQ4/KQ5 by scope split; the 2 Oct spike receipt and the 13 Oct gate decision remain the authority there. [lane 02](02-local-brain-voice.md) [R]

### Inferences
- On a follow-up like "make that snare less harsh", the rewrite stage would resolve "that snare" and "harsh" into a retrieval query ("snare EQ harshness 8 kHz") before the hybrid search; the measurable win is recall on device-purpose questions where the follow-up never names the device — KENN has those fixtures and the RRF comment shows they are the weak class (0.616 pre-fusion). **[I]**
- Cost: one local rewrite call per follow-up; at ~4B-class speeds this is a sub-second addition when the model is resident, but it must be measured against the 15 s/70% gate headroom. **[I]**

### Gaps
- No measurement of rewrite-driven retrieval quality on KENN's fixtures; no M3 latency for the extra call.
- The trainable-rewriter variant (paper §3.3-style SFT) is out of scope until a prompt-only rewrite shows signal.
- Whether KENN's history-aware router output can be reused as the rewrite input without a second model call was not investigated.

## Candidate tables (capability, licence code/weights, M3 cost-fit, activity, effort, verdict)

Effort scale used in the shortlists below: **S** ≈ one sitting (<1 day), **M** ≈ multi-day with a held-out evaluation attached, **L** ≈ needs its own plan slice.

### Eval harnesses (Q1)

| Candidate | Capability | Licence (code / weights) | M3 cost-fit | Activity (2026-10-15) | Effort | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| **promptfoo** | eval runner + web UI + Ollama target & judge | MIT / n/a | Node single install; `keep_alive: 0` controls residency | 26,012★, pushed 2026-10-15; npm 0.124.1 (2026-10-08) | S | ADOPT — shortlist #1 (C1/C4) |
| **DeepEval** | pytest-native eval + Ollama judge + G-Eval metrics | Apache-2.0 / n/a | Python, same venv as tests | 18,882★, pushed 2026-10-15; PyPI 4.2.9 (2026-10-15) | S | ADOPT — shortlist #2 (if pytest-first) |
| **Inspect AI** | audit-grade evals + local log viewer + static bundle | MIT / n/a | Python; viewer 127.0.0.1:7575 | 3,008★, pushed 2026-10-15; PyPI 0.3.280 (2026-10-14) | M | SHORTLIST #3 (sealed C4 evidence) |
| Ragas | RAG metric library | Apache-2.0 / n/a | Python | **dormant**: push 2026-02-24; PyPI 0.4.3 (2026-01-13); 637 open issues | — | AVOID as gating harness |
| Langfuse (self-host) | trace store + annotation queues | MIT outside `ee/`; enterprise inside | 5 services incl. ClickHouse | 35,857★, pushed 2026-10-15 | L | WATCH (volume doesn't exist yet) |

### Memory systems (Q2)

| Candidate | Capability | Licence (code / weights) | M3 cost-fit | Activity (2026-10-15) | Effort | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| mem0 | append-only preference/fact memory | Apache-2.0 / n/a | SDK light; defaults OpenAI models | 67,227★, pushed 2026-10-14; PyPI 2.2.1 (2026-09-25) | M | WATCH — patterns > dependency |
| Graphiti | temporal knowledge graph | Apache-2.0 / n/a | needs Neo4j/FalkorDB; extraction quality risk on small models | 31,779★, pushed 2026-10-15 | L | AVOID for now (infra + small-model warning) |
| Letta (V1 server) | agent memory service | Apache-2.0 / n/a | retired | last push 2026-09-10; README "Historical source" | — | AVOID |
| letta-code | agent application | Apache-2.0 / n/a | npm; application, not library | 3,619★, pushed 2026-10-15; npm 0.34.15 (2026-10-15) | — | n/a (not a memory library) |
| **KENN profile/task memory (in place)** | bounded prefs, verdicts, inert plans | in-repo | zero new deps | active in repo | — | KEEP — already the right pattern |

### Structured output (Q3)

| Candidate | Capability | Licence (code / weights) | M3 cost-fit | Activity (2026-10-15) | Effort | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| **XGrammar** | grammar engine | Apache-2.0 / n/a | already inside Ollama's MLX runner path | 1,960★, pushed 2026-10-14; PyPI 0.2.8 (2026-09-24) | S (verify parity) | ADOPT via Ollama (no new dep) |
| **Ollama `format` (incumbent)** | runtime schema enforcement | MIT runner / n/a | zero new deps | Ollama stable v0.40.4 line | S | KEEP — primary path |
| Outlines | schema→FSM layer over many backends | Apache-2.0 (open-core) / n/a | Python dep | 15,935★, pushed 2026-09-21; outlines-core 0.2.14 (2026-01-09) | S | WATCH (Python-side composition) |
| llguidance | grammar engine | MIT / n/a | embedded by serving stacks | 888★, pushed 2026-10-14 | M | WATCH |

### Training tooling (Q4)

| Candidate | Capability | Licence (code / weights) | M3 cost-fit | Activity (2026-10-15) | Effort | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| **PEFT** | LoRA/adapters | Apache-2.0 / n/a | already pinned in SEAL env | PyPI 0.21.2 (2026-10-01) | — | KEEP |
| **TRL** | SFT/DPO trainers | Apache-2.0 / n/a | Python; GPU 0/1 for runs | PyPI 1.15.0 (2026-10-08) | S | KEEP |
| Unsloth | faster LoRA + MLX claims | Apache-2.0 core / AGPL-3.0 Studio UI (dual) | macOS claims unverified; SEAL unmeasured | 78,042★, pushed 2026-10-15; PyPI 2026.10.5 (2026-10-13) | M | WATCH (licence split) |
| Axolotl | config-driven trainer | Apache-2.0 / n/a | publishes NVIDIA Ampere+/AMD requirement; telemetry opt-out | 12,571★, pushed 2026-10-15; PyPI 0.20.0 (2026-09-30) | M | WATCH (not for SEAL as-is) |

### Retrieval deltas (Q5)

| Candidate | Capability | Licence (code / weights) | M3 cost-fit | Activity (2026-10-15) | Effort | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| **Hybrid RRF (in place)** | BM25+dense fusion | in-repo | zero cost | measured 24 Sep 2026 (receipt in code comment) | — | KEEP — no work remains |
| Query rewriting (pre-retrieval) | rewrite-before-search | technique — no dependency | one extra local LLM call per follow-up | arXiv 2305.14283 (EMNLP 2023) | S/M | TRIAL (C3/L2) |
| Cross-encoder rerank | — | — | — | — | — | lane 02 KQ4 owns this; not revisited |

## Ranked shortlists mapped to C1–C5 / S2–S6 / L2 / L4, with first steps

### C1 — current-path baseline (native phase telemetry, repeatable runs)
1. **Adopt one harness for the next 30-question run.** promptfoo first: YAML suite, `ollama:chat:*` target, `-j 1`, `keep_alive: 0`, `PROMPTFOO_ASSERTIONS_MAX_CONCURRENCY=1`; rows mirror the existing C1 counters/IDs. **Effort S.** [Ollama provider doc](https://raw.githubusercontent.com/promptfoo/promptfoo/main/site/docs/providers/ollama.md)
2. DeepEval instead if the suite belongs in pytest (`deepeval set-ollama` first). **Effort S.**
3. Keep C1's "one run, no repeat" limitation visible in every export until repeats exist; the harness makes repeats cheap, it does not make them happen. **Effort S.**

### C2 — remove measured wasted work (eval-time residency is part of it now)
1. When evals run alongside a KENN session, always set `keep_alive: 0` on the eval's Ollama providers and confirm with `ollama ps` — the docs' own warning covers KENN's exact failure mode (two models resident after serial runs). **Effort S.** [same doc]
2. No other C2 delta is proposed here; lane 02 owns runtime/model work.

### C3 — five-turn conversation qualification (anaphora, corrections, follow-ups)
1. **Prompt-only query rewriting trial for follow-ups.** Resolve the follow-up against session context, rewrite the retrieval query, then run the existing hybrid search; measure recall on device-purpose fixtures (the class RRF showed weakest pre-fusion) and C3 acceptance. Keep routing unchanged. **Effort M.** [arXiv 2305.14283](https://arxiv.org/abs/2305.14283); [KENN_PLAN.md C3](../../../KENN_PLAN.md)
2. Reuse the C1 harness to script the C3 conversations as suite rows so the 12/30 accepted-count history (30 turns, 24 reached the model) stays comparable. **Effort S.**

### C4 — independent language and answer qualification (sealed sets, per-family results)
1. **Inspect AI for sealed runs.** Task files per family, Scores filtering per run, `inspect view bundle` as the archived evidence artefact; publish per-family correct/clarify/wrong exactly as the plan's C4 wording requires. **Effort M.** [log-viewer doc](https://raw.githubusercontent.com/UKGovernmentBEIS/inspect_ai/main/docs/log-viewer.qmd)
2. Mechanical separation: tuning suites and sealed suites live in different directories/files; the harness runs both but the export marks which is which. **Effort S.**

### C5 — quality and timing targets (six held-out wrapper rows)
1. Port the six held-out wrapper rows into the chosen harness and run them unmodified; they exist as the check, not the tuning set. **Effort S** once C4's harness exists. [KENN_PLAN.md C5](../../../KENN_PLAN.md)

### S2–S6 — SEAL (PEFT stack unchanged)
1. No tooling change: PEFT/TRL remain the stack; the harness from C1/C4 supplies S6's per-family and p50/p95 reporting. **Effort: none (zero new work).**
2. If S5/S6 grow beyond the 4-step pilot, evaluate Unsloth (core wheel only) in a same-hardware A/B against PEFT; never install Studio (AGPL-3.0). **Effort M.** [Unsloth README](https://raw.githubusercontent.com/unslothai/unsloth/main/README.md)

### L2 — retrieval and knowledge
1. RRF: nothing to add (shipped, measured).
2. Query rewriting trial (shared with C3) is the additive retrieval delta; reranker stays lane 02. **Effort M.**
3. No index rebuild implied by any of this; rewriting is query-side only.

### L4 — planner shadow qualification
1. **Runner parity check before the next shadow comparison**: send one required-schema planner-shaped request through the llama.cpp runner and the MLX runner on the installed Ollama line and compare `format` acceptance behaviour; record which runner produced each shadow trace. **Effort S.** [XGrammar paths, see KQ3 above]
2. Keep the planner shadow free of `tool_choice` assumptions (unsupported on the OpenAI-compatible surface); constrained decoding with a single-schema `format` is the available mechanism. **Effort S.** [lane 02 KQ2](02-local-brain-voice.md)

## Avoid list
- **Ragas as a gating harness** — dormant since 2026-02-24, 637 open issues; metrics library only, if at all. [GitHub API](https://api.github.com/repos/vibrantlabsai/ragas)
- **Langfuse self-host as the default trace store** — five-service stack competes with Ableton for RAM; the EE boundary (`ee/` dirs) must be kept straight if it is ever deployed. [LICENSE](https://raw.githubusercontent.com/langfuse/langfuse/main/LICENSE)
- **Graphiti runtime for KENN now** — graph DB prerequisite plus its own warning: "particularly problematic when using smaller models" for extraction. The validity-window *idea* is adoptable without the runtime. [README](https://raw.githubusercontent.com/getzep/graphiti/main/README.md)
- **Letta V1 server** — retired in place; "active projects should use the current source". [README](https://raw.githubusercontent.com/letta-ai/letta/main/README.md)
- **Unsloth Studio UI in a closed-source product** — AGPL-3.0; the Apache-2.0 core is the only usable part. [README](https://raw.githubusercontent.com/unslothai/unsloth/main/README.md)
- **Repo-level "Unsloth = Apache-2.0" statements** — incomplete for shipping decisions given the dual licence; cite the split.
- **Axolotl as the SEAL default** — publishes an NVIDIA Ampere+/AMD requirement and defaults telemetry on (`AXOLOTL_DO_NOT_TRACK=1` to opt out); heavyweight for a 4-step bounded packet. [GitHub API](https://api.github.com/repos/axolotl-ai-cloud/axolotl)
- **mem0 managed-platform scores as OSS evidence** — verbatim caveat: "proprietary optimizations not available in the open-source SDK". [README](https://raw.githubusercontent.com/mem0ai/mem0/main/README.md)
- **`tool_choice` on the OpenAI-compatible surface** — still unsupported (lane 02 KQ2); do not design around forced function calling.
- **Reading 16k★ on Ragas as health** — stars are historical; the activity columns above are the current signal.

## Verified vs inferred
**[V] Verified this run, 2026-10-15** (fetched live): promptfoo repo licence/stars/push + npm 0.124.1 licence; promptfoo Ollama doc quotes (`keep_alive: 0`, serial-residency warning, `PROMPTFOO_ASSERTIONS_MAX_CONCURRENCY` 3-default, `format` + `think: false`, grading-provider section) + getting-started Web UI; DeepEval repo/PyPI + `set-ollama` env vars and default base URL; Inspect AI repo/PyPI + providers (`ollama/llama3.1`, `OLLAMA_BASE_URL` default, `llama-cpp-python/llama3`, `emulate_tools`) + log-viewer (`127.0.0.1:7575`, Scores filter, `--no-trust-content`, `inspect view bundle`, `bundle_log_dir()`); Ragas org move, dormancy, 637 issues, PyPI 0.4.3; Langfuse root + `ee/` licence text, repo activity; mem0 repo/PyPI + README algorithm quotes and managed-platform caveat + benchmark table; Letta README "Historical source" quote + letta-code repo/npm; Graphiti README validity-window quote, provenance line, requirements (Neo4j/FalkorDB/Neptune/Kuzu-deprecated), small-model warning; zep repo description; KENN `retrieval.py` RRF comment/constants; KENN `assistant_profile_memory.py` constants/keys/verdicts; KENN `assistant_task_memory.py` docstring; KENN `requirements-training.txt` pins; SEAL runbook 4-step/8.55 GB quote; peft/trl/unsloth/axolotl PyPI versions; unsloth README dual-licence quote; XGrammar repo/PyPI + arXiv abstract; Ollama `mlxrunner/xgrammar/` file paths via code search; Outlines repo/PyPI + docs quotes; llguidance repo; Rewrite-Retrieve-Read abstract; KENN_PLAN C1–C5/L2/L4/S2–S6 line anchors.

**[R] Reproduced from earlier fetch logs in this pass, not re-fetched today**: promptfoo CSV/`file://` loading; DeepEval pytest-native + G-Eval + optional platform; Langfuse self-host service list + annotation-queues docs badge absence; mem0 OpenAI defaults; Graphiti telemetry opt-out; KENN `session_memory.py`; Unsloth macOS/MLX claims and "2× faster / 70% less VRAM"; Axolotl GPU requirement + telemetry opt-out; Ollama `tool_choice` gap (lane 02 KQ2).

**[I] Inferred (not sourced)**: all "fits the workflow" judgements; C1/C3/C4/C5/L4 experiment designs above; mem0/Graphiti mapping onto KENN's schema; rewrite-latency expectation; the claim that rewrite-driven recall would improve device-purpose follow-ups on KENN's fixtures.

**[?] Could not verify**: MLX-vs-llama.cpp behavioural parity for `format`; whether the Unsloth PyPI wheel boundary excludes all AGPL-3.0 components; whether Ollama's XGrammar loading requires system presence vs bundling; promptfoo `--filter-metadata`; DeepEval judge quality with small local models.

## Corrections vs earlier notes and lane 02 open questions
1. **Lane 02's "whether Ollama's MLX runner applies `format` schemas identically" is half-answered**: the MLX runner contains an XGrammar-based constraint layer (`mlxrunner/xgrammar/native/xgrammar.cpp` includes `<xgrammar/xgrammar.h>`; `dynamic.c` loads the API at runtime). Schema support on the MLX path is real; behavioural parity with the llama.cpp path remains unmeasured. [code search, 2026-10-15]
2. **"Unsloth is Apache-2.0" is an incomplete statement** — dual-licence (Apache-2.0 core, AGPL-3.0 Studio UI), verbatim README.
3. **Ragas is not the default answer for RAG eval anymore** — dormant since Feb 2026; the live harness choices are promptfoo/DeepEval/Inspect AI.
4. **Letta's main repo is not the active Letta** — README directs to `letta-code`; the V1 API server is retired.
5. **The Q5 "add hybrid retrieval" suggestion is dead on arrival** — RRF fusion shipped in KENN with a measured receipt (24 Sept 2026); the only additive technique in scope is pre-retrieval query rewriting.

## Facts not verified
- No harness was run on this machine: no per-call overhead, no grading-path memory, no UI checks for promptfoo, DeepEval, or Inspect AI.
- XGrammar schema-adherence rates for KENN's 4B-class models (same gap lane 02 recorded, not closed).
- MLX-runner vs llama.cpp-runner `format` behaviour parity (existence verified, equivalence not tested).
- DeepEval G-Eval judging reliability with a local 4B judge; no judge-agreement data exists anywhere in this pass.
- mem0 OSS reproduction of LoCoMo 92.5 / LongMemEval 94.4 numbers; no experiment attempted.
- Graphiti + Ollama extraction quality under KENN's model class; README warning quoted, not tested.
- Unsloth macOS/MLX training claims and any KENN-side speedup; no measurement.
- Langfuse annotation-queues licence status beyond directory placement (docs show no EE badge; code outside `ee/`; not a legal read).
- promptfoo `--filter-metadata`; promptfoo grouping behaviour under all assertion types.
- Whether KENN needs any trace store at all — a product decision, not a research finding.
