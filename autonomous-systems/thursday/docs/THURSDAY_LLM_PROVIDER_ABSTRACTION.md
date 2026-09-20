# Thursday LLM provider abstraction (2026-09-04)

## Why

Audit finding: every production LLM call site (`brain.py`, `response_rewrite.py`,
`registry/handlers.py`, `specialists.py`) called `audio_too.model_runtime.DEFAULT_LLM`
directly. There was no swappable provider interface in production code — only a
throwaway one inside `thursday/evals/behavioural.py`, used for benchmarking and never
wired into `brain.py`'s `decide()`. That made it impossible to point Thursday's brain
at a local OpenAI-compatible server or MLX-LM, benchmark candidate models against the
real decision path, or add a hard "no LLM" rollback switch without editing code.

This was the smallest change that unblocks the rest of the improvement plan (local-model
benchmarking, model-failure handling, capability reporting) without touching the parts of
`brain.py`/`orchestrator.py` that already work: schema-enum service validation, the
post-parse membership re-check, `chat_only` mode, the confirmation/risk gate, and the
existing retry-then-abstain fallback chain are all unchanged.

## What changed

- **New**: `thursday/llm_provider.py` — a `Protocol`-shaped `LLMProvider` interface
  (`generate(messages, *, timeout, response_schema=None) -> GenerateResult`,
  `health_check()`, `capabilities()`) with four implementations:
  - `AudioTooProvider` (default) — wraps `audio_too.model_runtime.DEFAULT_LLM` unchanged.
  - `OpenAICompatProvider` — talks to any OpenAI-compatible `/chat/completions` endpoint
    (Ollama, LM Studio, vLLM, etc.) via stdlib `urllib` (no new dependency). Tries
    `response_format: json_schema` first; on failure, falls back once to a plain chat
    completion with the schema appended as a trailing **user** turn (not a system
    message — see compatibility notes below) and remembers the result so it stops
    retrying the unsupported mode on every subsequent call.
  - `MLXLMProvider` — in-process `mlx_lm.load`/`generate`, model cached per process.
    No native structured-output support (see notes), so JSON is prompt-instructed only.
    Timeout is enforced by running generation in a worker thread and abandoning
    (not killing) it on expiry — MLX has no generation-cancellation API.
  - `NullProvider` — always raises immediately. This is the rollback switch:
    `THURSDAY_LLM_PROVIDER=none` forces every brain LLM call to fail into `brain.py`'s
    existing deterministic-abstain path with zero network calls and zero model loads.
  - All four raise the single `LLMUnavailable` exception on failure, so callers never
    need to branch on which provider is active.
- **Changed**: `thursday/brain.py`'s `_default_llm()` now returns
  `thursday.llm_provider.get_llm_provider()` instead of importing
  `audio_too.model_runtime.DEFAULT_LLM` directly. `ModelRuntimeUnavailable` is kept as a
  backward-compatible alias for `LLMUnavailable`. The `.generate()` call signature and
  return shape (`.content`) are unchanged, so nothing else in `decide()` needed to move.
  **Default behavior is byte-for-byte identical** — `THURSDAY_LLM_PROVIDER` is unset in
  production, so `get_llm_provider()` returns `AudioTooProvider`, same as before.
- **Not changed** (deliberately, to keep this the smallest high-impact change):
  `response_rewrite.py`, `specialists.py`, `registry/handlers.py`, `ops/finance_ops.py`
  still import `audio_too.model_runtime.DEFAULT_LLM` directly. They're candidates for
  the same swap later (see Unresolved risks).

## Environment variables

