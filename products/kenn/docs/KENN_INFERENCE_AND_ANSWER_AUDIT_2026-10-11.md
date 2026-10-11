# KENN inference and answer audit — 11 October 2026

This is a dated evidence audit for Jack and Claude. `KENN_PLAN.md` remains the roadmap and work queue. The recommendations below are experiments for its existing direction, not instructions to start another programme of work.

**Source snapshot:** monorepo `main`, `20b3de3c30749bfa46dc5c658d2903a80aa8af23`. **Evidence cutoff:** 11 October, approximately 18:42 BST; v5 was still running. Source, raw benchmark summaries/metadata, tests, runtime metadata and the 2/5 October research were inspected. Existing held-out evidence was analysed in aggregate; held-out questions and answers were not made into new examples or fixes.

Only this document was added by this audit. Implementation, plans, models, indexes and runtime configuration were not changed. No inference benchmark, index rebuild, package installation or real Live write was started. A small mocked test selection passed while the existing v5 benchmark continued.

## A. Leading diagnosis and confidence

**KENN's current delivery blocker is predominantly whether it produces an acceptable grounded answer, with a smaller sustained decoding problem. Correctness remains a separate, unresolved product blocker.** Confidence is high in the delivery diagnosis and moderate in the ranking of the remaining semantic causes, because current owner grades and per-request evidence-loss judgements are missing.

The completed v4 Live-open qualification session reproduces the plan's probe **35/34/34 of 44** and held-out **48/44/43 of 72** within 15 seconds. Probe passes its three-run bar; held-out misses 51 in every run. Across the 216 eligible held-out request occurrences, 135 delivered a model answer within 15 seconds, 64 retained a fallback, 12 delivered a strict decline, and five delivered an accepted model answer late. Making those five late answers instantaneous would yield 140/216, or 64.8%, still below 70%. Speed alone cannot close this gap.

Unsupported measurements are the largest named rejection: **35 eligible held-out occurrences**, versus two attribution failures, one overlap failure, one structure failure and one final quality rejection. Six named weak/intent guards and three hardware/plugin caveats prevented generation. Fifteen other fallback occurrences have no recorded rejection reason. These classes describe delivery outcomes; they do not establish whether each rejection was necessary or mistaken.

The prompt previously introduced genre/acoustic figures that its own grounding checker refused. That is confirmed, and the fix is **already merged**, alongside a stable system prefix. The unsealed prompt-figures A/B improved delivery by roughly four answers per 36 eligible questions, but the newer v5 first probe delivered **32/44**, down from v4's 35/44. It is faster and passes that single-run bar, but has four unshown-ID rejections. Neither the A/B nor a single v5 run establishes qualification or improved correctness.

The fine-tune is the decisive warning against equating acceptance with usefulness. `kenn-answer1` increased held-out delivery from 44 to 58, but the available partly blind Claude grading found only one right answer among its 16 new deliveries, with eight wrong. **Those are Claude grades, not verified owner grades.** Jack's private grading page remains unavailable to this audit.

The smallest credible route is to finish evaluating the merged prompt work, grade the existing note-first comparison, improve relevant evidence reaching the prompt, and make the short answer/citation contract easier to satisfy. Instrument actual delivery and sustained resource costs before pursuing a backend replacement. Do not weaken grounding to get through the gate.

## Current gate, authority and provenance

### What “Step 1” means now

There are three different completion claims:

1. The architecture audit, A1–A5 in the plan, has recorded completion. It is not the current delivery qualification.
2. The local inference/delivery gate remains open. C1–C5 and the later “15 s gate path” carry the relevant work.
3. Useful, correct answers require human grading. The **8 October owner decision** says to move past treating delivery alone as the measure, leave the gate **open, not passed**, and bring back owner-graded correctness before picking it up again. The subsequent 11 October work and v5 benchmark do not rescind that condition.

Read the later entries as amendments to the old model and sequencing choices. The plan originally selected an 8B chat brain; the current qualification experiment explicitly uses the Qwen3 4B. The main checkout's default still names the 8B. A successful 4B bench would not silently authorize a shipping model change.

Sources: [acceptance targets, working method and later gate decisions](../KENN_PLAN.md), particularly the sections beginning near lines 968, 1002, 1080, 1370, 1432 and 1593.

### Exact delivery calculation

| Item | Current definition |
|---|---|
| Probe | 47 requests: 44 answer-eligible and three expected abstentions. At least **31/44** within 15 s in **three consecutive clean runs**. |
| Held-out | 75 selected cases: 72 answer-eligible and three expected abstentions. At least **51/72** within 15 s in the same qualifying session. The harness supplies four extra context-only setup turns, so raw output contains 79 rows. |
| Numerator | Eligible rows with `delivered_by == "model"` and `final_seconds <= 15`. Strict model declines do not count. |
| Denominator | All non-context-only rows with `expect == "answer"`, including rejection, fallback, busy, timeout, decline and late delivery. |
| Exclusions | Expected-abstain cases and context-only setup turns. Never exclude a difficult answer request because it failed. |
| Attempted-only metric | Separately report model deliveries / harness `model_attempted` rows after removing context-only turns. It includes expected-abstain attempts and is not a provider-call counter. |
| Conditions | M3/16 GB, mains, Live open as workload, FakeLiveBackend for engineering, no concurrent Swift/opencode build, pinned hybrid index `v-5f6964698b76`, exact response cache disabled, model purged between runs, same model/code/harness. |

The held-out case-file SHA-256 is `47abf035890974f7513a034a38cae2363b5413ed08c6df3d593d4d59e9395093`. Probe case-file SHA-256 is `b5b49c1a3759079f43c9a57149b9a81b25745c772b6b132c799cf1ec43f10296`.

The harness's broad `abstained` text flag is not the server's strict whole-reply decline verdict. Some model-delivered answers also set that broad flag. The official gate uses `delivered_by`; this audit preserves that definition. Classify the ambiguous answers during human review rather than silently subtracting them or counting them as correct.

Source: [probe harness](../tooling/scripts/probe_advanced_questions.py), `ask` near line 134 and `summarise` near line 224. It polls at 500 ms; the browser normally polls at 2,000 ms. A harness pass does not prove the final answer appeared in the actual browser within the same time.

### Results that can and cannot be called current

