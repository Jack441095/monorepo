#!/usr/bin/env python3
"""Prepare or run a small KENN command-planning LoRA experiment.

The default action is a read-only dry run.  Pass ``--run`` explicitly to
load the cached base model and create adapter weights.  This script trains
only on the separate synthetic export; it never consumes the shadow holdout,
opens Ableton, or enables an LLM in the Live command gateway.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import random
import sys
import subprocess
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "backend" / "src"))
sys.path.insert(0, str(REPO_ROOT / "tooling" / "scripts"))

DEFAULT_DATA = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "training" / "ableton_command_training.jsonl"
DEFAULT_OUTPUT = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "artifacts" / "models" / "kenn-command-lora-pilot"
SCHEMA = "kenn.ableton_command_lora_experiment.v1"


def _load_rows(data_path: Path) -> list[dict[str, Any]]:
    from kenn.training.training_records import read_jsonl

    rows = read_jsonl(data_path, missing_ok=False)
    if not rows:
        raise ValueError("The command-training export is empty.")
    from build_kenn_command_training import assert_no_holdout_overlap, training_snapshot
    from build_kenn_command_corpus import scenario_snapshots
    from kenn.core.live_command import validate_llm_plan

    assert_no_holdout_overlap(rows)
    snapshots = scenario_snapshots()
    for row in rows:
        if row.get("schema") != "kenn.ableton_command_training.v1":
            raise ValueError(f"Unsupported training record schema: {row.get('schema')!r}")
        scenario = row.get("scenario")
        if scenario is None:
            snapshot = training_snapshot()
        else:
            if isinstance(scenario, bool) or not isinstance(scenario, int) or not 1 <= scenario <= len(snapshots):
                raise ValueError(f"{row.get('record_id')} has unsupported scenario {scenario!r}")
            snapshot = snapshots[scenario - 1]
        plan = row.get("label")
        checked = validate_llm_plan(plan, snapshot)
        if not checked.get("ok"):
            raise ValueError(f"Invalid label in {row.get('record_id')}: {checked.get('error')}")
        messages = row.get("messages")
        if not isinstance(messages, list) or len(messages) != 3 or messages[-1].get("role") != "assistant":
            raise ValueError(f"{row.get('record_id')} must contain system, user, and assistant messages.")
    return rows


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _provenance() -> dict[str, Any]:
    """Return reproducibility metadata without credentials or private data."""
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        revision = "unknown"
    provenance: dict[str, Any] = {
        "git_revision": revision,
        "python": platform.python_version(),
        "platform": platform.platform(),
    }
    try:
        import torch

        provenance["torch"] = str(torch.__version__)
        provenance["cuda_available"] = bool(torch.cuda.is_available())
        provenance["mps_available"] = bool(getattr(torch.backends, "mps", None) and torch.backends.mps.is_available())
    except Exception as exc:
        provenance["torch"] = f"unavailable: {type(exc).__name__}"
    return provenance


def _cached_base_available(base_model: str, *, allow_download: bool) -> tuple[bool, str]:
    try:
        from transformers import AutoConfig, AutoTokenizer
    except Exception as exc:
        return False, f"training_dependencies_unavailable: {type(exc).__name__}: {exc}"

    kwargs = {"local_files_only": not allow_download}
    try:
        AutoConfig.from_pretrained(base_model, **kwargs)
        AutoTokenizer.from_pretrained(base_model, **kwargs)
        return True, "config_and_tokenizer_available"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def dry_run(*, data_path: Path, base_model: str, output: Path, allow_download: bool, max_records: int = 0, device_name: str = "auto") -> dict[str, Any]:
    rows = _load_rows(data_path)
    if max_records < 0:
        raise ValueError("max_records must be zero or positive")
    selected_records = min(len(rows), max_records) if max_records else len(rows)
    base_available, base_status = _cached_base_available(base_model, allow_download=allow_download)
    try:
        import torch

        selected_device = str(_select_device(torch, device_name))
        device_status = "available"
    except Exception as exc:
        selected_device = None
        device_status = f"{type(exc).__name__}: {exc}"
    ready = base_available and selected_device is not None
    return {
        "schema": SCHEMA,
        "status": "ready" if ready else "blocked",
        "action": "dry_run",
        "training_run": False,
        "records": selected_records,
        "validated_records": len(rows),
        "max_records": max_records,
        "data": str(data_path),
        "data_sha256": _sha256(data_path),
        "base_model": base_model,
        "base_model_status": base_status,
        "device_request": device_name,
        "device": selected_device,
        "device_status": device_status,
        "provenance": _provenance(),
        "output": str(output),
        "holdout_protection": "passed",
        "next": "Pass --run only after reviewing the synthetic labels and accepting the pilot scope." if ready else "Resolve the unavailable base model or requested accelerator before training.",
    }


def _tokenize_rows(rows: list[dict[str, Any]], tokenizer: Any, max_length: int) -> list[dict[str, Any]]:
    encoded: list[dict[str, Any]] = []
    for row in rows:
        messages = row["messages"]
        prefix = tokenizer.apply_chat_template(messages[:-1], tokenize=False, add_generation_prompt=True)
        full = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
        item = tokenizer(full, truncation=True, max_length=max_length, add_special_tokens=False)
        prefix_ids = tokenizer(prefix, truncation=True, max_length=max_length, add_special_tokens=False)["input_ids"]
        labels = list(item["input_ids"])
        prefix_length = min(len(prefix_ids), len(labels))
        labels[:prefix_length] = [-100] * prefix_length
        if not any(label != -100 for label in labels):
            raise ValueError(f"The assistant target was truncated away in {row.get('record_id')}.")
        encoded.append({"input_ids": item["input_ids"], "attention_mask": item["attention_mask"], "labels": labels})
    return encoded


def _batch_tensors(encoded: list[dict[str, Any]], indices: list[int], *, pad_token_id: int, device: Any, torch: Any) -> dict[str, Any]:
    """Pad one small dynamic batch and move it to the selected accelerator."""
    from torch.nn.utils.rnn import pad_sequence

    items = [encoded[index] for index in indices]
    input_ids = pad_sequence(
        [torch.tensor(item["input_ids"], dtype=torch.long) for item in items],
        batch_first=True,
        padding_value=pad_token_id,
    )
    attention_mask = pad_sequence(
        [torch.tensor(item["attention_mask"], dtype=torch.long) for item in items],
        batch_first=True,
        padding_value=0,
    )
    labels = pad_sequence(
        [torch.tensor(item["labels"], dtype=torch.long) for item in items],
        batch_first=True,
        padding_value=-100,
    )
    return {
        "input_ids": input_ids.to(device),
        "attention_mask": attention_mask.to(device),
        "labels": labels.to(device),
    }


def _select_device(torch: Any, requested: str) -> Any:
    if requested == "auto":
        if torch.cuda.is_available():
            return torch.device("cuda")
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")
    if requested == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is not available on this host.")
    if requested == "mps" and not (getattr(torch.backends, "mps", None) and torch.backends.mps.is_available()):
        raise RuntimeError("MPS was requested but is not available on this host.")
    return torch.device(requested)


def _training_dtype(torch: Any, device: Any) -> Any:
    """Choose an accelerator-safe dtype for the selected training device."""
    device_type = str(getattr(device, "type", device))
    return torch.float16 if device_type in {"cuda", "mps"} else torch.float32


def train(*, data_path: Path, base_model: str, output: Path, epochs: int, max_length: int, learning_rate: float, allow_download: bool, seed: int, batch_size: int, max_records: int = 0, device_name: str = "auto") -> dict[str, Any]:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty adapter directory: {output}")
    if epochs < 1 or max_length < 1 or batch_size < 1 or max_records < 0:
        raise ValueError("epochs, max_length, and batch_size must be positive; max_records must be zero or positive")
    rows = _load_rows(data_path)
    validated_records = len(rows)
    if max_records:
        rows = rows[:max_records]
    if not rows:
        raise ValueError("max_records selected zero training records")

    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer

    random.seed(seed)
    torch.manual_seed(seed)
    device = _select_device(torch, device_name)
    dtype = _training_dtype(torch, device)
    print(f"Loading {base_model} on {device} ({len(rows)} records, batch size {batch_size})...", flush=True)
    kwargs = {"local_files_only": not allow_download, "torch_dtype": dtype}
    tokenizer = AutoTokenizer.from_pretrained(base_model, local_files_only=not allow_download)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    print("Tokenizing supervised records...", flush=True)
    encoded = _tokenize_rows(rows, tokenizer, max_length)
    model = AutoModelForCausalLM.from_pretrained(base_model, **kwargs)
    model.config.use_cache = False
    lora_config = LoraConfig(
        r=8,
        lora_alpha=16,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    )
    model = get_peft_model(model, lora_config).to(device)
    model.train()
    trainable = [parameter for parameter in model.parameters() if parameter.requires_grad]
    optimizer = torch.optim.AdamW(trainable, lr=learning_rate)
    losses: list[float] = []

    for epoch in range(epochs):
        order = list(range(len(encoded)))
        random.Random(seed + epoch).shuffle(order)
        epoch_losses: list[float] = []
        batches = [order[start:start + batch_size] for start in range(0, len(order), batch_size)]
        print(f"Training epoch {epoch + 1}/{epochs} ({len(batches)} batches)...", flush=True)
        for batch_number, batch_indices in enumerate(batches, start=1):
            tensors = _batch_tensors(
                encoded,
                batch_indices,
                pad_token_id=tokenizer.pad_token_id,
                device=device,
                torch=torch,
            )
            optimizer.zero_grad(set_to_none=True)
            result = model(**tensors)
            result.loss.backward()
            torch.nn.utils.clip_grad_norm_(trainable, 1.0)
            optimizer.step()
            loss = float(result.loss.detach().cpu())
            losses.append(loss)
            epoch_losses.append(loss)
            print(f"  batch {batch_number}/{len(batches)} loss={loss:.4f}", flush=True)
        print(f"Epoch {epoch + 1} mean loss={sum(epoch_losses) / len(epoch_losses):.4f}", flush=True)

    print(f"Saving adapter to {output}...", flush=True)
    output.mkdir(parents=True, exist_ok=False)
    model.save_pretrained(output)
    tokenizer.save_pretrained(output)
    manifest = {
        "schema": SCHEMA,
        "status": "trained_pilot",
        "base_model": base_model,
        "provenance": _provenance(),
        "data": str(data_path),
        "data_sha256": _sha256(data_path),
        "records": len(rows),
        "validated_records": validated_records,
        "max_records": max_records,
        "epochs": epochs,
        "batch_size": batch_size,
        "training_steps": len(losses),
        "max_length": max_length,
        "learning_rate": learning_rate,
        "device": str(device),
        "device_request": device_name,
        "mean_training_loss": sum(losses) / len(losses) if losses else None,
        "note": "Synthetic pilot only; not Live-qualified and not enabled by default.",
    }
    (output / "kenn_experiment_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--base-model", default="Qwen/Qwen2.5-1.5B-Instruct")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--max-length", type=int, default=2048)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--max-records", type=int, default=0, help="Optional bounded smoke-test limit; zero uses the full validated export")
    parser.add_argument("--device", choices=("auto", "cuda", "mps", "cpu"), default="auto", help="Training accelerator; auto prefers CUDA, then MPS, then CPU")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--allow-download", action="store_true", help="Allow Transformers to download the base model")
    parser.add_argument("--run", action="store_true", help="Actually train and write adapter weights")
    args = parser.parse_args()
    data_path = args.data.expanduser().resolve()
    output = args.output.expanduser().resolve()
    result = (
        train(data_path=data_path, base_model=args.base_model, output=output, epochs=args.epochs, max_length=args.max_length, learning_rate=args.learning_rate, allow_download=args.allow_download, seed=args.seed, batch_size=args.batch_size, max_records=args.max_records, device_name=args.device)
        if args.run
        else dry_run(data_path=data_path, base_model=args.base_model, output=output, allow_download=args.allow_download, max_records=args.max_records, device_name=args.device)
    )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result.get("status") in {"ready", "trained_pilot"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
