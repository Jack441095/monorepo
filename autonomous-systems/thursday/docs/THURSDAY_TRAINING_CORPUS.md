# Thursday brain/routing fine-tuning: corpus + Monday plan (2026-09-05)

## Where this fits

Goal: fine-tune a small local model to be Thursday's brain/routing decision
maker, replacing (or narrowing the gap to) the current prompt-engineered
approach measured in `docs/THURSDAY_LLM_PROVIDER_ABSTRACTION.md`. This is
the data-preparation half of that work — no GPU/training has happened yet.
**Status update 2026-09-08: the GPU track is parked, not merely delayed.**
The candidate box (`ubuntu@www.haoee.com`, 8x RTX 4090 D) is a shared work
machine. Its GPUs were observed free and then reoccupied by another team's
vLLM job within minutes, and disk sat at ~3.5GB free against the ~20-50GB a
run needs. That is not something a training run can survive, so no training
is scheduled against it. This document, `thursday/evals/training_corpus.py`,
and `thursday/training_export.py` remain ready to pick up the moment
reliable hardware exists. Tracked as workstream W3 in
`docs/THURSDAY_LONG_TERM_PLAN.md`.

## What exists

**`thursday/evals/training_corpus.py`** — 804 synthetic (prompt, target-JSON)
supervised fine-tuning examples across 15 families, programmatically
generated (not model-sampled — see the module docstring for why). Every
target is a hand-authored, deterministically-correct `BrainDecision` JSON;
prompts are built with the real `thursday.brain.build_brain_prompt()`
against the same synthetic 15-service catalog `thursday/evals/
brain_benchmark.py` uses, so the input distribution matches production.

| family | count | what it teaches |
|---|---|---|
| general_knowledge | 120 | answer directly, don't deflect or invent a tool call |
| audio_engineering | 90 | direct knowledge vs. routing to audio_analysis |
| business_ops | 90 | route to business_status/client_info/finance_ops/research_lookup |
| ordinary_conversation | 72 | warm, brief chat replies |
| codebase_ops | 54 | route to codebase_search/edit/git |
| external_comms | 48 | route to admin_agent/notify_ops/marketing_ops/infra_ops |
| pronoun_reference | 48 | resolve "them"/"that client"/"that mix" from prior turns, confidence=medium |
| clarification_needed | 48 | abstain + a specific question_for_user when genuinely ambiguous |
| hallucination_avoidance | 42 | decline an impossible action rather than inventing a service |
| abstention | 36 | honest "I don't know" for data Thursday doesn't have |
| compound | 30 | multi-step plan/parallel_swarm for combined requests |
| kenn_routing | 30 | route production questions to KENN when acting, not just answering |
| prompt_injection | 24 | refuse an injected instruction, never echo the payload |
| specialist_routing | 48 | route a named-specialist ask to specialist_task, and *not* a plain factual lookup that happens to touch the same subject |
| support_and_tickets | 24 | route to support_ops |

Deterministic stratified train/val split (`train_val_split()`): 697 train /
107 val, every family represented in both. Verified disjoint from
`brain_benchmark.py`'s 56-case **evaluation** corpus (zero text overlap,
enforced by `tests/test_training_corpus.py::test_disjoint_from_eval_benchmark_corpus`)
— that benchmark stays the real, uncontaminated held-out check after any
fine-tune; the corpus's own val split is a much weaker in-family sanity
check, not a substitute for it.

Regenerate: `python3 -m thursday.evals.training_corpus --train-out train.jsonl --val-out val.jsonl`

**`thursday/training_export.py`** — reads real usage once the execution
feedback loop (`docs/` — see the brain.py/orchestrator.py commits from this
session) has accumulated real `plan_memory`/`feedback.jsonl` data, and
exports it in a compatible shape. No real usage data exists yet as of this
writing — the synthetic corpus above is what Monday's first run would train
on; real data folds in later as it accumulates.

## GPU box findings (read-only check performed 2026-09-05)

- `ssh -p 2022 ubuntu@www.haoee.com` — 8x NVIDIA RTX 4090 D, 24GB each, CUDA
  13.0 driver, 472GB RAM, 96 cores.
- **Shared, not dedicated**: 6 of 8 GPUs were busy with other workloads
  (VLLM inference, a `trellis2` project, a `SkinTokens` project) at check
  time. Only GPUs 6/7 had real VRAM headroom (~20GB/~19GB free).
- **Disk was the real constraint, not VRAM**: 98GB root volume, only 5.5GB
  free. User is clearing space; expected ready Monday.
- Did not install anything or download models during the check (read-only:
  `nvidia-smi`, `df -h`, `free -h`, `python3 --version`, `nvcc --version`).

## Monday checklist

1. **Confirm disk space** is actually free before touching anything (`df -h
   /` — want at least ~30-50GB free for base model weights + LoRA
   checkpoints + optimizer states, more if trying multiple base models).
2. **Confirm which GPUs are free** at that moment (`nvidia-smi`) — the other
   projects on this box may still be running; only use GPUs with real
   headroom, don't preempt anyone else's job.
3. **Pick a base model.** Candidates already benchmarked this session on
   this exact task (see `docs/THURSDAY_LLM_PROVIDER_ABSTRACTION.md` and
   `docs/benchmark_results/`): Qwen3.5-4B (86% pass, best result so far) and
   qwen2.5:7b-instruct (82%). A LoRA fine-tune of either is very feasible on
   a single 4090's 24GB. Re-benchmarking the fine-tuned result against the
   same `thursday/evals/brain_benchmark.py` 50-case suite is the real
   pass/fail signal — don't trust training loss alone.
4. **Pick a fine-tuning framework** — not decided yet. Options given this
   rig (CUDA, standard HF-compatible stack): `mlx_lm.lora` (if training
   Apple-side isn't required — this box is CUDA, so more likely
   `peft`+`transformers`+`bitsandbytes`, or `axolotl`/`unsloth` for a more
   turnkey LoRA config). Check what's already installed on the box before
   assuming.
5. **Convert the corpus** to whatever format the chosen framework expects
   (chat-template-formatted text, or a `messages`+`completion` JSONL like
   what's already produced — most SFT trainers accept the latter directly
   or with a thin adapter script).
6. **Train a LoRA**, start conservative (few epochs, small rank) given the
   corpus is only 804 examples — this is not enough data for a full
   fine-tune or a large-rank LoRA without overfitting risk.
7. **Evaluate**: run `thursday/evals/brain_benchmark.py` against the
   fine-tuned model (point `THURSDAY_LLM_PROVIDER=mlx_lm` or
   `openai_compat` at wherever it's served) and compare against the
   existing Qwen3.5-4B/qwen2.5:7b baseline numbers. Only adopt it as
   Thursday's default provider if it demonstrably improves pass rate /
   reduces hallucination without regressing safety (`safety_violation_count`
   must stay 0).
8. **Wire in via env vars, not code changes**: `THURSDAY_LLM_PROVIDER`,
   `THURSDAY_LLM_MODEL`, `THURSDAY_LLM_BASE_URL` already support pointing
   Thursday at any new model/server — no brain.py changes needed to try it.

## Unresolved / needs a decision before Monday

- Fine-tuning framework not chosen (needs checking what's actually
  installed on the box, or installing one — which needs the disk space
  question settled first).
- 804 examples is workable for a narrow LoRA but on the small side; whether
  to expand further before training or just run a first pass and iterate is
  an open call.
- No real usage data exists yet to blend in via `training_export.py` — the
  first fine-tune will be 100% synthetic-data-trained.
