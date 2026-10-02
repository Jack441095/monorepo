# Codex handoff prompt

Paste everything below the rule into a fresh Codex session rooted at the repository root
(the directory that contains `monorepo/`).

The refactor state and method live in
`monorepo/products/kenn/docs/REFACTOR_HANDOFF_2026-10-02.md`. Read that too — it is the
authoritative record of what was split, the extraction method, and the per-item detail.

---

You are picking up KENN, an Ableton Live assistant. Backend:
`monorepo/products/kenn/apps/backend/src/kenn`. Another agent worked on it and stopped at a
deliberate handover point. **Every number below was measured on this machine, and where a
number is a single sample rather than a distribution it says so.**

## The goal

Get KENN's answer quality to a solid **90% acceptance, with latency kept low**.

Read this first, because it changes what "90%" means. Acceptance is currently **76-79%**,
measured at **n=29**, and **n=29 carries ±15 points** — two runs of identical application
code (9800a9e8 and a292dd4f) gave 23/29 then 22/29 accepted, and the completion median read
17.74 s then 21.74 s on the same code. **At n=29 you cannot tell 90% from 75%.** So the
goal is not "hit a number"; it is "build the thing that lets you know the number, then move
it." The sequencing below is ordered by that constraint.

The diagnosed failure is **provenance, not knowledge**: the 8B model invents measurements
that were never in the retrieved notes (`2 dB`, `48 kHz`, `0.5 Hz`) and answers anyway when
the notes do not support an answer. So the work is verification, grounding, and citation,
**not** chat quality and **not** model choice. Do not re-litigate the model swap; it is
closed on this hardware.

Latency: **TTFT is the only low-variance signal** — median 3.18 s, p95 5.04 s, against a
complete-answer median of 21.74 s. Quote TTFT for latency work. Anything you add on the hot
path must be justified against that, and the cheapest verification signals (logprobs,
conformal thresholds) are free or near-free for exactly that reason.

## Where we are

Branch `kenn-refactorisation`, three commits past `main` at `d15d199b`:

| Commit | What |
|---|---|
| `91b1b255` | Split the MCP intent router. `_dispatch` 1900 lines → 1 branch, `mcp_facade.py` 3542 → 1491, 14 handler modules + a 108-line registry. 129 tests. |
| `ce02289b` | Split `live_intent` rule parsing. `_parse_request_rules` 1241 lines → 484-line driver + 4 stage modules, `live_intent.py` 3938 → 3198. Pinned by a 384-row corpus replay generated from the **pre-split** source. |
| `526ba712` | **Fix a live crash.** `_answer_payload_stream_raw` read `answer_mode` before the line that assigns it, so any clarify-routed query ("make it better", "fix it", "can you help") raised `UnboundLocalError` **after the SSE headers were sent** — a stream that opened and silently stopped. Pre-existing at `d15d199b`; the fix mirrors the non-streaming sibling and adds `answer_mode: str = ""`. Regression test included. |

Baseline after `526ba712`: **3062 passed, 2 failed, 5 skipped** in ~104 s
(`python3 -m pytest -q -p no:randomly` from `apps/backend/src`). Both failures are
**pre-existing and expected — do not "fix" them**: `test_kenn_command_pilot::…preserves_artifacts`
(environmental, huggingface connection) and `test_live_command::test_llm_plan_gets_one_structural_repair_attempt`
(order-dependent, passes in isolation).

**A WIP branch `wip-chat-stream-split` holds an unfinished extraction** of
`chat_answer._answer_payload_stream_raw` (2 stages, `chat_answer_stream/`). It is marked
**do not merge**: its own characterisation fixture fails 8 of 8 `llm_stream_*` scenarios
deterministically (all `allow_llm: True`; the 12 non-LLM scenarios pass), and its reported
green could not be reproduced. The extraction may be sound with a broken fixture, or it may
be a real regression — unresolved. The strongest hypothesis: commit `d15d199b` shows the
LLM path needs model config the tests must set, and the fixture was baked without it. Do
not trust it; do not discard the method. Item 3a (`live_command._handle_command_impl`, 786
lines, 120 branches), item 4 (`live_action_service.execute`, 613 lines, the OSC write path),
and item 5 (delete 5 verified-dead tool functions, 71 lines) are **deliberately deferred**,
not forgotten.