| Build and environment | Probe within 15 s | Held-out within 15 s | Qualification status |
|---|---:|---:|---|
| 5 Oct allowed-figures build, quiet/Live closed | 32/33/31 | 44/72 | Historical probe threshold evidence; not current Live-open qualification. |
| 8 Oct main `86f69540`, 4B, pinned index, Live closed | 32/32/33 | 44/72 | Historical matched model baseline. |
| Same 8 Oct code/index, `kenn-answer1`, Live closed | 40/39/40 | 58/72 | Delivery improvement; rejected as a product candidate after adverse grading. |
| v3, `f82d4bdd…`, pinned index, Live closed | 35/35/34 | 45/48/42 | Not qualifying; also predates the grounding-hole and excision changes. |
| **v4**, `412fc628cebefac08a34e1ce77a09fec11e5e8f5`, pinned index, Live open/mains | **35/34/34** | **48/44/43** | Completed session; probe passes, held-out fails all three. |
| **v5**, `20b3de3c…`, merged prefix/prompt-figures, same pinned index, Live open/mains | **32**, first run | Not yet complete at cutoff | Newest completed individual run; complete qualification unknown. |

There is **no verified completed qualification satisfying delivery conditions and owner correctness** in the evidence inspected.

Raw receipts are outside Git under `kenn-evaluation-data/` (in the folder beside the monorepo): `2026-10-11-gate-qualification-bench-v4/`, `2026-10-11-gate-qualification-bench-v5/`, `2026-10-10-gate-qualification-bench-v3/`, `2026-10-08-retrieval-bench/`, and `2026-10-06-answer-tune/results.md`. The latter folder contains an **8 October** experiment despite its folder date. Each v4/v5 `*.summary.json` records commit, case checksum, model, index and power; `bench.sh` and companion logs provide the invocation and workload checks.

### Checkouts and disagreements between records

The actual repository is `Nite-DSP/monorepo`; the surrounding workspace contains external evidence and multiple worktrees. The inspected relevant heads were:

| Checkout, relative to `monorepo` | Branch/state | Head |
|---|---|---|
| Main | `main` | `20b3de3c3074` |
| `workspace/worktrees/kenn/bench-v4` | Detached | `412fc628cebe` |
| `workspace/worktrees/kenn/bench-v5` | Detached | `20b3de3c3074` |
| `…/stable-prefix` | `draft/stable-prefix` | `d45536ef2a9b` |
| `…/prompt-figures` | `draft/prompt-figures` | `398546aa961a` |
| `…/figure-excision` | `draft/figure-excision` | `cf15592f97a2` |
| `…/grounding-holes` | `draft/grounding-holes` | `376b4f002929` |
| `…/excerpt-id-format` | `draft/excerpt-id-format` | `f82d4bdd6a76` |
| `…/answer-tune` | `draft/answer-tune` | `cdaaf334514b` |
| `…/stage2-stage3-integration` | `codex/kenn-stage2-stage3-integration` | `db4d027c4075` |
| `…/kenn-app-sync-check` | Detached | `9d4c0b990f76` |

Other historical checkouts include `bench-main`, `figure-evidence`, `gpu-box-wrapper`, `knowledge-misroutes`, `reasons-probe`, `session-notes` and `reactions`. Their existence does not establish that their code is running. KENN code was clean when inspected; main's plan subsequently acquired an uncommitted v5 progress entry from the active work. Unrelated product/backend changes were already present. This audit leaves them untouched.

Resolve these record differences against the raw evidence:

- The plan header's 2 October update label is older than its dated 11 October entries. Main/v5 contain the latest merged work; v4 and development worktrees retain older plan copies. Do not infer one common state from the filenames.
- v4's plan says **20** held-out cases miss all three runs. Recomputing the official condition from its 72 eligible rows per run gives **19** cases missing all three, seven missing two, ten missing one. This audit uses the raw calculation.
- The stable-prefix investigation quotes 49/354 low-cache calls. The six v4 qualification time windows yield **45/339** phase-bearing generation records with fewer than 100 cached tokens. These are different scopes; do not substitute the broader investigation sample for this qualification sample.
- The plan says 255/339 calls hit the cap. Raw phase text contains **255 `length` endings** and **257 outputs of exactly 128 tokens**. Completion reason and token count are distinct measurements.
- Earlier 11 October wording proposed a rebuilt v5 index. Later investigation deferred the reference-note rebuild, and actual v5 provenance pins **`v-5f6964698b76`**. Main's own `CURRENT` is **`v-db8c6334cf63`**. The running bench does not qualify that main index.
- The recorded 8 October kenn-app sync was monorepo `eb5a21d0` / kenn-app `bb2ada6d`. No current installed kenn-app artifact or running app build was verified. The inspected Vue source cannot establish what a separately shipped/native surface displays.

## Pipeline and effective configuration

### Confirmed path and owners

```text
request + session/turn ownership
  → deterministic Live inspection/typed-command/tool shortcuts
  → session, history, review and optional current-Live context
  → deterministic routing, topic/follow-up expansion, optional route model
  → cached index load → BM25 + MiniLM ONNX hybrid search + source/rule reranking
  → weak/intent/hardware guards → local note-based draft
  → bounded shown excerpts + specialist observations + allowed-figures prompt
  → response-cache lookup → local model admission → load/prefill/decode
  → structure + grounding + quality gates, or strict decline
  → accepted answer / re-gated excision / template fallback
  → current-turn upgrade ownership or SSE final metadata
  → client polling/replacement/rendering
```

