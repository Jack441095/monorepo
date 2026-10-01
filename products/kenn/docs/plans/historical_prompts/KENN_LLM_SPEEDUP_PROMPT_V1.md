# KENN LLM SPEED-UP — AGENT PROMPT (V1)

> **What this file is:** a reusable, self-contained prompt that drives an AI coding agent (Cline / Claude Code / Codex / any repo-aware agent) to profile and make KENN's local LLM answer path measurably faster — without regressing answer quality or breaking the self-correction guarantee.
>
> **How to use it:** open the workspace root (`~/Nite-DSP`) and instruct the agent: *"Execute `KENN_LLM_SPEEDUP_PROMPT_V1.md` in full. Produce every deliverable in §7."* Run in Plan/read-only mode first; only implement after the owner approves the plan in §5.
>
> **Owner:** NITE DSP (Jack) · **Created:** 2026-09-18 · **Supersedes:** none

---

## 0. Role, mission and success criteria

You are a **principal performance engineer** specialising in on-device LLM inference (MLX / Apple Silicon, Python serving, prompt engineering, and caching). Your mission: **cut KENN's end-to-end answer latency by at least 40%** versus the current baseline, while keeping output quality within the tolerance defined in §3.4.

### Canonical paths (read these first)

- `Nite-DSP-Operations/monorepo/products/kenn/kenn/llm/kenn_lm.py` — local fine-tuned LoRA model wrapper (MLX preferred, HF/PEFT fallback, per-call subprocess fallback)
- `Nite-DSP-Operations/monorepo/products/kenn/kenn/llm/kenn_lm_server.py` — persistent MLX server (Unix socket, newline-delimited JSON, single-threaded)
- `Nite-DSP-Operations/monorepo/products/kenn/kenn/llm/llm_rewrite.py` — Ollama-backed answer/rewrite path (config, SQLite caching, streaming, Ollama keep-alive loop, synthesis)
- `Nite-DSP-Operations/monorepo/products/kenn/kenn/llm/paraphrase_engine.py`, `linter.py`
- Tests: `Nite-DSP-Operations/monorepo/Audio_Too/tests/kenn`, `tests/chat`, `tests/llm`
- Prior context: `docs/CAPABILITY_IMPROVEMENTS_2026-07-06.md` (in the kenn product repo); `SLO_CLASSIFICATION_OPTIMIZATION_PROMPT_V1.md` at workspace root (report-style precedent)