## Constraints — hard rules

**Never modify, in any commit:** `ANSWER_QUALITY_MIN_SCORE`, the 0.16 overlap threshold,
`_RANGE_RE`, `_MEASUREMENT_RE`, `_measurements`.

Coupled constants that break silently: the streaming prefix guard inspects **only the first
two chunks** (changing buffered-chunk count before the first guard call is a behaviour
change); `EVIDENCE_SCAN_WINDOW = 12` is aliased by two sides (change both or neither); the
evidence gate in `core/chat_grounding.py` (`_gate_evidence_text`, `verify_claim_citations`,
`evidence_measurements`) must be untouched or fixed at **both** ends in the same commit; the
deliberate deterministic parser stays authoritative for chat-originated DAW writes.

Environment: **never write to a running Ableton Live session** — `FakeLiveBackend`, mocks,
fixtures. **One CPU-heavy process at a time** (16 GB, 4P/4E cores; load average has hit 21).
**Never `KENN_SKIP_EMBEDDINGS=1`** (misaligns the embedding matrix, degrades `hybrid_search`
to BM25-only, flatters acceptance for the wrong reason). **Never rebuild the index on this
Mac** (GPU box, GPUs 0/1 only).

Git: stage by explicit path — `products/kenn/runtime/` and `workspace/` are untracked and
**not** gitignored, so `git add .` sweeps them in. Single-line commit messages, no AI
attribution trailers.

## Hardware ceiling

Apple M3, 16 GB unified memory, 4P/4E cores. **The chat model is fixed at 8B**
(`kenn-brain-qwen3-8b`, Q4_K_M, 5.0 GB). Qwen3-30B-A3B-Instruct-2507 at Q4 needs ~18-19 GB
and does not fit; a dense 14B-Q4 fits but decodes slower than the current 133-140 tok/s.
Quality comes from architecture, not size. fp16/bf16 is emulated on Apple Silicon CPU
(~0.01x). **CoreML/ANE is actively harmful for short sequences** (queries are 10-20 tokens);
use int8 ONNX. The deliberative planner (Qwen3-4B, ~2.5 GB) is worth keeping resident:
8B + 4B is ~7.5 GB, and it holds 100% contract validity and 100% safety pass rate over 6
runs — a better track record than the chat brain.

## Do not rebuild Tier 1

Deterministic device control is **already shipped and already meets its gate**: p95 **667 ms**
against a 700 ms budget, 99.1% action accuracy, 100% parameter accuracy, 99.6% track
resolution across **294 real production commands** (`core/kenn/data/live_llm_shadow.jsonl`).
The remaining value is the tail: the top 5% of controller requests hold 59.9% of total
controller time.

## Known retrieval defect — read before proposing any reranker

Related-questions sections are indexed as chunks and win on embedding cosine to a **verbatim
query echo** (0.531), not BM25. The fix is written and tested (called fix-5) but **the index
was never rebuilt**. Two diagnoses were already tried and recorded as **false** — do not
repeat them: term density does not explain it (2.53 vs 2.46; the winner had *fewer* term
hits, 13 vs 15), and re-weighting the chunk body does not fix it at 2x or 3x (a chunk whose
body **is** the query outscores the section answering it at any weight). **No reranker,
embedder, or weighting scheme fixes this** — the matched signal is identity, not relevance.
Fixes: (a) rebuild the index with fix-5 live (GPU box), or (b) **filter those sections at
query time** (~10 lines, no rebuild, unblocks it without hardware). Index `v-db8c6334cf63`
is intact; `CURRENT` points at it. Corpus: 786 notes, chunks median 532 chars, max 5392.

## Recommended order of work

This is ordered by the n=29 constraint, and it inverts the "add a verification model first"
instinct. Models are last; measurement is first.

1. **Filter Related-questions chunks at query time** (~10 lines). Highest value per unit of
   effort, unblocks the standing item without the GPU box. Verify acceptance moves — but read
   step 2 before trusting the number.
2. **Stand up citation precision/recall measurement** (see ALCE below). You have never
   measured whether the gate is *correct*, only that it fires. Build a labelled eval set with
   citation precision and recall decomposed — **at minimum ~150 rows** to halve the ±15-point
   interval. This is the prerequisite that makes every later step falsifiable.
