#!/usr/bin/env python3
"""Merge a PEFT LoRA adapter into an original, complete safetensors checkpoint (C6).

Training loads Qwen3.5 text-only, so ``merge_and_unload`` saves a checkpoint
without the multi-token-prediction layer and vision tower, and llama.cpp then
fails to load it (``blk.32.attn_norm.weight`` not found). This writes a copy of
the original checkpoint with every tensor kept and each adapted weight
replaced by ``W + scale * (B @ A)``, computed in float32. Every adapter pair
must land on exactly one original tensor, or nothing is written.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path


def pair_keys(adapter_keys: list[str], prefix_from: str, prefix_to: str) -> dict[str, tuple[str, str]]:
    """Map each original weight name to its (lora_A, lora_B) adapter keys."""
    pairs: dict[str, tuple[str, str]] = {}
    for key in adapter_keys:
        if not key.endswith(".lora_A.weight"):
            continue
        module = key[: -len(".lora_A.weight")]
        if not module.startswith(prefix_from):
            raise ValueError(f"Adapter key {key!r} does not start with {prefix_from!r}")
        b_key = module + ".lora_B.weight"
        if b_key not in adapter_keys:
            raise ValueError(f"Missing lora_B for {module}")
        pairs[prefix_to + module[len(prefix_from):] + ".weight"] = (key, b_key)
    if len(pairs) * 2 != len(adapter_keys):
        raise ValueError("Adapter contains keys that are not lora_A/lora_B pairs.")
    return pairs


def lora_scale(config: dict) -> float:
    rank, alpha = int(config["r"]), float(config["lora_alpha"])
    return alpha / math.sqrt(rank) if config.get("use_rslora") else alpha / rank


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prefix-from", default="base_model.model.model.")
    parser.add_argument("--prefix-to", default="model.language_model.")
    args = parser.parse_args()

    import torch
    from safetensors import safe_open
    from safetensors.torch import load_file, save_file

    config = json.loads((args.adapter / "adapter_config.json").read_text())
    scale = lora_scale(config)
    with safe_open(str(args.adapter / "adapter_model.safetensors"), "pt") as handle:
        adapter = {key: handle.get_tensor(key) for key in handle.keys()}
    pairs = pair_keys(list(adapter), args.prefix_from, args.prefix_to)

    index = json.loads((args.base / "model.safetensors.index.json").read_text())
    missing = sorted(set(pairs) - set(index["weight_map"]))
    if missing:
        raise ValueError(f"{len(missing)} adapted weights are not in the base checkpoint, e.g. {missing[:3]}")

    args.output.mkdir(parents=True, exist_ok=False)
    applied = 0
    for shard in sorted(set(index["weight_map"].values())):
        tensors = load_file(str(args.base / shard))
        for name in [n for n in tensors if n in pairs]:
            a_key, b_key = pairs[name]
            weight = tensors[name]
            delta = adapter[b_key].float() @ adapter[a_key].float()
            if delta.shape != weight.shape:
                raise ValueError(f"{name}: delta {tuple(delta.shape)} vs weight {tuple(weight.shape)}")
            tensors[name] = (weight.float() + scale * delta).to(weight.dtype)
            applied += 1
        save_file(tensors, str(args.output / shard), metadata={"format": "pt"})
        print(f"{shard}: {len(tensors)} tensors", flush=True)
    if applied != len(pairs):
        raise ValueError(f"Applied {applied} of {len(pairs)} adapter pairs.")
    for item in args.base.iterdir():
        if item.is_file() and not item.name.endswith(".safetensors"):
            shutil.copy2(item, args.output / item.name)
    print(json.dumps({"applied": applied, "scale": scale, "output": str(args.output)}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
