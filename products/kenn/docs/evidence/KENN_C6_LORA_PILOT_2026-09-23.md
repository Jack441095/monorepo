# C6 LoRA pilot: qwen3.5:4b fine-tuned for the command planner (2026-09-23)

The owner chose `qwen3.5:4b` as the C6 base (see the C2 GPU evidence addendum). This is the first fine-tune: one
epoch on a synthetic, leak-guarded corpus, scored through KENN's production planner path on the same 124 cases as C2.

## Result

**The fine-tuned model with the compact prompt beats the stock model with the full prompt.**

- **It asks for clarification every time it should (30/30).** Only the deterministic parser did that before.
- **It accepts a third as many wrong plans (5 vs 15).**
- **The trade-off:** it now also asks about some clear commands, so run 2 should retune the corpus balance.

| Planner (all on GPU 0, bf16, thinking off, same 124 cases) | Correct | Accepted | Clarify (30) | Act (94) | Curated (24) | Wrong plans accepted | p50 |
|---|---|---|---|---|---|---|---|
| Stock Qwen3.5-4B + full prompt (today's candidate) | 65.3% | 87.1% | 19/30 | **62/94** | 13/24 | 15 | 1.12 s |
| Stock Qwen3.5-4B + compact prompt | 4.0% | 14.5% | 4/30 | 1/94 | 1/24 | 1 | 3.59 s |
| **Fine-tuned (run 1) + compact prompt** | **68.5%** | **91.1%** | **30/30** | 55/94 | **15/24** | **5** | **0.96 s** |

- **The stock model scores 4% with the compact prompt.** Without the long instructions it does not know the plan
  format. The compact prompt works only with a model that learned the format, which is what the fine-tune adds.
- **The import path is faithful.** The stock weights served through my import path scored 65.3%, against 66.1% for
  Ollama's library `qwen3.5:4b` (Q4_K_M) in C2.
- **Where run 1 fails:**
  - It asks instead of acting on clear commands: mute 5, device parameter 5, insert 4, rename 3, solo 2, focus-device 1.
  - Two-part requests collapse to one action: "recipe" became solo or mute in 4 cases.
  - 11 plans were rejected for missing exact fields (track index or name, device and parameter fields, return index).

## Corpus

`build_kenn_command_corpus.py --variants 8 --scenarios 4 --include-drafted --prompt compact` produced 2,208 records,
split 1,987 train and 221 valid.

- **Seeds:**
  - 48 reviewed seeds.
  - 21 drafted clarify seeds (`drafted_command_seeds.py`, owner review pending). They cover requests with no amount
    or no clear referent, written in different idioms and track names from the evaluation phrasings.
- **Variants:** 4 track-name scenarios × 8 natural variants, with no "(variant N)" filler.
- **48% of records are "clarify"** (25% before the drafted seeds).
- **Targets are compact:** no schema constant and no null fields, about 31 tokens.
- **Leak guard:** every query is checked, case- and punctuation-insensitively, against the shadow holdout and both
  natural holdouts. It caught one real overlap (my drafted candidate "create a return track"), which was reworded.
- **Compact prompt:** an ~80-token system prompt (`KENN_LLM_COMMAND_PROMPT=compact`) instead of 1,341 tokens.
  Median record length drops from 1,944 to 694 tokens.

## Training

| | |
|---|---|
| Base | `Qwen/Qwen3.5-4B` (Apache-2.0), fetched on the box via hf-mirror.com. Both shards' SHA-256 match Hugging Face's published LFS hashes. |
| Where | GPU box, GPU 0 only (RTX 4090 D), user-level venv under `/mnt/data/kenn-bakeoff/c6`, no system changes, no restarts. Only the trainer script and the validated text records were sent, never KENN source or audio. |
| Method | `train_kenn_command_lora_cuda.py`: LoRA r=16, α=32, all linear layers (248 modules, 0.77% of parameters), bf16, gradient checkpointing, loss on the assistant turn only, thinking-off template. |
| Schedule | 1 epoch, 249 optimizer steps (batch 2 × accumulation 4), lr 2e-4 cosine with warm-up. |
| Cost | 17 min, peak 13.7 GB. |
| Validation loss | 2.03 → 0.025 (step 62) → 0.001 (end). The validation split comes from the same synthetic distribution, so this shows the format was learned, not that it generalises. The 124-case evaluation measures that. |

The Mac could not train this model. mlx-lm on the M3 with 16 GB ran out of GPU memory with 4 or more adapted layers,
even at 700 tokens, and a single layer ran at about 14 s per step.

## Serving path (and a bug fixed on the way)

1. Training loads Qwen3.5 text-only, so PEFT's merged save dropped the multi-token-prediction layer.
   - llama.cpp then refused the GGUF: `blk.32.attn_norm.weight not found`.
   - `merge_lora_into_checkpoint.py` fixes this. It merges `W + (α/r)·B·A` into a copy of the original, complete
     checkpoint (all 738 tensors), and fails unless every adapter pair lands exactly once.
2. llama.cpp's converter makes a bf16 GGUF (441 tensors, same as stock).
3. `ollama create` uses the stock model's `RENDERER`/`PARSER`/`PARAMETER` lines, so the prompt format and sampling
   settings are identical.
   - Ollama 0.34.2 quantises only safetensors imports, and on Linux that needs its MLX runtime, which is not
     available. So `llama-quantize` (built on the box's CPU) makes the Mac's Q4_K_M copy.
   - Q4_K_M GGUF: 2.78 GB, SHA-256 `2abe9e03d66b19aa3aa2e8f8c9443f12828679cd24d802308a6dbe878647d874`.

## Caveats

- **Everything here is still owner-review pending.**
  - The drafted clarify seeds and 100 of the 124 evaluation phrasings are Claude-drafted, pending owner review.
  - The corpus is synthetic and narrow (validation loss 0.001).
- **One run, one seed.** A few points either way is within noise.
- **Not a promotion.** The fine-tune stays behind the shadow flag; C4 promotion is the owner's decision.
- **Serving detail.** The stock Modelfile ships `presence_penalty 1.5`, which KENN's planner calls do not override.
  Kept identical across all rows here. Whether turning it off helps JSON plans is untested.

## Next

1. **Run 2:** bring the clarify share down to ~35% and add explicit-command variety (mute/solo/rename/device/insert
   and two-part requests), then re-score.
2. **Mac latency** of the Q4_K_M fine-tune with the compact prompt (this document's addendum).
3. **Owner review** of the 21 drafted clarify seeds and the 100 drafted evaluation phrasings.
