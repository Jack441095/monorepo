#!/usr/bin/env python3
"""Prepare or run a KENN command-planner LoRA with mlx-lm on Apple Silicon (C6).

The default action is a read-only dry run. Pass ``--run`` explicitly to
train. Records are validated and checked against the holdout exactly as in
``train_kenn_command_lora.py`` (the PyTorch pilot); this script only swaps
the trainer for mlx-lm, which can LoRA-train a 4-bit base (e.g.
``mlx-community/Qwen3.5-4B-4bit``) within 16 GB beside Ableton Live.

Loss is on the assistant turn only (``--mask-prompt``). Qwen3.5's chat
template renders each target with an empty think block, the same form KENN
serves with thinking off, so the adapter learns what it will be asked for.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "backend" / "src"))
sys.path.insert(0, str(REPO_ROOT / "tooling" / "scripts"))

from train_kenn_command_lora import DEFAULT_DATA, _load_rows, _provenance  # noqa: E402

DEFAULT_BASE = "mlx-community/Qwen3.5-4B-4bit"
DEFAULT_OUTPUT = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "artifacts" / "models" / "kenn-command-lora-mlx"
SCHEMA = "kenn.ableton_command_lora_mlx_run.v1"


def split_rows(rows: list[dict[str, Any]], *, valid_fraction: float, seed: int) -> tuple[list, list]:
    """Deterministic split; at least one validation row, at least one training row."""
    if len(rows) < 2:
        raise ValueError("Need at least two records to hold one out for validation.")
    order = list(range(len(rows)))
    random.Random(seed).shuffle(order)
    n_valid = min(len(rows) - 1, max(1, round(len(rows) * valid_fraction)))
    valid = sorted(order[:n_valid])
    train = sorted(order[n_valid:])
    return [rows[i] for i in train], [rows[i] for i in valid]


def write_mlx_data(rows: list[dict[str, Any]], data_dir: Path, *, valid_fraction: float, seed: int) -> dict[str, int]:
    train, valid = split_rows(rows, valid_fraction=valid_fraction, seed=seed)
    data_dir.mkdir(parents=True, exist_ok=True)
    for name, subset in (("train", train), ("valid", valid)):
        with (data_dir / f"{name}.jsonl").open("w", encoding="utf-8") as handle:
            for row in subset:
                handle.write(json.dumps({"messages": row["messages"]}, ensure_ascii=False) + "\n")
    return {"train": len(train), "valid": len(valid)}


def lora_command(args: argparse.Namespace, data_dir: Path) -> list[str]:
    return [
        sys.executable, "-m", "mlx_lm", "lora",
        "--model", args.base_model, "--train", "--data", str(data_dir),
        "--fine-tune-type", "lora", "--mask-prompt", "--grad-checkpoint",
        "--num-layers", str(args.num_layers), "--batch-size", str(args.batch_size),
        "--iters", str(args.iters), "--learning-rate", str(args.learning_rate),
        "--max-seq-length", str(args.max_seq_length), "--steps-per-report", "5",
        "--steps-per-eval", str(max(5, args.iters // 4)), "--val-batches", str(args.val_batches),
        "--save-every", str(max(1, args.iters // 4)),
        "--seed", str(args.seed), "--adapter-path", str(args.output / "adapter"),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--base-model", default=DEFAULT_BASE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--iters", type=int, default=200)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--num-layers", type=int, default=8, help="layers (from the top) that get LoRA adapters")
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--max-seq-length", type=int, default=4096)
    parser.add_argument("--valid-fraction", type=float, default=0.1)
    parser.add_argument("--val-batches", type=int, default=10)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--run", action="store_true", help="train (default is a dry run)")
    args = parser.parse_args()

    rows = _load_rows(args.data)
    args.output = args.output.expanduser().resolve()
    data_dir = args.output / "data"
    manifest: dict[str, Any] = {
        "schema": SCHEMA,
        "action": "train" if args.run else "dry_run",
        "records": len(rows),
        "data": str(args.data),
        "data_sha256": hashlib.sha256(args.data.read_bytes()).hexdigest(),
        "base_model": args.base_model,
        "hyperparameters": {k: getattr(args, k) for k in
                            ("iters", "batch_size", "num_layers", "learning_rate", "max_seq_length",
                             "valid_fraction", "val_batches", "seed")},
        "holdout_protection": "passed",
        "provenance": _provenance(),
    }
    try:
        import mlx_lm

        manifest["mlx_lm"] = mlx_lm.__version__
    except ImportError as exc:
        manifest.update(status="blocked", reason=f"mlx-lm unavailable: {exc}")
        print(json.dumps(manifest, indent=2))
        return 1
    manifest["split"] = write_mlx_data(rows, data_dir, valid_fraction=args.valid_fraction, seed=args.seed)
    command = lora_command(args, data_dir)
    manifest["command"] = command
    if not args.run:
        manifest.update(status="ready", next="Pass --run to train. Nothing was trained.")
        print(json.dumps(manifest, indent=2))
        return 0

    started = time.time()
    log_path = args.output / "train.log"
    with log_path.open("w", encoding="utf-8") as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, text=True)
    lines = log_path.read_text(encoding="utf-8").splitlines()
    manifest.update(
        status="trained" if result.returncode == 0 else "failed",
        returncode=result.returncode,
        seconds=round(time.time() - started, 1),
        train_log=str(log_path),
        loss_lines=[line for line in lines if "loss" in line.lower()][-6:],
        adapter=str(args.output / "adapter"),
    )
    (args.output / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in ("status", "seconds", "split", "loss_lines", "adapter")}, indent=2))
    return 0 if result.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