3. **Turn the gate into a conformal risk-controlled threshold** (see below). This converts
   "90% acceptance" from a hope into a certified bound, e.g. "under 5% of accepted answers are
   unsupported", and gives a coverage–risk curve to trade acceptance against error deliberately.
4. **Logprobs from the existing 8B** (see below). Still the only verification signal that costs
   nothing and uses the model you already run. Measure margins across the eval corpus; there is
   currently no usable threshold.
5. **Only then a verification model.** If you reach this step, prototype
   `Jev-Style-0.8B-Decision-v3-GGUF` (see below) — on the strength of its 4-bit parity result
   and context length, not its name.
6. **Phase 8 corpus growth**, on the GPU box.

## OSS research already done — do not redo it

Every parameter count, size and licence was read from the HF/PyPI API or the project source,
not recalled. Where no published latency exists it says so.

**Logprobs — the cheapest signal, and free.** Ollama's native `POST /api/chat` supports
`{"logprobs":true,"top_logprobs":N}` and it **works on this build**. Traps that invalidate
the obvious design: the **chosen token's `logprob` is 0.0 for every token** (a "sum the
logprobs" design detects nothing); `top_logprobs` **defaults to 0**; the usable signal is the
margin over the non-chosen alternatives; `logprobs` returns a **list** when `top_logprobs>0`
and a **dict** otherwise; the opening token always has a low margin (3.6-3.9), never fold it
into a claim score. Measured at **n=2 only**: value present in the note gave numeric
min-margin 17.23 / mean 31.20; value absent gave min-margin 5.59 / mean 18.57. Ranges overlap
almost entirely; **no usable threshold exists.** Logprobs are also not calibrated truth
probabilities and degrade under quantised decoding.

**Constrained decoding — do not add a library.** Ollama's `format` already accepts a JSON
schema. Libraries disqualified by reading their source: **Outlines** (its Ollama adapter is a
passthrough that explicitly rejects regex/CFG — just call `format`); **guidance** (CFG needs
local token access; over HTTP it degrades to prompting); **XGrammar** (needs logits Ollama
does not expose; repo 404s); **lm-format-enforcer** (repo 404s, local-only). Use a Pydantic
model, `.model_json_schema()`, pass as `format`, `temperature: 0`. This makes `source_id`
schema-required, which fixes citation *shape* (what the 2-of-11 measurement is currently
measuring) but **not** citation *truth*.

**Reranking — best measured option, but not blind.** `fastembed` `TextCrossEncoder` with
`ms-marco-MiniLM-L-6-v2`: 22.7M params, 22.1 MB int8 arm64 ONNX, Apache-2.0, no PyTorch.
Published p99 **49 ms for ~30 pairs on an M4 Max**; expect 2-3x on this 8-core M3. **Blocker:**
no rerank-vs-BM25 eval set, and MS MARCO relevance does not transfer to 786 personal audio
notes. **Build a 30-row eval set first.** A better embedder will not help — it scores a
verbatim query copy *higher*.

**Entailment models — all soft signals, never gates.** Nothing published a CPU latency for
any of these. `cross-encoder/nli-MiniLM2-L6-H768` (82.1M, 79.0 MB int8 arm64, Apache-2.0) is
SNLI/MNLI-only and weak on numerics — prose claims only, never numbers.
`MoritzLaurer/DeBERTa-v3-xsmall-mnli-fever-anli-ling-binary` (70.8M, 83.2 MB, MIT) has the
best-matched training data (FEVER-NLI is claim-vs-retrieved-passage) but the base model
scores only 0.777 on FEVER-NLI. Skip `typeform/distilbert-base-uncased-mnli` (no ONNX, stale).

**Stay bespoke on units and multi-turn context.** `Pint` parses units beautifully, but your
inputs are "lower the hats by 2 dB" — the part that fails is binding "hats" to a device and
"lower by" to a delta, which is slot-filling, not unit arithmetic. On coreference: "and the
release to 100 ms" is **ellipsis over a slot store you already maintain** (the
`deterministic_intent` in `core/live_command.py` carries track/device/parameter/value/unit at
99.1% agreement), not pronoun coreference — a three-line default-fill, not a neural coref
chain. `fastcoref` needs spaCy+PyTorch at ~7 s on 8 cores; `coreferee` is pinned to Python
3.6-3.10. **The one thing worth building is an explicit, inspectable `last_intent` record on
the session, surfaced in the receipt.**