**Known baseline facts (verify, don't trust):** MLX ≈ 29 tok/s vs HF/MPS ≈ 6.5 tok/s; `self_correct=True` can cost up to 3 generation calls per turn (initial + 15-token critique + possible 400-token regen); model reload from disk on the subprocess fallback path; project venv is x86_64 (Rosetta) so MLX runs via native arm64 Python.

**Success criteria (all must hold before you stop):**
1. A reproducible benchmark script exists and reports baseline vs after, p50 + p95, for: cold-start first-answer latency, warm steady-state latency, tokens/sec, and streaming TTFB.
2. End-to-end answer latency improves ≥ 40% (or every applied optimization is documented with its measured effect and the remaining gap is explained).
3. All existing tests in `tests/kenn`, `tests/chat`, `tests/llm` pass unchanged.
4. Answer quality is spot-checked: ≥ 10 fixed evaluation prompts scored before/after; no regression on structure/format validity (`valid_response`, `valid_structure`).
5. Every claim in the final report cites file path + line, command + observed output, or a benchmark output file. No uncited assertion.

---

## 1. Ground rules (non-negotiable)

- **R1 — Evidence or it doesn't exist.** Verify each claimed bottleneck with a profile or benchmark before optimizing it. A doc comment saying "this is slow" is a lead, not a fact.
- **R2 — Measure before and after.** Build the benchmark harness (§2) *before* touching anything. No optimization lands without a paired before/after number.
- **R3 — One change at a time.** Each optimization is a separate, isolated change with its own measurement, so attribution is unambiguous. Revert anything that doesn't pay for itself.
- **R4 — Quality is a gate, not a nice-to-have.** Latency wins that degrade answer validity, structure, or the self-correction guarantee are rejected.
- **R5 — Destructive-command ban.** No `rm -rf` outside throwaway dirs, no force-push, no publishing, no paid-API calls at scale. Benchmark API/Ollama calls only within already-configured local or free endpoints.
- **R6 — Secret hygiene.** Reference key paths only; never echo values.
- **R7 — Respect the venv split.** Do not "simplify" the x86_64 venv / arm64 MLX split (`arch -arm64` + `/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13`) without proof a unified path is faster.
- **R8 — Keep the fallback ladder.** Server → MLX subprocess → HF/PEFT must remain functional. Optimizations may not remove fallbacks.

---

## 2. Phase 1 — Baseline and profiling (read-only + benchmark only)

1. Read all canonical paths end-to-end. Build a written inventory of every hop in the answer path: caller -> `KennLM` generation (or `llm_rewrite` path) -> socket ping -> server generation -> critique -> possible regen -> response. Note per-hop timeouts and any serial round-trips.
2. Write `benchmarks/kenn_llm_bench.py` (new file, allowed) that measures:
   - **Cold start:** server not running -> first answer (includes model load time).
   - **Warm steady state:** N=20 repeated single-turn generations (p50, p95).
   - **Self-correct turn:** `self_correct=True` vs `self_correct=False`.
   - **Streaming TTFB** (time-to-first-token) for the streaming path in `llm_rewrite.py`.
   - Optionally: answer-cache hit vs miss latency.
3. Run the benchmark; save raw output to `benchmarks/results_baseline.txt`. Record model load time, tok/s, per-phase timings.
4. Profile at least one warm generation with `py-spy` or `cProfile` on the client side and, separately, the server side. Look for: socket polling/backoff overhead, chat-template re-application cost, tokenizer overhead, JSON encode/decode of large payloads, retry/sleep loops, keep-alive ping cost.


---

## 3. Phase 2 — Optimization candidates (evaluate each; implement only what pays)

Ordered by expected ROI. Investigate each; implement in isolation per R3.

### 3.1 Generation-level (usually the biggest lever)
- **Speculative decoding:** `mlx_lm` supports draft-model speculative generation. Measure it if a small draft model is feasible; otherwise document why and skip.
- **Quantization check:** confirm `artifacts/models/kenn-mlx` is 4-bit; if fp16/bf16, a 4-bit quantized conversion typically gains 1.5-2x tok/s. Measure quality on the eval set.
- **`max_tokens` audit:** default 450 / regen 400. Measure the actual token-length distribution of real answers; if p95 answer length is ~200 tokens, cap the default at a data-backed number. Confirm the 15-token critique rarely truncates.
- **KV / prompt-prefix cache reuse:** `mlx_lm.generate` re-prefills the full prompt every call. Investigate `mlx_lm.models.cache` (prompt cache make/save/load) to keep the system-prompt prefix cached across turns in the persistent server — the server is long-lived, exactly where prefix caching pays.

### 3.2 Turn-structure level
- **Self-correct policy:** measure how often the 15-token critique actually triggers a regen. If the regen rate is low (< ~15%), make self-correct conditional (e.g., only high-stakes tasks) or fold the critique into the same generation pass (single-call self-check with a structured verdict field). Preserve the correctness guarantee; cite regen-rate data.

### 3.3 Serving level
- **Pre-warm the server at app launch** (start + one dummy generation) so the first real user turn is warm; verify the `_last_start_attempt_time` backoff doesn't cause repeated failed pings within a session.
- **Ollama path (`llm_rewrite.py`):** confirm the keep-alive ping loop actually prevents model unload and isn't itself adding serial latency per request; check whether `num_keep_alive` in the payload would make the ping loop unnecessary (delete the loop if so).
- **Cache:** confirm the SQLite answer-cache key covers real variability; measure hit rate in a realistic session. No key-semantics change without data.

### 3.4 Quality guardrail (applies to every landed change)
- Fixed eval set: >= 10 representative prompts (rewrite / note / answer mix). Score `valid_structure` / `valid_response` pass rate, plus a 1-5 human spot check on 5 of them, before and after. Any drop -> revert the change.

---

## 4. Phase 3 — Implementation order

1. Land cheapest-first, biggest-measured-impact: typically (a) prompt/KV prefix caching, (b) max_tokens cap, (c) self-correct policy, (d) quantization/speculative decoding, (e) pre-warm.
2. After each change: run the full bench + `python -m pytest tests/kenn tests/chat tests/llm -x --tb=short -q` + the §3.4 eval set.
3. Keep a change ledger: change -> bench delta -> tests -> keep/revert.

---

## 5. Plan gate

Before implementing anything, present: the ranked bottleneck table (§2 deliverable), the candidate list to implement with predicted gain each, total predicted end-to-end gain, and risks. **Wait for owner approval.** Read-only until then (the benchmark script and its results files are the only writes allowed pre-approval).

---

## 6. Report format

Use the estate convention: `OBSERVED:` (command + output, cited) -> `INFERRED:` (confidence HIGH/MEDIUM/LOW) -> `UNVERIFIED:` (and why). All numbers from the benchmark harness; no estimates dressed as measurements.

---

## 7. Deliverables checklist

- [ ] `benchmarks/kenn_llm_bench.py` + `benchmarks/results_baseline.txt` and `benchmarks/results_after.txt`
- [ ] Ranked bottleneck table with measured costs (§2)
- [ ] Change ledger: every attempted change with before/after numbers and keep/revert decision (§4)
- [ ] >= 40% end-to-end latency improvement, or documented explanation of the ceiling
- [ ] Test suites green (`tests/kenn`, `tests/chat`, `tests/llm`)
- [ ] Eval-set quality check passed (§3.4)
- [ ] Final report with OBSERVED/INFERRED/UNVERIFIED lanes and next-lever recommendations (e.g., model upgrade options)

**Deliverable:** a ranked bottleneck list (highest measured cost first), each with measured ms and evidence.
