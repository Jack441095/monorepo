"""One offline CUDA operation per process; adapters never touch a running provider."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from .records import Limits, read, write


def encode_targets(tokenizer, examples: list[list[dict]], max_length: int) -> list[dict]:
    """Mask complete assistant targets; reject template mismatches and truncation before GPU work."""
    rows = []
    for messages in examples:
        if not messages or messages[-1].get("role") != "assistant":
            raise ValueError("training requires an assistant target")
        prefix = tokenizer.apply_chat_template(messages[:-1], tokenize=False,
                        add_generation_prompt=True, enable_thinking=False)
        full = tokenizer.apply_chat_template(messages, tokenize=False, enable_thinking=False)
        ids = tokenizer(full, add_special_tokens=False)["input_ids"]
        prefix_ids = tokenizer(prefix, add_special_tokens=False)["input_ids"]
        if not full.startswith(prefix) or ids[:len(prefix_ids)] != prefix_ids:
            raise ValueError("chat template prefix mismatch would train on prompt tokens")
        if len(ids) > max_length or len(ids) <= len(prefix_ids):
            raise ValueError("training target is empty or exceeds the token ceiling; never truncate reviewed answers")
        rows.append({"input_ids": ids, "labels": [-100] * len(prefix_ids) + ids[len(prefix_ids):]})
    if not rows:
        raise ValueError("no reviewed training targets")
    return rows


def row_schedule(count: int, steps: int) -> list[int]:
    """Spread bounded steps across the corpus so later contexts are not silently ignored."""
    return [step * count // steps for step in range(steps)]


def generation_outcome(text: str, truncated: bool) -> dict:
    """Count KENN's existing abstention wording; direct offline calls have no fallback path."""
    from kenn.llm.llm_rewrite import is_abstain_reply
    return {"text": text, "truncated": truncated, "abstained": is_abstain_reply(text), "fallback": False}


