#!/usr/bin/env python3
"""Standalone CUDA LoRA trainer for the KENN command planner (C6, GPU box).

Self-contained on purpose: the GPU box receives only this script and the
already-validated, holdout-checked chat records (``train.jsonl`` and
``valid.jsonl`` from ``train_kenn_command_lora_mlx.py``'s split), never KENN's
source. Loss is on the assistant turn only; the prompt is rendered with
thinking off (Qwen3.5's empty think block), the form KENN serves.

Writes the LoRA adapter, a merged bf16 model (for ``ollama create``), and a
manifest with the losses.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import time
from pathlib import Path


def load_split(path: Path) -> list[list[dict]]:
    return [json.loads(line)["messages"] for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def encode(conversations: list[list[dict]], tokenizer, max_length: int) -> list[dict]:
    rows = []
    for messages in conversations:
        prefix = tokenizer.apply_chat_template(messages[:-1], tokenize=False, add_generation_prompt=True,
                                               enable_thinking=False)
        full = tokenizer.apply_chat_template(messages, tokenize=False)
        if not full.startswith(prefix):
            raise ValueError("Chat template prefix does not match the full rendering; masking would be wrong.")
        ids = tokenizer(full, add_special_tokens=False)["input_ids"][:max_length]
        n_prefix = len(tokenizer(prefix, add_special_tokens=False)["input_ids"])
        labels = [-100] * min(n_prefix, len(ids)) + ids[n_prefix:]
        if all(label == -100 for label in labels):
            raise ValueError("A target was truncated away; raise --max-length.")
        rows.append({"input_ids": ids, "labels": labels})
    return rows


def batches(rows: list[dict], size: int, pad_id: int, torch, device, order: list[int]):
    for start in range(0, len(order), size):
        items = [rows[i] for i in order[start:start + size]]
        width = max(len(item["input_ids"]) for item in items)
        ids = torch.full((len(items), width), pad_id, dtype=torch.long)
        labels = torch.full((len(items), width), -100, dtype=torch.long)
        mask = torch.zeros((len(items), width), dtype=torch.long)
        for row, item in enumerate(items):
            n = len(item["input_ids"])
            ids[row, :n] = torch.tensor(item["input_ids"])
            labels[row, :n] = torch.tensor(item["labels"])
            mask[row, :n] = 1
        yield {"input_ids": ids.to(device), "attention_mask": mask.to(device), "labels": labels.to(device)}


def target_loss(model, batch, torch):
    """Loss over the answer tokens only, computing logits just for them.

    With batch size 1 and no padding, everything after the prompt is the
    target, i.e. the last n tokens, so ``logits_to_keep=n+1`` avoids a
    (sequence x 248k-vocabulary) logits tensor for long evidence prompts.
    """
    labels = batch["labels"][0]
    n = int((labels != -100).sum())
    logits = model(input_ids=batch["input_ids"], attention_mask=batch["attention_mask"],
                   logits_to_keep=n + 1).logits[0, :-1].float()
    return torch.nn.functional.cross_entropy(logits, batch["input_ids"][0, -n:])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-model", required=True)
    parser.add_argument("--data", type=Path, required=True, help="directory with train.jsonl and valid.jsonl")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--epochs", type=float, default=1.0)
    parser.add_argument("--batch-size", type=int, default=2,
                        help="examples per forward pass (a 248k vocabulary makes logits the memory peak)")
    parser.add_argument("--grad-accum", type=int, default=4, help="forward passes per optimizer step")
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--rank", type=int, default=16)
    parser.add_argument("--max-length", type=int, default=1024)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--no-merge", action="store_true")
    parser.add_argument("--sparse-logits", action="store_true",
                        help="batch size 1: compute logits for the answer tokens only (long prompts)")
    args = parser.parse_args()
    if args.sparse_logits and args.batch_size != 1:
        parser.error("--sparse-logits needs --batch-size 1")

    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    device = torch.device("cuda")
    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    pad_id = tokenizer.pad_token_id if tokenizer.pad_token_id is not None else tokenizer.eos_token_id
    train_rows = encode(load_split(args.data / "train.jsonl"), tokenizer, args.max_length)
    valid_rows = encode(load_split(args.data / "valid.jsonl"), tokenizer, args.max_length)
    print(f"train {len(train_rows)} valid {len(valid_rows)}", flush=True)

    model = AutoModelForCausalLM.from_pretrained(args.base_model, dtype=torch.bfloat16).to(device)
    model.config.use_cache = False
    model.gradient_checkpointing_enable()
    model.enable_input_require_grads()
    lora = LoraConfig(r=args.rank, lora_alpha=2 * args.rank, lora_dropout=0.05, bias="none",
                      task_type="CAUSAL_LM", target_modules="all-linear")
    model = get_peft_model(model, lora)
    model.print_trainable_parameters()
    trainable = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(trainable, lr=args.learning_rate, weight_decay=0.0)
    steps_per_epoch = math.ceil(len(train_rows) / (args.batch_size * args.grad_accum))
    total = max(1, int(steps_per_epoch * args.epochs))
    warmup = max(1, total // 20)
    scheduler = torch.optim.lr_scheduler.LambdaLR(
        optimizer, lambda s: min(1.0, (s + 1) / warmup) * 0.5 * (1 + math.cos(math.pi * min(1.0, s / total))))

    def validate() -> float:
        model.eval()
        losses = []
        with torch.no_grad():
            for batch in batches(valid_rows, args.batch_size, pad_id, torch, device, list(range(len(valid_rows)))):
                losses.append(float(target_loss(model, batch, torch) if args.sparse_logits else model(**batch).loss))
        model.train()
        return sum(losses) / len(losses)

    history = {"val_loss_start": validate(), "train_loss": [], "val_loss": []}
    print(f"val loss at start {history['val_loss_start']:.4f}", flush=True)
    started, step, epoch = time.time(), 0, 0
    model.train()
    while step < total:
        order = list(range(len(train_rows)))
        random.Random(args.seed + epoch).shuffle(order)
        micro = list(batches(train_rows, args.batch_size, pad_id, torch, device, order))
        for start in range(0, len(micro), args.grad_accum):
            group = micro[start:start + args.grad_accum]
            loss_sum = 0.0
            for batch in group:
                loss = (target_loss(model, batch, torch) if args.sparse_logits else model(**batch).loss) / len(group)
                loss.backward()
                loss_sum += float(loss)
            loss = torch.tensor(loss_sum)
            torch.nn.utils.clip_grad_norm_(trainable, 1.0)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad(set_to_none=True)
            step += 1
            history["train_loss"].append(round(float(loss), 4))
            if step % 10 == 0 or step == total:
                print(f"step {step}/{total} loss {float(loss):.4f} lr {scheduler.get_last_lr()[0]:.2e} "
                      f"{time.time() - started:.0f}s mem {torch.cuda.max_memory_allocated() / 1e9:.1f}GB", flush=True)
            if step % max(1, total // 4) == 0 or step == total:
                history["val_loss"].append((step, round(validate(), 4)))
                print(f"step {step} val loss {history['val_loss'][-1][1]:.4f}", flush=True)
            if step >= total:
                break
        epoch += 1

    args.output.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(args.output / "adapter")
    manifest = {"schema": "kenn.ableton_command_lora_cuda_run.v1", "base_model": args.base_model,
                "hyperparameters": {k: getattr(args, k) for k in ("epochs", "batch_size", "grad_accum", "learning_rate", "rank", "sparse_logits",
                                                                  "max_length", "seed")},
                "train_records": len(train_rows), "valid_records": len(valid_rows), "steps": total,
                "seconds": round(time.time() - started, 1),
                "peak_gpu_memory_gb": round(torch.cuda.max_memory_allocated() / 1e9, 2), **history}
    if not args.no_merge:
        merged = model.merge_and_unload()
        merged.save_pretrained(args.output / "merged", safe_serialization=True)
        tokenizer.save_pretrained(args.output / "merged")
        manifest["merged"] = str(args.output / "merged")
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("DONE", json.dumps({k: manifest[k] for k in ("steps", "seconds", "peak_gpu_memory_gb", "val_loss_start",
                                                     "val_loss")}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