## JEV — the name you were given is wrong

**"typeask" does not exist.** No AI company called TypeAsk. The real thing is **TypeSafe AI's
"Jev"** — and the name is not an acronym, it is after **William Stanley Jevons**.

- **What Jev is:** a discriminative decision model — transformer-based, returns typed values
  with probabilities (`Choice` 2-255 options, `Score` 2-10 levels, `Noul` = boolean), all
  questions scored in parallel in one pass. It does **not** generate text. Released
  **15 September 2026** by TypeSafe AI (SF, founded 2024 by Diogo Almeida, ex-OpenAI RLHF).
  Trained on synthetic data via RLCD (calibrated decisions, not rater preference).
- **Why it is disqualified for KENN:** **proprietary and cloud-only.** Reachable only through
  `TYPESAFE_API_KEY`, OpenRouter, or Requesty — no weights, no GGUF, no safetensors. KENN is
  offline. Not a close call.
- **The useful discovery:** Ollama's `POST /v1/systemone` **follows TypeSafe's Jev API**, and
  the `typesafe-sdk` can be pointed at Ollama itself. So the **interface is already local**,
  served by open-weight models, no cloud.
- **Transferable warning** (from Pydantic AI's docs, not the vendor): Jev-class models are
  weak on arithmetic/counting, degrade with irrelevant context (filter before you send), and
  treat state as data not as hostile — *"a guard built on Jev belongs alongside deterministic
  checks, not instead of them."* That last line is the correct architecture for KENN's whole
  problem.

**The open ecosystem that grew around this shape** (last ~3 weeks), ranked by fit:

- **`chaoliangUNSW/Jev-Style-0.8B-Decision-v3-GGUF`** — the one to prototype if you reach step
  5. 0.53 GB Q4_K_M, Apache-2.0, base Qwen3.5-0.8B. **Q4_K_M matches PyTorch FP32 on 240/240
  parity rows** — the specific result that de-risks its probabilities at the quantisation you
  already run. **25,600-token context** (fixes the 8,192-token cap that would truncate KENN's
  12-chunk window). 79.2% on 2,000 typed decisions; BoolQ-adjacent figures only for intent
  classification, **zero evaluation on factual verification**. **Caveats:** published latency
  is F16 on an M1 Max (treat 1,381 ms as a floor); bus factor 1; card admits some training
  rows are OpenAI/Anthropic outputs; **does not plug into Ollama** — needs its own llama.cpp
  scorer process (logit access Ollama does not expose).
- **`com-kotobalabs/open-jev-deberta-v3-large`** — the most rigorous documentation in the
  space (0.854 in-domain / 0.690 OOD, ECE 0.022, BoolQ 0.879) but **512-token context
  truncates KENN's largest chunks** and 1.8 s fp32 on M1 Max. Wrong for KENN.
- **`bespokelabs/Bespoke-Nimble-9B`** — most-liked (225), Apache-2.0, but a 165 MB LoRA over
  Qwen3.5-9B (too heavy). **`togethercomputer/Tev1-{0.8B,4B}`** — the "0.8B" is actually
  873M params, "4B" is 4.66B. **`TypeSafeAI/Qyvos`** — official org, 2 days old, no licence,
  0 likes; watch, don't adopt.

**Search-hygiene warning:** an HF search for `jev` returns heavy name-collision noise
(`JEV-27B-VL`, `JevK5`, `jevify-gemma4-*`). None are TypeSafe's Jev. Do not let anyone hand
you one of these.

## Two categories the first survey missed — the actual bottleneck

Both are bigger than any single model.

**1. Conformal risk control / selective prediction — the highest-value gap.** Your gate is a
fixed threshold. Every verification model returns a probability, and "calibrate the threshold
on your own corpus" is the unsolved part. **Conformal Risk Control / Learn-then-Test**
(Angelopoulos et al., arXiv:2110.01052) turns threshold selection into hypothesis testing with
**finite-sample guarantees** — "at this threshold, under 5% of accepted answers are
unsupported" — plus a coverage–risk curve. OSS: **MAPIE** (v1.3.0). Cost: ~a day, no new
model, no new MB. Caveat: guarantees need the calibration set to be exchangeable with
production; editing your notes will violate that, so it degrades to a useful empirical
threshold curve, which is still better than a guessed one. This is what makes "90%"
**certifiable** rather than asserted.

**2. Citation-attribution evaluation (ALCE / AutoAIS / TRUE).** Your gate is binary and you
have never measured whether it is *correct*. ALCE (Gao et al., EMNLP 2023, arXiv:2305.14627,
`github.com/princeton-nlp/ALCE`) decomposes citation quality into **citation recall** (is
every claim cited?) and **citation precision** (does each citation support its claim?) —
exactly your failure's decomposition. AutoAIS is the NLI judge for the precision half; TRUE
(Long et al.) is the claim-level alternative. This is an **evaluation harness, not a model** —
a whole category the first survey did not touch. Cost: a labelling pass over ~50-100 existing
accepted answers.

**3. Semantic entropy / self-consistency — a different signal from logprobs.** Logprobs are
per-token; NLI needs a second model. Semantic entropy (Kuhn & Gal, Nature 2024) draws N
generations, clusters by meaning, and takes the entropy — a fabricated measurement is unstable
across samples where a copied one is not. Uses the 8B you already run, zero new parameters.
**Cost: N× generation.** At a 17.7-21.7 s median, N=5 is ~90 s — defensible only as a
background shadow pass (your Tier A path already runs `shadow_background`), not on the hot path.

**Ruled out on evidence:** SPLADE (`prithivida/Splade_PP_en_v1`, 507 MB ONNX, in fastembed) is
a learned term-match scorer and may make the echo *worse* — only after the index is rebuilt.
Hidden-state factuality probes (DoLa/INSIGHT) need hidden states Ollama does not expose.
`OpenAssistant/reward-model-deberta-v3-large-v2` is 3.7 years stale with no ONNX.

## The binding constraint

No verification model can be evaluated at n=29 — the ±15-point noise floor cannot tell a 69%
verifier from an 85% one. The best documented accuracy in the whole space is 0.854 in-domain /
0.690 OOD. **Before spending a day on any model, build the eval set with citation
precision/recall decomposed** — ~150 rows minimum to halve the interval. That is the
prerequisite that makes everything above falsifiable.

## Two known defects, found but deliberately not fixed

- **`"pan track 2"` produces a broken example.** The clarify question suggests `"pan Snare /
  Clap 2 left"` and the parser reads the `2` back as **2% left**. In the write path, so it was
  left alone under the pure-move rule rather than fixed on a refactor branch.
- **`set_tempo` is invisible to the order test.** `test_live_intent_rule_order.CHAIN_ACTIONS`
  omits it because `_tempo_request` writes into a dict bound to `fields` (`live_intent.py:2065`)
  and the AST scan at `:113-116` does not traverse it, so a dropped tempo rule changes nothing
  observable. Currently covered only by the corpus replay.

Verified dead code in `autonomous_agent.py`: **5 tool functions, 71 lines**, wired into neither
registry and uncallable — `tool_audit_live_session`, `tool_auto_remediate_session_issues`,
`tool_generate_neural_bassline`, `tool_formulate_surgical_remediation`, `tool_synthesize_pro_rack`.
10 more functions (91 lines) are wired but the planner cannot select them. Audit method is in
the refactor doc; registry keys are bare and sometimes diverge from function names
(`tool_orchestrate_subagent` is bound under key `"orchestrate"`), so resolve the function each
`KennTool` binds rather than matching names.

## Working agreements

Comments explain **why**, never what. No divider banners, no docstrings echoing a signature,
no filler words (robust, seamless, comprehensive, leverage, ensure, orchestrate). Tests read
as executable documentation — name them for the behaviour they protect, and mutation-check a
new regression test before merge. Match the surrounding file's style. Do not commit without
being asked.

Start by reading `REFACTOR_HANDOFF_2026-10-02.md` and `git log --oneline`, then tell me what
you would do first and why before writing code.