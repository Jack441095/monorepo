#!/usr/bin/env python3
"""Extract a model-identified CLAP embedding index without semantic labels."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np
import torch


VERSION = "extract_label_free_clap_index_v1"


def _runner():
    path = Path(__file__).with_name("label_free_zero_shot.py")
    spec = importlib.util.spec_from_file_location("label_free_zero_shot", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load label-free runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(root: Path, model_dir: Path, out: Path, device: str = "cpu",
        batch_size: int = 32, limit: int | None = None) -> dict[str, object]:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    runner = _runner()
    paths = runner.discover_audio(root)
    if limit is not None:
        paths = paths[:max(0, limit)]
    processor, model = runner._load_model(model_dir, device)
    vectors: list[np.ndarray] = []
    valid_paths: list[str] = []
    errors: list[dict[str, str]] = []
    for start in range(0, len(paths), batch_size):
        chunk = paths[start:start + batch_size]
        audio: list[np.ndarray] = []
        batch_paths: list[Path] = []
        for path in chunk:
            try:
                audio.append(runner.load_audio(path))
                batch_paths.append(path)
            except Exception as exc:
                errors.append({"path": str(path), "error": str(exc)})
        if not audio:
            continue
        with torch.no_grad():
            inputs = processor(audio=audio, sampling_rate=runner.SAMPLE_RATE,
                               return_tensors="pt", padding=True)
            inputs = {key: value.to(device) for key, value in inputs.items()}
            features = runner._embedding_tensor(model.get_audio_features(**inputs))
            features = torch.nn.functional.normalize(features, dim=-1).cpu().numpy()
        vectors.append(np.asarray(features, dtype=np.float32))
        valid_paths.extend(str(path) for path in batch_paths)
        if (start + len(chunk)) % (batch_size * 16) == 0:
            print(json.dumps({"processed": start + len(chunk), "total": len(paths)},
                             sort_keys=True), flush=True)
    embeddings = np.concatenate(vectors, axis=0) if vectors else np.empty((0, 0), dtype=np.float32)
    payload = {
        "record_type": "slo_label_free_audio_embedding_index",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "model": str(model_dir.resolve()),
        "n_files": len(valid_paths),
        "n_errors": len(errors),
        "errors": errors,
        "safety": {
            "read_only": True,
            "ground_truth_read": False,
            "semantic_labels_created": False,
            "training_data_created": False,
            "rename_actions": False,
            "source_audio_modified": False,
            "human_approval_required": True,
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, **{
        "record_type": np.asarray(payload["record_type"]),
        "schema_version": np.asarray(payload["schema_version"]),
        "method_version": np.asarray(payload["method_version"]),
        "model": np.asarray(payload["model"]),
        "paths": np.asarray(valid_paths),
        "embeddings": embeddings,
        "errors": np.asarray(errors, dtype=object),
        "safety": np.asarray(json.dumps(payload["safety"], sort_keys=True)),
    })
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--device", choices=["cpu", "cuda", "mps"], default="cpu")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    result = run(args.input, args.model, args.out, args.device, args.batch_size, args.limit)
    print(json.dumps({"out": str(args.out), "n_files": result["n_files"],
                      "n_errors": result["n_errors"], "read_only": True}, indent=2))


if __name__ == "__main__":
    main()