| Stage | Source symbols and material behaviour |
|---|---|
| Request/ownership | [server.py](../apps/backend/src/kenn/server.py), `_handle_ask` around line 2700. Sanitizes request/session, begins a new turn and runs Live inspection, typed command and explicit-tool paths before knowledge synthesis. |
| Current context | Same handler around lines 2855–2898; stored session context, mix/review/classifier/stem observations, optional Live summary. These are conditional inputs, not proof every knowledge answer receives fresh Live state. |
| History/routing | [chat_routing.py](../apps/backend/src/kenn/core/chat_routing.py), `normalize_history` (70), `route_query` (1588), `search_query_with_history` (2067). Cleaned history is bounded; model prompt uses the last four turns, each capped at 900 characters. Deterministic routing comes first. |
| Follow-up retrieval | [chat_answer.py](../apps/backend/src/kenn/core/chat_answer.py), `_resolve_results_with_topic_lock` (1409), `_history_for_answer` (1453), `compact_history` (1463). Reuses evidence only when topic/query constraints allow; otherwise searches at least 16 candidates. `compact_history` is now a no-op after earlier context-loss fixes. |
| Retrieval | [chat_retrieval.py](../apps/backend/src/kenn/core/chat_retrieval.py), `search` (195), and [retrieval.py](../apps/backend/src/kenn/retrieval/retrieval.py), `hybrid_search` (333), `bm25_search` (812), `rerank_results` (1080). BM25 terms plus 384-dimensional MiniLM ONNX, fusion, source applicability and lexical/rule scoring. Dense hits now receive their own full BM25 score rather than borrowing another result's score. |
| Evidence shown | [llm_rewrite.py](../apps/backend/src/kenn/llm/llm_rewrite.py), `model_evidence` (1030), `_build_synthesis_messages` (1878). Scan first 12 results with score at least 4; up to 400 cleaned characters per excerpt and 1,200 total characters including labels. A 300-character draft and up to 900 characters of specialist observations have separate budgets. Several retrieved results never reach the model. |
| Prompt | Same builder. Source excerpts precede the draft, observations, allowed figures, conversation context and current question. Allowed-figure list caps at 12, prioritizing specialist figures. Full approved-note tails and typed-question figures accepted by the gate are deliberately not all in this list, because unseen numbers lack their supporting sentences. |
| Admission/provider | `LLMUsage` (187), `_local_model_request` (284), `_build_native_ollama_payload` (775), `_chat_completion`, `chat_completion_stream` (1443). Nonblocking local admission lock; retries only selected connection failures. Prose uses native Ollama transport with thinking disabled. |
| Checks/fallback | [chat_grounding.py](../apps/backend/src/kenn/core/chat_grounding.py) plus `make_answer` (959) and final payload quality checks in `chat_answer.py`. Numeric/source checks, evidence overlap, unasked products, claims of Live changes and final quality can reject otherwise well-shaped text. HTTP tries whole-sentence endings and narrowly excised text before retaining the template. |
| HTTP delivery | `server.py` around line 3018, [answer_upgrades.py](../apps/backend/src/kenn/core/answer_upgrades.py), `begin_turn` (60), `start` (94), `get` (177). Foreground note answer is returned immediately; a background rerun may replace it. One process-wide upgrade slot, no queue; new turns cannot publish stale answers. Superseded computation can continue to hold the slot until it finishes. |
| Browser delivery | [api/kenn.ts](../apps/frontend/src/api/kenn.ts), `askKenn` (261), sends `stream: false`; [useKenn.ts](../apps/frontend/src/composables/useKenn.ts), `waitForUpgrade` (222), waits up to 90 s, normally polls every 2 s and replaces only the owning message/turn. Actual rendering timestamps are not captured. |
| Streaming delivery | `server.py` around 2914; `_answer_payload_stream_raw` and streaming caller in `chat_answer.py`; `enhance_stream` in `llm_rewrite.py`. Provisional tokens precede the final full verdict. Early guards protect a prefix, but final rejection can replace the text. HTTP's synchronous structure/excision path is not equivalent to streaming. |
| Typed actions | [live_command.py](../apps/backend/src/kenn/core/live_command.py), `handle_command`, and [live_action_service.py](../apps/backend/src/kenn/core/live_action_service.py), `execute` (3664), `propose_undo` (3358). Session-bound confirmations, target/state checks, readback and receipt-backed inverse remain the action authority. Generated prose must not claim it performed an action. This knowledge benchmark does not qualify real-Live action safety or exact Undo. |

### Effective runtime, rather than an alias alone

The v4/v5 invocation explicitly sets `KENN_USE_MLX=0`, `AUDIO_TOO_LLM_MODEL=qwen3:4b-instruct-2507-q4_K_M`, FakeLiveBackend, background upgrades, `KENN_LLM_CACHE=0` and rejection-text exposure for private evaluation. The main product `.env` names `kenn-brain-qwen3-8b`; that is overridden in the bench process. Existing process environment wins over loaded dotenv values, whose root/order also matter.

Read-only API/process inspection during v5 found:

| Property | Observed value or limit |
|---|---|
| Provider/version | Ollama **0.40.1**, llama.cpp runner. Upstream version file pins **b11351**. v4 summaries do not pin the Ollama build, so historical version equality is unproven. |
| Checkpoint | Alias `qwen3:4b-instruct-2507-q4_K_M`, GGUF Q4_K_M, 4,022,468,096 parameters. Exact original HF/conversion revision was not recorded in benchmark receipts. |
| Manifest digest | `0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0` |
| Loaded weight blob | `85e4a5b7b8ef0e48af0e8658f5aaab9c2324c76c1641493f4d1e25fce54b18b9` |
| Template/tokenizer | Actual `/api/show` template SHA-256 `40c21f34cf67d8c760ef72f8ad3ae5afad514299d4b06e91dd9a8d705af7b541`; ChatML template with tool/reasoning branches; GGUF tokenizer `gpt2`, pre-tokenizer `qwen2`. Do not equate this with the MLX wrapper's handwritten ChatML. |
| Thinking | KENN sends `think: false`. The official Instruct-2507 card describes a non-thinking model; Ollama's generic `thinking` capability flag does not prove a separately trained thinking mode. |
| Context | Runner **4,096 tokens**, one slot. The model's advertised/trained 262,144-token context is not the active allocation. |
| Output | Prose **128 tokens**; command task cap 256. |
| Sampling | KENN prose temperature **0.35**, overriding model default 0.7. Model parameters: top-k 20, top-p 0.8, repeat penalty 1; stop `im_start`/`im_end`. KENN does not pin a seed, top-k/top-p or context in this request. |
| Residency | 30-minute keepalive plus periodic pinger; bench explicitly purges between runs, then starts/warm-ups the companion. Therefore first measured questions are not a controlled model-cold workload. |
| Runner flags | `-c 4096 -np 1 --flash-attn auto -b 512 -ub 512 --context-shift --keep 4`. “Auto” is not evidence that every kernel actually used flash attention. |
| Loaded size | `/api/ps` reports 3,175,339,786 bytes, approximately 2.96 GiB, for loaded size/VRAM. This is not total application or system memory. |