| Variable | Default | Effect |
|---|---|---|
| `THURSDAY_LLM_PROVIDER` | `audio_too` | `audio_too` \| `openai_compat` \| `mlx_lm` \| `none` |
| `THURSDAY_LLM_MODEL` | unset | model name (openai_compat) or HF repo id (mlx_lm) |
| `THURSDAY_LLM_BASE_URL` | `http://127.0.0.1:11434/v1` | openai_compat server URL (matches `server.py`'s existing default) |
| `THURSDAY_LLM_TIMEOUT` | `10` (falls back to `AUDIO_TOO_LLM_TIMEOUT` if set) | per-call timeout, seconds |
| `THURSDAY_LLM_FALLBACK_MODEL` | unset | retried once, same provider/server, if the primary model errors |

## Model compatibility notes (real findings, not assumptions)

Tested against the actual local backends present on this machine — Ollama running
`qwen2.5:7b-instruct`, and a freshly downloaded `mlx-community/Qwen3.5-4B-MLX-4bit` —
using `brain.py`'s real `BrainDecision` JSON schema shape.

1. **Ollama / qwen2.5:7b-instruct via OpenAI-compat `/chat/completions`**: accepted
   `response_format: json_schema` and returned valid, schema-conformant JSON on the
   first try (~30s cold latency for a 7B model on this machine). `supports_json_schema`
   capability reports `True` after a successful call.

2. **MLX / Qwen3.5-4B-MLX-4bit — chat template rejects a trailing system message.**
   The first implementation appended the "respond with JSON matching this schema"
   instruction as an extra `system` message at the end of the conversation (mirroring
   the OpenAI-compat fallback). Qwen3.5's MLX chat template raised
   `"System message must be at the beginning"` on every call — a real, not
   hypothetical, structured-output failure of exactly the kind this task warned against
   assuming away. **Fix**: append the schema instruction as a trailing **user** turn
   instead, for both `MLXLMProvider` and `OpenAICompatProvider`'s fallback path. Works
   with every chat template exercised so far.

3. **MLX / Qwen3.5-4B-MLX-4bit is a thinking/reasoning model by default.** With
   `enable_thinking` left at the tokenizer's default (`True` for this model), it spent
   its entire `max_tokens` budget on chain-of-thought prose and never reached the JSON
   payload — 400 tokens produced zero valid JSON. `tok.apply_chat_template` accepts an
   `enable_thinking` kwarg (confirmed by reading the tokenizer's actual template code,
   not the model card). `MLXLMProvider` now defaults `enable_thinking=False`; with it
   off, 3/3 real routing-style prompts ("how's business doing", "look up a client",
   "what's 17×23") returned valid JSON, 14–48s latency on this M3 Air/16GB machine
   (first call slower — cold model load/compile).

4. **Neither local backend was ever asked to make a native tool call** — `brain.py`'s
   `decide()` doesn't use OpenAI tool-calling, it uses JSON-schema-shaped chat
   responses, so `supports_tool_calls` is reported as `False`/not implemented on every
   provider here. If a future change wants real tool-calling, that needs its own
   compatibility pass — do not assume it works because a model card claims support.

5. **A schema-conformant `service_id`/`agent` field is not the same as a
   schema-conformant *step*.** In one MLX test run, the model emitted
   `{"kind": "subagent", "service_id": "business_status"}` — valid against my simplified
   test schema (which didn't constrain per-`kind` required fields), but against
   `brain.py`'s real schema this step has `agent` unset, so `decide()`'s existing
   post-parse validation (`brain.py` step-validation loop) would silently drop it,
   correctly falling through rather than executing garbage. Not a bug — a demonstration
   that the existing double-validation (schema enum + post-parse membership check) is
   doing real, necessary work even against a "successful" structured-output call.

## Benchmark harness (priority 4) and results actually run

`thursday/evals/brain_benchmark.py` is a 50-case harness that calls `thursday.brain.decide()`
directly (the real production decision function, not a prompt-completion proxy) against a
synthetic-but-realistic 14-service catalog, and scores the returned `BrainDecision`
deterministically — no LLM judge. It covers all twelve categories the task specified
(ordinary conversation, general knowledge, codebase questions, audio-engineering, business
operations, compound requests, ambiguous pronouns, prompt injection, unavailable services,
confirmation-requiring requests, correct-abstention cases, and tool-call-hallucination
traps) and reports: pass rate overall and per-category, a hard safety-violation count
(P0 — a forbidden/excluded service ever appearing in validated steps), invalid-JSON rate,
a `likely_hallucinated_step` rate (steps proposed but entirely dropped by validation — the
observable proxy for "the model tried to call something that doesn't exist"), fallback
frequency (both retries inside `decide()` failed), a `chat_type_shape_ok` check (a real gap
this run surfaced — see below), abstention quality, clarification quality, and median
latency. Memory/plan-memory storage is redirected to a fresh temp dir per run
(`THURSDAY_STATE_DIR`) so results never read from or pollute a real installation.
`tests/test_brain_benchmark.py` covers the corpus structure and scoring logic itself
(17 tests, no LLM calls).

Full runs, no static inspection, against the real production `decide()` path:

| Provider / model | Pass rate | Safety violations | Invalid JSON | Hallucinated-step rate | Fallback freq. | Chat-shape violations | Abstention quality | Clarification quality | Median latency |
|---|---|---|---|---|---|---|---|---|---|
| `none` (deterministic baseline) | 38% | 0 | 0% | 0% | 100% | 0% | 100% | 0% | 0.02s |
| Ollama `qwen2.5:7b-instruct` | 82% | 0 | 0% | 0% | 20%\* | 18% | 56% | 0% | 23.8s |
| MLX `mlx-community/Qwen3.5-4B-MLX-4bit` | 86% | 0 | 0% | 2% (1/50) | 0% | 6% | 78% | 100% | 17.2s |

\* Fallback frequency for Ollama varied run to run (0%, 20%, 88% were all observed across
runs — see findings below); the 20% figure is from the final run reported here.

Findings from actually running this, not from reading the code:

1. **A real bug was caught and fixed by running the harness**: `brain.py`'s `decide()` was
   still reading the legacy `AUDIO_TOO_LLM_TIMEOUT` env var directly (`os.environ.get(...)`)
   instead of `thursday.llm_provider.default_timeout()`, which is the one that understands
   `THURSDAY_LLM_TIMEOUT`. Setting `THURSDAY_LLM_TIMEOUT=90` had **no effect** — every call
   silently used the old 10s default, causing both the primary call and the halved-timeout
   retry to fail against the full ~14-service prompt+schema, driving an 88% fallback-to-abstain
   rate in the first full run. Fixed by routing `decide()`'s timeout lookup through
   `default_timeout()` (one-line change, `brain.py`). After the fix, fallback frequency on
   the same model/hardware dropped to 0% in one run and 20% in another (see below) —
   i.e. it is *also* somewhat load/timing-sensitive, not perfectly reliable even with a
   correct 60s budget. This is exactly the class of thing "do not claim success from static
   inspection alone" warns about — reading `decide()`'s code would never have surfaced this.
2. **Qwen3.5-4B-MLX-4bit outperformed qwen2.5:7b-instruct on this harness** on every metric
   measured except a slightly worse `hallucination_trap` category score (2/3 vs 3/3) — it
   was faster (median 17.2s vs 23.8s on this M3 Air/16GB), asked clarifying questions when
   genuinely ambiguous input called for one (100% vs 0%), and produced fewer schema-shape
   inconsistencies. Neither model produced a single safety violation across 50 cases each.
3. **Both models are non-deterministic despite `temperature: 0`** in the request. The same
   case (`inj-1`) produced `type: "plan"` routing to `finance_ops` in one run and
   `type: "abstain"` in another, for byte-identical input. Ollama's fallback frequency also
   varied run to run under otherwise-identical settings. Benchmarking a local model once and
   trusting the number is not safe; this harness should be run multiple times before drawing
   conclusions, which it currently is not set up to do automatically (see Unresolved risks).
4. **A real schema-shape gap, not a safety issue**: `build_decision_json_schema()` has no
   cross-field rule tying `type` to `message`/`steps`, so a model can emit a schema-valid but
   self-inconsistent decision — `type: "chat"` with `message: null` (violates the prompt's
   own "message is REQUIRED for chat" instruction) or `type: "chat"` with a service step
   attached. Observed on Ollama at an 18% rate, MLX at 6%. Not caught as a safety failure
   (orchestrator.py never executes steps for a `chat`-typed decision), but it likely produces
   a blank or awkward user-facing reply in production. Tracked as `chat_type_shape_ok` in the
   harness; not fixed in this pass — see Unresolved risks.
5. **The harness's excluded-service check worked as intended**: case `unavail-4` (codebase
   search asked for with `codebase_search` excluded from the catalog) was the one case that
   tripped `likely_hallucinated_step` for MLX — `raw_step_count > 0` but zero validated
   steps, meaning the model proposed calling the excluded service and validation correctly
   dropped it. This is the double-validation (schema enum + post-parse membership check)
   documented in the audit doing exactly its job against a real hallucination attempt.
6. Qwen3.5-9B-MLX-4bit was **not** benchmarked (see Unresolved risks — scoping decision this
   session, not a technical blocker).

Raw per-case results (all 50 records, not just the summary) for each run are saved under
`docs/benchmark_results/`: `brain_benchmark_none.json`, `brain_benchmark_ollama_qwen2.5-7b-instruct.json`,
`brain_benchmark_mlx_qwen3.5-4b.json`.

## Exact commands used for verification

```bash
# Full existing suite (regression check — must stay green)
cd /Volumes/Jack_Gandy_1TB_SSD/NITE_DSP/autonomous-systems/thursday
python3 -m pytest tests -q

# New provider unit tests only
python3 -m pytest tests/test_llm_provider.py -q

# Brain benchmark harness's own scoring/corpus tests (no LLM calls)
python3 -m pytest tests/test_brain_benchmark.py -q

# Run the 50-case brain benchmark against the deterministic no-LLM baseline
THURSDAY_LLM_PROVIDER=none python3 -m thursday.evals.brain_benchmark

# Run it against Ollama (requires `ollama serve` running, qwen2.5:7b-instruct pulled)
THURSDAY_LLM_PROVIDER=openai_compat THURSDAY_LLM_MODEL=qwen2.5:7b-instruct \
  THURSDAY_LLM_BASE_URL=http://127.0.0.1:11434/v1 THURSDAY_LLM_TIMEOUT=60 \
  python3 -m thursday.evals.brain_benchmark --json /tmp/bb_ollama.json

# Run it against MLX (downloads ~2GB on first run if not cached)
THURSDAY_LLM_PROVIDER=mlx_lm THURSDAY_LLM_MODEL="mlx-community/Qwen3.5-4B-MLX-4bit" \
  THURSDAY_LLM_TIMEOUT=60 python3 -m thursday.evals.brain_benchmark --json /tmp/bb_mlx.json

# Live compatibility probe against Ollama (requires `ollama serve` running,
# qwen2.5:7b-instruct pulled)
python3 -c "
from thursday.llm_provider import OpenAICompatProvider
p = OpenAICompatProvider(model='qwen2.5:7b-instruct', base_url='http://127.0.0.1:11434/v1')
print(p.generate([{'role':'user','content':'reply OK'}], timeout=30).content)
"

# Live compatibility probe against MLX (downloads ~2GB on first run if not cached)
python3 -c "
from thursday.llm_provider import MLXLMProvider
p = MLXLMProvider(model='mlx-community/Qwen3.5-4B-MLX-4bit', enable_thinking=False)
print(p.generate([{'role':'user','content':'reply OK'}], timeout=60).content)
"

# Capability report for whatever THURSDAY_LLM_PROVIDER is currently set to
python3 -c "from thursday.llm_provider import capability_report; print(capability_report(probe=True))"
```

## Unresolved risks

- **Only `brain.py` was rewired.** `response_rewrite.py`, `specialists.py`,
  `registry/handlers.py`, `ops/finance_ops.py` still call
  `audio_too.model_runtime.DEFAULT_LLM` directly. They weren't touched here to keep this
  change small and reversible; each is a candidate for the same swap, but each has its
  own call-signature quirks (e.g. `response_rewrite.py` passes `json_mode=False`, not
  `response_schema`) that need their own compatibility check before wiring in.
- **Qwen3.5-9B-MLX-4bit was not downloaded or tested** in this pass (only the 4B variant,
  per explicit scoping decision this session) — its latency/quality/RAM-pressure profile
  on this 16GB machine is unknown and should be checked before treating it as the primary
  candidate.
- **MLX generation timeout is soft.** `MLXLMProvider` abandons a timed-out generation
  thread rather than killing it — the underlying MLX compute keeps running in the
  background, competing for CPU/GPU with whatever comes next, until it finishes on its
  own. On a 16GB machine under memory/thermal pressure this could compound if brain calls
  time out repeatedly. A hard-kill would need a subprocess-based provider instead of
  in-process `mlx_lm`, a larger change not attempted here.
- **`response_format: json_schema` support for `OpenAICompatProvider` is optimistic on
  first call and only "learned" (cached as unsupported) after one failure per process
  lifetime** — a server that flakes on schema support only some of the time will alternate
  between the two request shapes rather than settling, which could look like extra
  latency/log noise. Not observed in testing here, but not ruled out either.
- **Both local models are non-deterministic across runs at `temperature: 0`** (see finding 3
  above), and the harness runs each case exactly once. A single 50-case run is directional
  evidence, not a stable score — before treating either model's pass rate as a real gate,
  the harness should be extended to run each case N times and report variance, which it does
  not do today.
- **`chat_type_shape_ok` is observed, not enforced.** Both models produced `type: "chat"`
  decisions with `message: null` or with an attached (unexecuted) service step at a
  meaningful rate (18% Ollama, 6% MLX). `build_decision_json_schema()` has no JSON-Schema
  `if/then` rule to make this structurally impossible the way service-id validity already
  is, and `decide()` doesn't post-process it either. Worth fixing (a schema `allOf`/`if-then`
  clause, or a small post-parse normalization in `decide()` — e.g. treat `message: null` on
  `type: "chat"` as a soft-abstain) but not done in this pass to keep the change scoped to
  the benchmark harness itself.
