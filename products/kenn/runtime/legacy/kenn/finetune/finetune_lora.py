#!/usr/bin/env python3
"""Fine-tune a small language model on KENN's template Q&A pairs using LoRA and PyTorch MPS/CUDA."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import torch
from torch.utils.data import Dataset, DataLoader
from torch.optim import AdamW

# Setup paths
KENN_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATA = KENN_DIR / "artifacts" / "training" / "kenn_session_training.jsonl"
DEFAULT_OUT = KENN_DIR / "artifacts" / "models" / "kenn-lora"


SYSTEM_PROMPT = "You are KENN, a senior audio engineer answering from provided sources."


class QADataset(Dataset):
    """Custom dataset to format (question, context, answer) triples for SFT."""
    def __init__(self, jsonl_path: Path, tokenizer: AutoTokenizer, max_length: int = 1024):
        self.examples = []
        if not jsonl_path.exists():
            raise FileNotFoundError(f"Dataset path not found: {jsonl_path}")

        print(f"Loading training data from {jsonl_path}...")
        with jsonl_path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                q = data.get("question", "")
                c = data.get("context", "")
                a = data.get("answer", "")

                if not q or not a:
                    continue

                answer_ids = tokenizer(a, add_special_tokens=False)["input_ids"]
                if tokenizer.eos_token_id is not None:
                    answer_ids = [*answer_ids, tokenizer.eos_token_id]

                # Preserve the supervised answer when long retrieved context
                # exceeds max_length.  Only assistant tokens contribute to loss.
                prompt_reserve = max(1, min(128, max_length // 4))
                answer_ids = answer_ids[: max(1, max_length - prompt_reserve)]
                prompt_budget = max(1, max_length - len(answer_ids))

                # Truncate the CONTEXT TEXT itself (keeping its head — each
                # note leads with its title/tags/short-answer, the most
                # identifying part) instead of right-truncating the fully
                # rendered prompt. Right-truncation kept only the tail of the
                # prompt string, which for any non-trivial context discarded
                # the "Context:" header and nearly the whole context block —
                # the model was effectively trained on question-only ->
                # answer pairs, teaching it to answer from memorized patterns
                # and ignore retrieved context at inference (see BACKLOG.md).
                empty_prompt = tokenizer.apply_chat_template(
                    [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": f"Context:\n\nQuestion:\n{q}"},
                    ],
                    tokenize=False, add_generation_prompt=True,
                )
                overhead_len = len(tokenizer(empty_prompt, add_special_tokens=False)["input_ids"])
                context_budget = max(0, prompt_budget - overhead_len)

                context_ids = tokenizer(c, add_special_tokens=False)["input_ids"][:context_budget]
                context_text = tokenizer.decode(context_ids) if context_ids else ""

                messages = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Context:\n{context_text}\n\nQuestion:\n{q}"},
                ]
                prompt = tokenizer.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=True
                )
                prompt_ids = tokenizer(prompt, add_special_tokens=False)["input_ids"]
                # Safety clamp for any decode/retokenize drift — a no-op in
                # the common case since context_ids was already budgeted.
                prompt_ids = prompt_ids[-prompt_budget:]

                input_ids = [*prompt_ids, *answer_ids]
                attention_mask = [1] * len(input_ids)

                self.examples.append({
                    "input_ids": input_ids,
                    "attention_mask": attention_mask,
                    "labels": [-100] * len(prompt_ids) + list(answer_ids)
                })
        print(f"Loaded {len(self.examples)} training examples.")

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, idx: int) -> dict[str, list[int]]:
        return self.examples[idx]


def collate_fn(batch: list[dict[str, list[int]]], pad_token_id: int) -> dict[str, torch.Tensor]:
    """Collate batch with dynamic padding."""
    input_ids = [torch.tensor(f["input_ids"], dtype=torch.long) for f in batch]
    attention_mask = [torch.tensor(f["attention_mask"], dtype=torch.long) for f in batch]
    labels = [torch.tensor(f["labels"], dtype=torch.long) for f in batch]

    max_len = max(len(x) for x in input_ids)

    padded_input_ids = []
    padded_attention_mask = []
    padded_labels = []

    for ids, mask, label in zip(input_ids, attention_mask, labels):
        pad_len = max_len - len(ids)
        # Pad right for autoregressive training
        padded_input_ids.append(torch.cat([ids, torch.tensor([pad_token_id] * pad_len, dtype=torch.long)]))
        padded_attention_mask.append(torch.cat([mask, torch.tensor([0] * pad_len, dtype=torch.long)]))
        # Mask out padding tokens from loss computation using -100
        padded_labels.append(torch.cat([label, torch.tensor([-100] * pad_len, dtype=torch.long)]))

    return {
        "input_ids": torch.stack(padded_input_ids),
        "attention_mask": torch.stack(padded_attention_mask),
        "labels": torch.stack(padded_labels)
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fine-tune a lightweight LLM using LoRA.")
    parser.add_argument("--base-model", default="Qwen/Qwen2.5-1.5B-Instruct", help="Hugging Face model ID or path.")
    parser.add_argument("--data-path", type=Path, default=DEFAULT_DATA, help="Path to training jsonl.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT, help="Where to save LoRA adapters.")
    parser.add_argument("--epochs", type=int, default=3, help="Number of training epochs.")
    parser.add_argument("--batch-size", type=int, default=1, help="Batch size per device.")
    parser.add_argument("--grad-accum", type=int, default=4, help="Gradient accumulation steps (effective batch = batch-size * grad-accum).")
    parser.add_argument("--lr", type=float, default=2e-4, help="Learning rate.")
    # Kept at 512, not bumped — FULL_APP_PLAN.md documents 1024 already
    # caused an MPS OOM on this hardware, which is why it was reduced to 512.
    # The actual grounding fix is the truncation *direction* fix above (keep
    # the context head, not the prompt tail) — that helps at any max_len.
    parser.add_argument("--max-len", type=int, default=512, help="Max sequence length.")
    args = parser.parse_args()

    # Determine device and dtype
    if torch.backends.mps.is_available():
        device = torch.device("mps")
        dtype = torch.float16
        print("Using Apple MPS (Metal Performance Shaders) for hardware acceleration.")
    elif torch.cuda.is_available():
        device = torch.device("cuda")
        dtype = torch.float16
        print("Using CUDA GPU for hardware acceleration.")
    else:
        device = torch.device("cpu")
        dtype = torch.float32
        print("Using CPU (Warning: training will be slow).")

    # Load tokenizer and model
    print(f"Loading tokenizer: {args.base_model}...")
    tokenizer = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id

    print(f"Loading base model: {args.base_model}...")
    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        torch_dtype=dtype,
        trust_remote_code=True
    )

    # Configure PEFT/LoRA
    print("Setting up PEFT/LoRA config...")
    peft_config = peft.LoraConfig(
        task_type=peft.TaskType.CAUSAL_LM,
        inference_mode=False,
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        target_modules=["q_proj", "v_proj", "k_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
    )
    model = peft.get_peft_model(model, peft_config)
    model.print_trainable_parameters()
    model.to(device)

    # Load dataset and dataloader
    try:
        dataset = QADataset(args.data_path, tokenizer, max_length=args.max_len)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1
    if not dataset:
        print("Error: no valid question/answer examples were found in the dataset.")
        return 1

    dataloader = DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=True,
        collate_fn=lambda b: collate_fn(b, tokenizer.pad_token_id)
    )

    # Optimizer
    optimizer = AdamW(model.parameters(), lr=args.lr)
    grad_accum = max(1, args.grad_accum)

    print(f"Starting training for {args.epochs} epochs (grad_accum={grad_accum}, effective batch={args.batch_size * grad_accum})...")
    model.train()
    for epoch in range(1, args.epochs + 1):
        total_loss = 0.0
        start_time = time.time()
        optimizer.zero_grad()
        for step, batch in enumerate(dataloader, 1):
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels = batch["labels"].to(device)

            outputs = model(input_ids=input_ids, attention_mask=attention_mask, labels=labels)
            loss = outputs.loss / grad_accum
            loss.backward()

            if step % grad_accum == 0 or step == len(dataloader):
                optimizer.step()
                optimizer.zero_grad()

            total_loss += loss.item() * grad_accum
            if step % 20 == 0 or step == len(dataloader):
                print(f"Epoch {epoch}/{args.epochs} | Step {step}/{len(dataloader)} | Loss: {(loss.item() * grad_accum):.4f}")

        avg_loss = total_loss / len(dataloader)
        epoch_time = time.time() - start_time
        print(f"Epoch {epoch} complete | Average Loss: {avg_loss:.4f} | Time: {epoch_time:.1f}s")

    print(f"Saving LoRA adapters to {args.output_dir}...")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(args.output_dir))
    tokenizer.save_pretrained(str(args.output_dir))
    print("Fine-tuning completed successfully!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