Primary sources: [Ollama 0.40.1 llama.cpp version](https://raw.githubusercontent.com/ollama/ollama/v0.40.1/LLAMA_CPP_VERSION), [versioned runner implementation](https://raw.githubusercontent.com/ollama/ollama/v0.40.1/llm/llama_server.go), [Qwen Instruct-2507 model card](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507). These identify upstream behaviour; performance figures above/below come from KENN, not an upstream benchmark.

### Three caches, three meanings

- **Exact response cache:** SQLite, default 512 entries/24 h. `_cache_key` in `llm_rewrite.py` includes provider, endpoint, model **alias**, messages and effective output contract, including thinking/sampling. It does not pin a weight digest. Replacing an alias's weights can therefore replay old text unless the cache is invalidated. The caller rechecks grounding, but revalidation cannot prove the text came from the new model. Disabled in v4/v5.
- **Semantic/session cache:** `session_memory._semantic_cache_version` includes logic and active index identity; callers bypass reuse for history, current-state/plugin evidence and unsafe/transient/proposal answers. Session isolation is present. The identity does not include model digest/prompt hash. Whole-answer reuse is not a backend throughput measurement.
- **Provider KV prefix cache:** still enabled when `KENN_LLM_CACHE=0`. Cached-prefix counts in v4 prove reuse. Stable leading tokens can reduce prefill without an exact-response hit. Evidence order/history changes still reduce reuse.

## B. Evidence table and miss diagnosis

| Finding | Classification | Evidence and implication |
|---|---|---|
| Prompt supplies figures the gate rejects | Confirmed defect, **fixed on main**, qualification pending | Plan's v4 audit found ten prompt-origin rejections among 237 raw held-out row-runs; genre guidance in 90, acoustic guidance in 24. Current `build_system_prompt` strips those figures while keeping words. Unsealed A/B is positive; v5 is incomplete. |
| Accepted-generation timing inflated by 1,000 | Confirmed current logging defect | `make_answer` passes `_ma_llm_ms` at lines 1089/1107 to `_log_generation_outcome`, whose argument is seconds and which multiplies by 1,000 at lines 1214/1216. Rejections pass seconds correctly. Do not use accepted route-row `ms` as latency; provider detail and client final clocks remain usable. |
| Global “last usage” used for timing attribution | Confirmed design uncertainty under concurrency | `_last_call_timing` reads `_global_usage[-1]`. One upgrade slot does not rule out another route/stream/diagnostic call. Request-scoped `capture_usage` already exists; use that for attribution. No observed v4 misattribution is claimed. |
| Decode grows across the session | Confirmed measurement; cause hypothetical | Held-out decode median rises 4.5 → 5.7 → 6.4 s; prefill stays approximately 1.9 s. Thermal throttling, power and memory pressure are plausible but unisolated. |
| 128-token output is frequently exhausted | Confirmed | 255/339 phase records end `length`; 257 contain 128 output tokens. Reaching the cap does not itself prove an incomplete sentence, but the historical cap receipt documents incomplete answers. Cutting to a sentence can also remove an essential step. |
| Garbled IDs remain a rejection source | Confirmed | v4 has five eligible probe unshown-ID rejections; newer v5 probe has four. Current resolver already accepts ordinals, unique hex prefixes of at least six characters and unique one-character substitutions in 12-hex IDs. Do not propose those existing fixes again or widen fuzzy matching. |
| Quantity/source applicability is weaker than value membership | Confirmed semantic limitation | Measurement union can accept a value from a typed question or any section of an approved shown note; citation verification tests whether a figure occurs in an excerpt body. Neither proves the cited number supports this recommendation or refers to the same quantity. Uncited/ambiguous claims are diagnostic, not automatic rejection. |
| Units/signs have incomplete coverage | Confirmed parser scope; frequency unknown | `_RANGE_RE`/`_MEASUREMENT_RE` cover specified units, signs and ranges, not every ratio, Q value or quantity phrasing. Decimal/integer equivalence and bounded interval integers are supported; dB/dBTP blanket equivalence has already been removed. Unicode/sign and unit-conversion cases require deterministic fixtures, not a regex relaxation. |
| Excision can preserve acceptance but alter meaning | Hypothesis requiring review, with known adversary cases | Current `salvage_unsupported_figures` removes small asides or sentences, then re-gates. Re-gating value membership/overlap cannot prove a remaining high-pass instruction or negation still means the same thing. Existing tests/adversary fixes reduce, but do not quantify, this risk. |
| Retrieval misses and evidence-window omissions | Confirmed mechanisms; latest exact class totals missing | Retrieved candidates exceed the roughly two/three shown excerpts. Synonym gaps and present-but-low-ranked sources exist in earlier studies. Do not label all 12 current declines unnecessary or all unsupported figures absent from the corpus. |
| Busy/stale delivery can cost requests | Confirmed branch behaviour; not quantified here | Global nonblocking upgrade/local generation slots decline extra work; stale turns cannot publish. Serial v4 does not measure ordinary rapid follow-ups or concurrent sessions. |
| User-visible first useful/final answer | Missing measurement | Provider TTFT, provisional SSE token, foreground template and accepted rendered answer are different events. v4 HTTP has no actual browser render or audio-dropout trace. |
| Current owner correctness/usefulness | Unavailable | Private note-first/held-out grading pages were not available. Keyword recall, quality score and grounding acceptance are not substitutes. |

### What the raw misses do and do not identify

For **216 eligible held-out occurrences**, the exhaustive final-outcome partition is:

| Final outcome | Count | Percentage |
|---|---:|---:|
| Accepted model answer within 15 s | 135 | 62.5% |
| Template/fallback | 64 | 29.6% |
| Strict model decline | 12 | 5.6% |
| Accepted model answer later than 15 s | 5 | 2.3% |

Within the 64 fallbacks, recorded reasons identify 35 unsupported-measurement rejections, nine early guards/caveats, five other generation/check failures, and 15 without a reason. Declines are separate. There were no harness errors. These are repeated requests on the same set, not 216 independent questions; do not attach an independent-binomial confidence interval to the pooled rate.

Evidence absent from the corpus, evidence missed by retrieval, evidence lost at selection, unnecessary decline, wrong-but-accepted advice and correct-versus-false grounding rejections **cannot be fully separated from these metadata alone**. That requires development-case passage judgements plus independent human answer grading. Historical refused-figure inspection found some figures already in retrieved notes and others genuinely absent; that supports selection work, not a claim that the latest held-out misses all have one cause. No new held-out question-specific analysis is required to act on that finding.

For context, the probe's 132 eligible occurrences partition into 103 timely model answers, 14 fallbacks, 12 strict declines and three late model answers. Probe performance is markedly better than held-out performance and has been tuned against repeatedly.

### Performance, with explicit samples and clocks

Per-run gate and attempted-only metrics from raw summaries:

| v4 run | Timely model / eligible | Model accepted / harness attempts | Eligible final p50 / p95, s |
|---|---:|---:|---:|
| Probe 1 | 35/44, 79.5% | 35/45, 77.8% | 6.63 / 8.17 |
| Probe 2 | 34/44, 77.3% | 36/45, 80.0% | 8.21 / 11.25 |
| Probe 3 | 34/44, 77.3% | 35/45, 77.8% | 7.95 / 11.41 |
| Held-out 1 | 48/72, 66.7% | 48/67, 71.6% | 7.19 / 11.23 |
| Held-out 2 | 44/72, 61.1% | 46/67, 68.7% | 7.72 / 13.30 |
| Held-out 3 | 43/72, 59.7% | 46/67, 68.7% | 8.46 / 12.27 |

Eligible final p50/p95 above are recalculated across all eligible requests, including immediate fallbacks. The summary's median uses all raw rows, including exclusions, and therefore differs slightly. p95 here uses sorted element `floor(0.95 * (n - 1))`. These are client/harness final clocks, not decode-only time and not browser-render clocks.

Provider phase data were recovered from `bench-v4/products/kenn/.runtime/logs/routes.jsonl`, selecting each run's UTC question window. There are **339 phase-bearing generation records**: 45 per probe and 68 per held-out run, including context setup calls. The text is rounded to 0.1 s; it is a formatted copy of native duration fields, not full-precision nanoseconds.

| v4 run | Phase n | Prefill p50/p95, s | Decode p50/p95, s | Prompt tokens p50/p95 | Cached tokens p50/p95 | `length` / `stop` |
|---|---:|---:|---:|---:|---:|---:|
| Probe 1 | 45 | 1.5 / 3.6 | 4.3 / 4.7 | 1195 / 1260 | 762 / 815 | 38 / 7 |
| Held-out 1 | 68 | 1.9 / 4.1 | 4.5 / 7.7 | 1235 / 1378 | 702 / 815 | 51 / 17 |
| Held-out 2 | 68 | 1.9 / 4.1 | 5.7 / 8.4 | 1235 / 1378 | 702 / 815 | 45 / 23 |
| Probe 2 | 45 | 1.5 / 4.0 | 6.1 / 8.4 | 1195 / 1260 | 762 / 815 | 34 / 11 |
| Held-out 3 | 68 | 1.9 / 4.2 | 6.4 / 8.2 | 1235 / 1378 | 702 / 815 | 50 / 18 |
| Probe 3 | 45 | 1.5 / 3.6 | 6.0 / 9.4 | 1195 / 1260 | 762 / 815 | 37 / 8 |

Output p50/p95 is **128/128 tokens in every run**. Load p50/p95 rounds to **0.0/0.0 s** throughout; first-run maximum load is 2.1 s and later maxima are below 1 s. Decode maxima reach 15.6 s on probe 2 and 14.9 s on held-out 2. Low-prefix-reuse calls are a prefill opportunity, but decode is the larger sustained cost.

Other timing evidence:

- Foreground template HTTP latency: **n=378, median 70 ms, p95 100 ms, max 140 ms**. Its repeated routing/retrieval is not a multi-second explanation.
- Companion phase logs show retrieval medians roughly **32–38 ms**, p95 approximately **50–55 ms**, context construction medians **3–4 ms**, and the foreground pipeline roughly **58–64 ms**. There are 47 probe phase rows/run and 78 held-out phase rows/run; a shortcut omits one held-out phase row.
- Validation was measured in the earlier 2 October experiment at approximately 1.16 ms median / 1.87 ms maximum. Current isolated validation p95 was not measured; do not relabel that historical figure current.
- Queue/admission time, exact completion-to-poll-to-render delay, first useful grounded answer, current Live audio buffer/dropouts, temperature and power limits are unmeasured. There is no evidence of accepted answers being permanently lost in v4; five arrive late.

v4 swap rises from roughly 2 GB to 3.9/4.6 GB, then stays around 4.2–4.6 GB while decode continues to slow. During v5 inspection Live was open, mains connected, Live CPU around 55%, and swap around 3.2 GiB. These snapshots establish competing workload, not a thermal diagnosis or acceptable audio performance. A warm new process, model-cold request and provider-KV-cold request must be reported separately.

## Reusing the 2/5 October research

The [2 October research](research/KENN_PRODUCT_AND_OPEN_SOURCE_RESEARCH_2026-10-02.md) and its later phase-telemetry addendum remain the useful starting point. The [5 October GLM research](research/KENN_GLM_COMPREHENSIVE_RESEARCH_2026-10-05.md) explicitly corrects its own original speed, memory and gate projections. Read that correction box before quoting its tables.

| Recommendation | Current disposition |
|---|---|
| Native phase/attempt telemetry before runtime changes | **Implemented and measured**, but accepted route-duration units, request attribution and display timestamps still need repair. |
| Stable system prefix | **Implemented but not qualified**; merged via `e3673444`, quick-fix wording included. Current first probe is faster but acceptance is lower; changed rule/directive order can affect output. |
| Prompt/grounding agreement on figures | **Implemented and measured on unsealed A/B**, merged via `def7a83c`; full Live-open/quality qualification pending. |
| Allowed-figure list, typed figures, decimal/range handling, shown-note figures | **Implemented and measured**; not sufficient to solve correctness/source applicability. Do not propose adding the list again. |
| Full-BM25 scoring for dense hits | **Implemented and measured**; previous candidate-score attribution error was fixed. |
| Broader excerpt window and synonym-weight reduction | **Contradicted as immediate defaults** by prior tradeoffs; those variants were shelved. More evidence can displace the relevant excerpt and harm generalization. |
| Repeated HTTP routing/retrieval optimization | **Measured and deprioritized**: approximately 70 ms foreground cost against seconds of decoding. Preserve the topic/session behaviour unless a new bottleneck is measured. |
| Note-first answers | **In progress**, 40-case shuffled comparison already built: 20 probe plus 20 non-held-out gap-finder cases. Owner grades pending. No need to build another pack. |
| Reference-number note/rebuild | **Deferred by later evidence**, after earlier approval to draft/rebuild. Many refused figures already occur in existing notes; v5 remains pinned. A blanket numeric whitelist would hide applicability errors. |
| Synonyms / small ONNX cross-encoder | Existing-stack synonyms are **still worth testing first**; cross-encoder conditional on remaining retrieval failures. Existing ONNX runtime is already in the backend stack; a new model/export/adapter still requires asset approval. |
| Same-checkpoint MLX versus Ollama | **Still worth testing conditionally**, after wrapper correctness and matched provenance. Current MLX default is Qwen2.5 1.5B, so it is not an equivalent 4B backend comparison. |
| Speculative decoding | **Deferred** until a suitable tokenizer/checkpoint-compatible draft and full memory budget are demonstrated. An upstream feature is not evidence this runner is using it. |
| Fine-tuning | Existing tune **measured and rejected** on available grading. Further work requires correct owner-reviewed targets and a clean evaluation, not lower loss alone. |
| MoE / Kev routing | **Parked**. Active parameters describe compute, not resident weights; the 5 October corrected DeepSeek estimate is around 8–9 GB before the rest of the system. Kev's task/model and Mac latency are not established KENN gains. |

Associated local research records include [3 October speed research](evidence/KENN_SPEED_RESEARCH_2026-10-03.md) and [Claude cloud research context](evidence/KENN_CLAUDE_CLOUD_HANDOFF_2026-10-03.md). The private [note-first grading artifact](https://claude.ai/artifact/G3A5dmySDgPnwLErYqLzrt) and [answer-tune owner grading artifact](https://claude.ai/artifact/FaMTQoNEq7Y74wdPSJRAmh) are identified by the plan/raw write-up but were unavailable. Their contents and grades are not assumed. An independently retrievable original cloud research transcript was not found beyond the local research records.

### Runtime questions that need a fair experiment

`mlx_inference_engine.py` currently defaults to `mlx-community/Qwen2.5-1.5B-Instruct-4bit`, selects cached snapshots by modification time, formats ChatML manually and keeps a singleton model. Its 2,048 MB setting calls the allocator **cache limit**, not a hard cap on weights plus KV plus process RAM. Its token estimates do not match native Ollama phase counts.

There is also a concrete cache-contract concern: `pin_system_prompt` pre-fills a prefix via a one-token generation; later `generate`/`stream_generate` passes the **whole prompt** again with that populated cache. The [versioned MLX-LM implementation](https://raw.githubusercontent.com/ml-explore/mlx-lm/v0.31.3/mlx_lm/generate.py) updates supplied caches with supplied prompt tokens. That makes duplicate-prefix state a source-backed inference requiring a cached-versus-uncached equivalence test; it is not a measured current Ollama defect. The pin operation's generated token also needs accounting. Do not benchmark this wrapper as equivalent until token/template/cache contracts are verified. Do not run `test_mlx_inference.py` casually: several tests perform real model inference.

For memory scale only, this 4B's 36 layers × eight KV heads × 128 head dimensions × key/value × two bytes × 4,096 tokens is approximately **576 MiB of f16 KV storage**. This is a calculation, not observed allocation; actual cache type/buffers differ. A draft adds its weight file, its own KV and buffers alongside Live, the main model, embedding runtime and macOS. No suitable draft or measured acceleration has been established, so there is no defensible speedup percentage to quote.

## C. Five highest-value improvements, ranked

All five preserve grounding thresholds, session isolation and typed action ownership. Proposed implementation is not authorized by this audit document itself. Follow the plan's one-change/review/keep-or-revert process and record results there.

### 1. Finish qualifying the already merged prompt/evidence alignment

**Why first:** a confirmed prompt-origin contradiction accounts for about three held-out rejections per run in the previous study. The unsealed A/B showed a real delivery gain without adding memory or a runtime. It is already being tested, so the smallest action is to finish that work rather than duplicate it.

**Area/change:** `llm_rewrite.build_system_prompt`, `_build_synthesis_messages`; preserve removal of genre/acoustic numbers and the reviewed stable-prefix/quick-fix wording. No further change during v5. After completion, separate gains/losses in development cases and owner-grade answer pairs; prefix order and figure removal are two mechanisms even though v5 contains both.

**Expected effect:** fewer self-induced unsupported figures; shorter prefill on route/mode changes; negligible extra memory. Correctness benefit remains a hypothesis. Unsealed A/B acceptance rose from 21/36 and 20/36 to 24/36 and 25/36; median final times overlapped. First v5 probe is 32/44, median 6.15 s, 32/45 attempted acceptance, no late model answers, four ID and three measurement rejections.

**Verify/experiment:** commands V1 and Q below; consume the running benchmark, do not start a competing one. For follow-up A/B, use the probe plus non-held-out development pool, randomize order, freeze the prompt before qualification.

**Success:** full unchanged delivery bars plus owner grades at least as good as baseline, with no new wrong actionable advice. A prefill gain alone is insufficient. **Rollback:** semantic/format/decline regressions or lower independent usefulness; compare prefix and figure changes separately before deciding what to revert. **Dependencies/approval:** no new assets; this work was already requested/merged. Owner correctness remains required.

### 2. Improve passage selection before adding a retrieval model

**Why second:** the model can only ground an answer in the small window it sees. Earlier retrieval/figure studies show present evidence being missed or cut; current declines and early guards cost more opportunities than late answers. Their exact false-decline fraction is unknown.

**Area/change:** `chat_routing.search_query_with_history`, `chat_retrieval.search`, `retrieval.hybrid_search/rerank_results`, and `llm_rewrite.model_evidence`. Start with the existing synonym work and non-held-out passage judgements. Distinguish absent note, wrong ranking, and omitted sentence. Prefer a query-relevant supported sentence within the existing budget over blindly expanding the window. Any prompt/grounding selection change must use the **same returned `shown` list** on both sides.

**Expected effect:** better supported answers and fewer unjustified declines; ranking cost should remain small. No quantified delivery gain is promised. Wrong source applicability, instrument or Live-version matches can worsen advice even when recall improves.

**Verify/experiment:** V2 and R below. Keep weak/unanswerable and topic-switch cases in development; record judged passage support, not title matches only. Test a cross-encoder over the top 12 only if these changes leave a demonstrated ranking gap.

**Success:** the existing conditional reranker criterion is at least **+0.05 recall@4** or **20% fewer retrieval-caused failures**, no applicability regression, incremental p95 at most 150 ms and added peak memory at most 250 MB. Also require downstream human usefulness not to fall. **Rollback:** more unrelated source/instrument spill, false answers replacing appropriate declines, or budget failure. **Dependencies/approval:** synonyms use the existing stack. New ONNX model/export assets and adapter need approval; no new vector database is justified. Do not rebuild the index on this Mac or silently alter the pinned gate index.

### 3. Make citations and the 128-token answer contract easier to complete

**Why third:** newer v5 has four garbled-ID rejections, while three-quarters of v4 generations end at the cap. The present design spends tokens reproducing hashes and answer structure. Fuzzy-ID relaxation and sentence excision can improve acceptance without improving advice.

**Area/change:** first trial **explicit short ordinal citations** in `model_evidence` and `_build_synthesis_messages`, using the resolver's existing bounded ordinal mapping and keeping canonical IDs in displayed source metadata. Couple labels and final verification; do not broaden what an unresolved citation can mean. Separately trial a concise complete Short answer plus two actionable steps within 128 tokens, retaining the existing headings and synthetic source ownership. These are two isolated experiments, not one mixed patch.

**Expected effect:** fewer copying errors and more complete advice with less decode work; no new model RAM. Both benefits are hypotheses until tested. A shorter response that loses the causal explanation, essential caution or useful step is a regression. A `stop` ending by itself is not a quality grade.

**Verify/experiment:** V3; unsealed matched A/B with completion reason, actual tokens, complete-step judgements, citation agreement and owner grades. Include ambiguous ordinals, numbers from the wrong excerpt, negated instructions, quantities with matching scalar values and source IDs that cannot resolve.

**Success:** fewer unshown/misattributed citations and incomplete answers, equal or better human usefulness, no newly accepted wrong quantity/source claims, and improved final latency if token count falls. **Rollback:** any wrong citation mapping, missing instruction/caution, or acceptance gained by deleting meaningful content. **Dependencies/approval:** no new dependencies. Owner/reviewer agreement on answer contract changes; keep the 128-token cap and protected regex/thresholds fixed unless separately approved. Excision is already present; do not sell it as a new semantic solution.

### 4. Grade the existing note-first pack, then conditionally serve useful notes

**Why fourth:** note-first has a direct low-latency path for facts already authored in notes and avoids generative invention. The existing 40-case pack is waiting for the decisive input. Relevance and follow-up understanding remain risks; a correct note can still fail to answer the producer.

**Area/change:** existing note-first pack/scorer, then `make_answer`/HTTP answer path only after grades justify it. Start with plain knowledge requests whose retrieved note directly answers the question. Preserve current session observations, follow-up context, out-of-scope declines and typed proposals. Do not route all session-dependent questions through a generic note.

**Expected effect:** potentially useful answers close to foreground latency without generation residency/cost. **The measured 70 ms median is today's template path, not a qualified note-first implementation or correctness result.** The research's >90% acceptance/zero-swap projections are not measurements.

**Verify/experiment:** grade the existing shuffled 20-probe/20-non-held-out pairs Right=2, Partly=1, Wrong=0; join grades with `2026-10-11-note-first-pack/note-first-key.json`. V4 protects follow-up, turn and action boundaries. Then report note delivery, model delivery and time-to-useful-answer separately.

**Success:** per the owner decision, note-first grade total at least today's answer total; additionally inspect wrong actionable advice and topic/context losses rather than relying only on the total. Demonstrate benefit on fresh questions before broader routing. **Rollback:** generic irrelevant notes, lost session-specific facts or worse usefulness. **Dependencies/approval:** owner grades and explicit decision about whether/how note delivery counts. Under the current gate it is not a model answer; do not change the denominator or numerator to claim a pass.

### 5. Repair timing attribution, then test sustained Live-fit runtime changes

**Why fifth:** five held-out answers are late and decode slows across the session, but improving speed cannot solve the dominant answer gap. Reliable clocks and measured resource impact are prerequisites to choosing a runtime.

**Area/change:** correct seconds/milliseconds at `make_answer` → `_log_generation_outcome`; replace global-last attribution with existing request-scoped usage; add generation-done, poll-received and render-complete timestamps to upgrade/client instrumentation. Preserve privacy by logging IDs, timings and outcomes, not user text. These are bounded telemetry fixes; test them individually.

**Expected effect:** telemetry accuracy, then a measurable p95 benefit if sustained decode/resource contention is reduced. No speed gain is claimed from the logging fix itself. Preserve one local generation slot initially; increasing slots/context can raise KV/memory and harm audio.

**Verify/experiment:** V5, then matched process-cold/model-cold/provider-KV-cold/warm trials after active v5 finishes. Keep mains/Live workload/buffer/model/index/output/sampling fixed. Log memory pressure, swap, decode slope and owner-observed audio interruptions. A declared cooldown is a separate experiment until approved; do not retrofit it into qualification receipts.

Only then trial Ollama versus MLX with **equivalent Qwen3-4B-Instruct-2507 lineage**, explicit revisions/tokenizer/template/sampling, equal evidence and 128-token budget. First prove MLX cached/uncached prompt equivalence and no silent provider fallback. Report quantization differences rather than calling them identical. Speculation follows only a compatible draft and complete resident-memory estimate.

**Success:** actual accepted-rendered p95 improves across sustained runs without reduced human quality, more busy/stale losses, growing pressure or audio interruption. Final qualification still uses the unchanged gate and correctness requirements. **Rollback:** a latency win bought by a different model/task, cache replay, thermal reset, lower quality or audio/memory regression. **Dependencies/approval:** telemetry can use existing facilities. MLX/draft assets, any installation, resource-policy change or changed qualification conditions need owner approval. Only GPUs 0/1 may be used for authorised remote work.

## D. Concrete experiment sequence and verification

This is a proposed sequence within the existing plan, not work performed by the audit.

1. **Let active v5 finish.** Preserve the bench source, plan amendments, exact index/model/template/provider identity and conditions. Record all six runs, not the best one. Stop qualification if workload/power/build/index conditions become invalid; retain the failed/invalid receipt with its reason.
2. **Reconcile delivery with human judgement.** Obtain the existing note-first grades and relevant owner correctness grades. Grade on correctness, relevance, completeness, supported quantities, source applicability and wrong actionable advice. Keep old held-out aggregates as regression evidence; do not inspect them to choose new prompt examples or per-case rules.
3. **Run one development intervention at a time.** Prompt alignment is already in v5. Next try existing-stack retrieval, ordinal citation, then concise answer wording in separate A/Bs; note-first wiring is conditional on its grade result. Use the probe and non-held-out gap-finder pool. Stop/revert at the first safety, session isolation or usefulness regression; do not rescue a failing experiment by relaxing the checker.
4. **Fix clocks before backend claims.** Capture scoped native usage and actual display times; add a deterministic unit test for the 1,000-fold bug and cancellation/busy attribution. Run resource trials only after the active session finishes. Reject backend comparisons with different checkpoints, templates, task caps or unreported fallback.
5. **Freeze before independent qualification.** After development, run the unchanged delivery qualification and a fresh independent graded set. The plan's initial chat-usefulness target is at least 90% useful supported answers on at least 150 independent cases, with sealed correctness at least 95%. The wider natural-language target is at least 95% on 500 fresh blind phrasings from at least three authors/two reviewers, with zero wrong actionable plans. Do not imply that a 40-case comparison closes those targets.

### Commands and their boundaries

Commands below are existing scoped checks or baseline tools, unless explicitly marked as candidate work. Run CPU-heavy/model checks sequentially and after active qualification. Use the checkout for the candidate, never another worktree's `.env`/index by accident.

From `monorepo/products/kenn/apps/backend/src`:

```sh
# V1: prompt transport, prefix, figures and cache/usage contracts.
env PYTHONDONTWRITEBYTECODE=1 KENN_LIVE_BACKEND=fake KENN_LLM_CACHE=0 \
  ../.venv/bin/python -m pytest -q -p no:randomly -p no:cacheprovider \
  kenn/tests/test_prompt_prefix_reuse.py kenn/tests/test_prompt_figures.py \
  kenn/tests/test_llm_usage_telemetry.py kenn/tests/test_llm_cache_key.py

# V2: existing retrieval behaviour and evaluator accounting.
KENN_LIVE_BACKEND=fake ../.venv/bin/python -m pytest -q -p no:randomly \
  kenn/tests/test_retrieval_ranking.py kenn/tests/test_retrieval_mode_evaluation.py \
  kenn/tests/test_precedence_effect_retrieval.py

# V3: both ends of measurement/citation selection, short endings and excision.
KENN_LIVE_BACKEND=fake ../.venv/bin/python -m pytest -q -p no:randomly \
  kenn/tests/test_claim_citation_grounding.py kenn/tests/test_figure_evidence.py \
  kenn/tests/test_allowed_figures.py kenn/tests/test_end_on_a_whole_sentence.py \
  kenn/tests/test_salvage_unsupported_measurements.py

# V4: history and turn ownership around any answer-path change.
KENN_LIVE_BACKEND=fake ../.venv/bin/python -m pytest -q -p no:randomly \
  kenn/tests/test_history_boundaries.py kenn/tests/test_answer_upgrades.py \
  kenn/tests/test_answer_upgrade_context.py kenn/tests/test_live_command.py

# V5: admission/cancellation/phase accounting; add the proposed unit regression first.
KENN_LIVE_BACKEND=fake ../.venv/bin/python -m pytest -q -p no:randomly \
  kenn/tests/test_llm_usage_telemetry.py kenn/tests/test_llm_cache_key.py \
  kenn/tests/test_stream_request_delivery.py kenn/tests/test_stream_cancel_work.py
```

Only **V1 was executed during this audit: 95 passed in 0.44 s**. It uses mocked providers/temporary caches and performed no model inference or real Live work. No pre-existing failure was observed in that selection. Other tests and full-suite claims in the plan are historical, not rerun here. Full-suite verification is required later for shared entry-point changes, according to the plan.

From `monorepo/products/kenn`, existing retrieval baseline R:

```sh
KENN_LIVE_BACKEND=fake apps/backend/.venv/bin/python \
  tooling/scripts/evaluate_retrieval_modes.py \
  --cases apps/backend/src/kenn/evals/device_purpose_retrieval_cases.json \
  --cutoff 4 --output /tmp/kenn-audit-device-retrieval.json

KENN_LIVE_BACKEND=fake apps/backend/.venv/bin/python \
  tooling/scripts/evaluate_retrieval_modes.py \
  --cases apps/backend/src/kenn/evals/technique_purpose_retrieval_cases.json \
  --cutoff 4 --output /tmp/kenn-audit-technique-retrieval.json
```

This tool has no built-in cross-encoder switch. Candidate work must use its injectable searcher API, preserve skipped/excluded fixtures, and add p95/memory measurement; do not invent a CLI flag or interpret median/max as p95.

Qualification Q is the existing **external** `2026-10-11-gate-qualification-bench-v5/bench.sh`, which invokes `tooling/scripts/probe_advanced_questions.py` with the ordinary probe and `--cases …/kenn-cases-300.json --only-file …/kenn-heldout-ids.txt`. It is currently running. Do **not** rerun it alongside itself. For a later frozen candidate, reproduce its explicit environment, pinned index, purge/warm-up sequence and workload conditions in an owner-approved isolated bench; record a new output directory and source snapshot. The user-facing gate is still `overall.gate_model_within_15s`, not raw `delivered_by_model`.

Aggregate reproduction requires only metadata: load each v4 `*.jsonl`, retain `expect == "answer"` and not `context_only`, count the official condition, and group remaining rows by `delivered_by`/`rejection_reason`. For persistence, count case IDs missing that condition across the three runs. For phase tables, parse only generation details in these UTC windows on 11 October: probe1 15:07:25–15:14:10; heldout1 15:14:45–15:26:54; heldout2 15:27:29–15:40:16; probe2 15:40:51–15:48:56; heldout3 15:49:31–16:02:53; probe3 16:03:28–16:11:27. This avoids later ad-hoc provider calls sharing the same route-log file.

## E. Remaining owner decisions and unavailable evidence

- **Correctness:** provide/complete the existing private grades. The raw fine-tune write-up explicitly attributes the reported 33%/26% right and 17%/28% wrong figures to partly blind Claude grades over differing answers. Jack's grades are authoritative and have not been verified here. Do not promote `kenn-answer1` on delivery or training loss.
- **Note-first:** grade the existing 40-case pack, decide permissible routing and whether note delivery has any separately named metric. Preserve the current model-only gate until that decision is explicit.
- **Evaluation independence:** repeated held-out exposure and documented fixes prompted by two held-out cases have weakened the current set's independence. Training substring checks do not prove topic/template independence. Even the remaining 70 eligible cases are not a fresh holdout; an aggregate excluding the two exposed cases is only a sensitivity analysis, not a new pass definition. Commission fresh questions/reviewers, seal them before tuning, and keep the old set for regression.
- **Shipping identity:** decide whether the 4B candidate replaces the plan's 8B shipping choice, which index ships, and which app/backend artifact is qualified. Bench-v5's pinned old index does not qualify main's newer `CURRENT` or an unverified kenn-app/native build.
- **Workload:** approve any declared cooldown or changed runtime/resource policy separately. Record actual Live buffer/audio interruptions during supervised workload qualification. More slots, longer context, forced flash attention, KV quantization and speculative draft residency are experiments, not harmless defaults.
- **Assets/dependencies:** approve exact MLX conversion/tokenizer revisions or an ONNX cross-encoder/draft only after the existing-stack experiment justifies them. No installation, CI, permission or deployment change was made here.
- **Real product journeys:** schedule owner-supervised current-session and Apply/readback/Undo checks. FakeLive knowledge scores do not prove the assistant understands fresh LUFS/true-peak/crest observations, selects the right track/device, applies an exact intended action, or restores it. No real writes belong in daily engineering tests.

**KENN is becoming more useful when fresh independent reviewers find more correct, relevant, complete and supported answers; producers receive those answers promptly under sustained Live workload; follow-ups preserve the right facts; and inspectable typed proposals apply/read back/undo exactly without unauthorized writes.** A higher delivery score from suppressing declines, removing meaningful advice until it passes, accepting numbers without their quantity/context, copying the benchmark, changing exclusions, using cache hits or counting note delivery as model delivery can raise the scoreboard while leaving the product worse. Keep those distinctions visible in every receipt.
