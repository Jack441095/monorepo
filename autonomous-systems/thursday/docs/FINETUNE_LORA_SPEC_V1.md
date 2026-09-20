# Thursday LoRA Fine-Tune Spec V1

**STATUS: PROPOSED — DO NOT TRAIN. Founder approval required before any
training run. No training happens in CI. This document is the approval
artifact: training starts only after the founder signs the gate below.**

## Goal (narrow on purpose)

Teach a small local model Thursday's **routing, tone, and SOP-following**:
which service/evidence-gatherer a request needs, how to phrase grounded
summaries, when to abstain. **Facts (prices, names, versions, statuses)
are NEVER trained** -- they are retrieved live (finance_ops, truth
sheet, business_knowledge.json) on every call, before and after any
fine-tune. A fine-tuned model that quotes a memorized price is a failed
run, not a feature.

## Base model options (local-first)

1. **Qwen3 4B (MLX, Apple Silicon)** — preferred: matches the existing
   `mlx_lm` provider path, thinking-mode control already implemented
   (`enable_thinking=False` default for routing calls).
2. **Llama 3.1 8B (Ollama / CUDA box)** — fallback if MLX quality
   disappoints on structured JSON routing; served via `openai_compat`.

Both run fully local. Cloud APIs are for benchmarking only, never for
training data exfiltration (the corpus stays on disk here).

## Data (from `training_readiness`, never hand-built)

- Source: `training_export.export_training_records()` (plan_id-joined
  plan_memory + feedback), gated by `training_readiness.readiness_report()`:
  minimum 50 records, 0 surviving secret shapes (FAIL CLOSED otherwise).
- Mix: routing decisions (intent → service/gatherer) 50%, grounded-summary
  phrasing with corrections (correction_from/to pairs) 30%, abstain cases
  (security/data ABSTAINED + evidence-missing) 20%.
- Excluded by construction: anything with prices, client names, emails,
  tokens (redacted at save AND export AND gate-checked).
- SOP demonstrations: a small hand-written set (≤30) showing
  evidence-first answering over thursday-sops content. Reviewed by the
  founder line by line before inclusion.

## Method

- LoRA rank 8–16, adapters only; base weights frozen.
- 1–3 epochs, early stop on eval loss plateau; deterministic seed.
- Context: single-turn routing/phrasing pairs (same shape as
  brain.py prompts), max length 2048.

## Eval gates (ALL must pass vs the base model)

1. Routing accuracy UP on `thursday/evals/brain_benchmark.py` (or its
   current equivalent) -- service/gatherer selection.
2. Hallucination rate DOWN or flat -- grounded-summary eval: every number
   in output must appear in the provided evidence.
3. **Zero price/fact regressions**: the 30-question corpus eval
   (`tests/test_doc_search_corpus_eval.py`) + pricing tests
   (`test_thursday_finance_ops.py`) + support FAQ tests pass unchanged,
   with retrieval paths untouched (fine-tune must not bypass RAG).
4. Abstain rate sane: security/data specialists still ABSTAIN with zero
   LLM calls; evidence-missing paths still say so.
5. Latency: p95 single routing call within 2× base on the target machine.

## Hardware estimate

- MLX LoRA 4B on Apple Silicon (unified memory ≥32GB): hours, overnight run.
- CUDA alternative (24GB VRAM): LoRA 8B in a few hours.
- No new hardware to buy before the readiness gate reports READY.

## Approval gate

- [ ] Founder reviews this spec + a 10-record sample export (redacted).
- [ ] `readiness_report()` verdict READY on live stores.
- [ ] Founder writes approval (date + initial) below. Only then schedule PHASE 5 training.

Approved: Founder — chat approval 2026-09-18 (spec + routing/tone-only scope approved).
Date: 2026-09-18
Note: approval covers the SPEC. Training additionally requires the data
gate (readiness_report READY, 50+ clean records; live stores at 0 on
2026-09-18) + a 10-record sample review. No training run until both.