def execute(request: dict) -> dict:
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "1":
        raise ValueError("only physical GPU 1 is authorized for this worker")
    import torch
    from peft import LoraConfig, PeftModel, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer, StoppingCriteria, StoppingCriteriaList

    limits = Limits(**request["limits"])
    limits.validate()
    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise ValueError("expected exactly one visible CUDA device: physical GPU 1")
    total_memory = torch.cuda.get_device_properties(0).total_memory
    torch.cuda.set_per_process_memory_fraction(min(1.0, limits.max_memory_gb * 1e9 / total_memory), 0)
    torch.manual_seed(request.get("seed", 0))
    started = time.monotonic()
    tokenizer = AutoTokenizer.from_pretrained(request["base_model"], local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(request["base_model"], local_files_only=True,
                                               torch_dtype=torch.bfloat16).to("cuda:0")
    if request["adapter"]:
        model = PeftModel.from_pretrained(model, request["adapter"],
                                          is_trainable=request["kind"] == "train", local_files_only=True)
    torch.cuda.synchronize()
    load_seconds = time.monotonic() - started
    if request["kind"] == "generate":
        model.eval()
        prompt = tokenizer.apply_chat_template(request["messages"], tokenize=False,
                        add_generation_prompt=True, enable_thinking=False)
        inputs = tokenizer(prompt, add_special_tokens=False, return_tensors="pt").to("cuda:0")
        prompt_tokens = inputs.input_ids.shape[1]
        if prompt_tokens + request["max_tokens"] > limits.max_length:
            raise ValueError("generation exceeds prompt/output token budget; shorten the reviewed context")
        phases = []

        class PhaseClock(StoppingCriteria):
            def __call__(self, input_ids, scores, **kwargs):
                # Synchronization makes these offline GPU phase timings useful, at some overhead.
                torch.cuda.synchronize()
                phases.append(time.monotonic())
                return False

        generation_start = time.monotonic()
        temperature = request["temperature"]
        options = {"do_sample": temperature > 0}
        if temperature > 0:
            options.update(temperature=temperature, top_p=1.0, top_k=0)
        with torch.no_grad():
            ids = model.generate(**inputs, **options, max_new_tokens=request["max_tokens"],
                stopping_criteria=StoppingCriteriaList([PhaseClock()]),
                pad_token_id=tokenizer.eos_token_id)
        torch.cuda.synchronize()
        ended = time.monotonic()
        tokens = ids[0, prompt_tokens:]
        text = tokenizer.decode(tokens, skip_special_tokens=True)
        eos = model.generation_config.eos_token_id
        eos = {eos} if isinstance(eos, int) else set(eos or [])
        truncated = len(tokens) == request["max_tokens"] and int(tokens[-1]) not in eos
        return {**generation_outcome(text, truncated),
                "prompt_tokens": prompt_tokens, "output_tokens": len(tokens), "provider_calls": 1,
                "first_visible_seconds": None,
                "first_token_seconds": phases[0] - started if phases else None,
                "complete_seconds": ended - started, "load_seconds": load_seconds,
                "prefill_seconds": phases[0] - generation_start if phases else None,
                "decode_seconds": ended - phases[0] if phases else None,
                "peak_memory_gb": torch.cuda.max_memory_allocated() / 1e9,
                "peak_reserved_memory_gb": torch.cuda.max_memory_reserved() / 1e9,
                "memory_pressure": None, "model_switches": 1,
                "condition": "cold_fresh_cuda_process", "cache_hit": False,
                "measurement_scope": "offline HF GPU; not M3 serving or visible-answer timing"}

    if request["kind"] != "train":
        raise ValueError("worker accepts only generate or train operations")
    # Reuse the planner trainer's batching and assistant loss, not its planner dataset
    # or epoch-based loop. This pilot uses exact step/token ceilings and never merges weights.
    from scripts.train_kenn_command_lora_cuda import batches, target_loss
    rows = encode_targets(tokenizer, request["messages"], limits.max_length)
    if not request["adapter"]:
        model = get_peft_model(model, LoraConfig(r=limits.rank, lora_alpha=2 * limits.rank,
            lora_dropout=0.05, bias="none", task_type="CAUSAL_LM", target_modules="all-linear"))
    model.config.use_cache = False
    model.gradient_checkpointing_enable()
    model.enable_input_require_grads()
    model.train()
    params = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(params, lr=limits.learning_rate, weight_decay=0.0)
    steps = limits.policy_steps if request["policy"] else limits.steps
    pad_id = tokenizer.pad_token_id if tokenizer.pad_token_id is not None else tokenizer.eos_token_id
    actual_tokens, target_tokens, losses = 0, 0, []
    train_start = time.monotonic()
    schedule = row_schedule(len(rows), steps)
    for index in schedule:
        # Batch size one avoids the existing trainer's eager list of every GPU batch.
        batch = next(batches(rows, 1, pad_id, torch, "cuda:0", [index]))
        loss = target_loss(model, batch, torch)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(params, 1.0)
        optimizer.step()
        optimizer.zero_grad(set_to_none=True)
        actual_tokens += len(rows[index]["input_ids"])
        target_tokens += sum(label != -100 for label in rows[index]["labels"])
        losses.append(float(loss.detach()))
        if torch.cuda.max_memory_reserved() / 1e9 > limits.max_memory_gb:
            raise MemoryError("GPU reserved memory exceeded pilot ceiling")
    torch.cuda.synchronize()
    train_seconds = time.monotonic() - train_start
    output = Path(request["output"])
    output.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(output / "adapter", safe_serialization=True)
    return {"steps": steps, "seconds": time.monotonic() - started,
            "gpu_seconds": train_seconds, "load_seconds": load_seconds,
            "peak_gpu_memory_gb": torch.cuda.max_memory_allocated() / 1e9,
            "peak_reserved_memory_gb": torch.cuda.max_memory_reserved() / 1e9,
            "training_tokens": actual_tokens, "target_tokens": target_tokens,
            "padded_token_budget": steps * limits.max_length,
            "example_count": len(rows), "used_example_indices": sorted(set(schedule)),
            "losses": losses, "synthetic": False,
            "quantization": "bf16 training; production Q4_K_M unchanged"}


def main() -> int:
    request = read(Path(sys.argv[1]))
    response = execute(request)
    write(Path(request["response_path"]), response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