- **Qwen3.5-9B-MLX-4bit was not downloaded or benchmarked** in this pass (only the 4B
  variant, per explicit scoping decision this session) — given the 4B variant already beat
  the 7B Ollama baseline here, whether the extra weight/latency of the 9B buys anything on
  this 16GB machine is untested and should be checked before treating 4B as final.
- **Only `brain.py` was rewired to the new provider abstraction.** `response_rewrite.py`,
  `specialists.py`, `registry/handlers.py`, `ops/finance_ops.py` still call
  `audio_too.model_runtime.DEFAULT_LLM` directly. They weren't touched here to keep this
  change small and reversible; each is a candidate for the same swap, but each has its own
  call-signature quirks (e.g. `response_rewrite.py` passes `json_mode=False`, not
  `response_schema`) that need their own compatibility check before wiring in.
- **MLX generation timeout is soft.** `MLXLMProvider` abandons a timed-out generation
  thread rather than killing it — the underlying MLX compute keeps running in the
  background, competing for CPU/GPU with whatever comes next, until it finishes on its
  own. On a 16GB machine under memory/thermal pressure this could compound if brain calls
  time out repeatedly. A hard-kill would need a subprocess-based provider instead of
  in-process `mlx_lm`, a larger change not attempted here.
- **`response_format: json_schema` support for `OpenAICompatProvider` is optimistic on
  first call and only "learned" (cached as unsupported) after one failure per process
  lifetime** — a server that flakes on schema support only some of the time will alternate
  between the two request shapes rather than settling, which could look like extra
  latency/log noise. Not observed in testing here, but not ruled out either.
- **No feedback-loop wiring (task priority 5)** — `GenerateResult` now carries
  `latency_s`/`provider`/`model`, and `BrainDecision` now carries `raw_step_count`, which is
  exactly what a future feedback-loop recorder needs, but nothing currently persists it
  anywhere (plan_memory, receipts, etc.).
- **The harness's "unavailable services" and "hallucination trap" categories rely on
  `raw_step_count > 0 and steps == []` as a proxy for "the model tried to call something
  invalid."** It's a real signal (confirmed working against case `unavail-4`, see finding 5
  above) but an imprecise one — it can't distinguish "hallucinated a nonexistent service"
  from "proposed a real-but-wrong service that also happened to get excluded" from "the
  model second-guessed itself and emitted an empty steps array on purpose." A more precise
  measurement would need `decide()` to expose the raw pre-validation step list, which was
  judged too invasive for this pass (see `BrainDecision.raw_step_count`'s docstring).
