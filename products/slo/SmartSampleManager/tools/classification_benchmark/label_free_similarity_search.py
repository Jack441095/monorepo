#!/usr/bin/env python3
"""Read-only nearest-neighbour search over a label-free audio embedding index.

The index contains normalized vectors and source paths, not semantic labels.
Results are similarity evidence for browsing/review and never trigger rename,
metadata, or source-audio actions.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any

import numpy as np


VERSION = "label_free_similarity_search_v1"


def _load_index(path: Path) -> tuple[dict[str, Any], np.ndarray, np.ndarray]:
    payload = np.load(path, allow_pickle=True)
    record_type = str(payload["record_type"])
    if record_type != "slo_label_free_audio_embedding_index":
        raise ValueError("incompatible embedding index record_type")
    safety = json.loads(str(payload["safety"]))
    if not safety.get("read_only") or safety.get("semantic_labels_created") or safety.get("rename_actions"):
        raise ValueError("embedding index is not read-only")
    paths = np.asarray(payload["paths"])
    vectors = np.asarray(payload["embeddings"], dtype=np.float32)
    if paths.ndim != 1 or vectors.ndim != 2 or len(paths) != len(vectors):
        raise ValueError("embedding index paths/vectors have incompatible shapes")
    if len(set(str(x) for x in paths)) != len(paths):
        raise ValueError("embedding index contains duplicate paths")
    norms = np.linalg.norm(vectors, axis=1)
    if not np.all(np.isfinite(vectors)) or not np.allclose(norms, 1.0, atol=2e-3):
        raise ValueError("embedding index vectors must be finite and normalized")
    header = {
        "record_type": record_type,
        "schema_version": str(payload["schema_version"]),
        "method_version": str(payload["method_version"]),
        "model": str(payload["model"]),
        "views": int(payload["views"]),
        "safety": safety,
    }
    return header, paths.astype(str), vectors


def _query_vector(path: Path, model_dir: Path, device: str) -> np.ndarray:
    """Embed one external query using the same CLAP contract as the index."""
    runner_path = Path(__file__).with_name("label_free_zero_shot.py")
    spec = importlib.util.spec_from_file_location("label_free_zero_shot", runner_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load label-free runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    processor, model = module._load_model(model_dir, device)
    audio = module.load_audio(path)
    with module.torch.no_grad():
        inputs = processor(audio=[audio], sampling_rate=module.SAMPLE_RATE,
                           return_tensors="pt", padding=True)
        inputs = {key: value.to(device) for key, value in inputs.items()}
        vector = module._embedding_tensor(model.get_audio_features(**inputs))[0]
        vector = module.torch.nn.functional.normalize(vector, dim=-1).cpu().numpy()
    return np.asarray(vector, dtype=np.float32)


def search(index: Path, query_index: int | None = None,
           query_path: Path | None = None, model: Path | None = None,
           device: str = "cpu", top_k: int = 20,
           exclude_self: bool = True) -> dict[str, Any]:
    if (query_index is None) == (query_path is None):
        raise ValueError("provide exactly one of query_index or query_path")
    header, paths, vectors = _load_index(index)
    if top_k < 1:
        raise ValueError("top_k must be positive")
    if query_index is not None:
        if not 0 <= query_index < len(vectors):
            raise ValueError("query_index is out of range")
        query = vectors[query_index]
        query_source = str(paths[query_index])
        query_index_value: int | None = query_index
    else:
        if model is None:
            raise ValueError("model is required for an external query path")
        query = _query_vector(query_path, model, device)
        query_source = str(query_path.resolve())
        query_index_value = None
    query = np.asarray(query, dtype=np.float32).reshape(-1)
    if query.shape[0] != vectors.shape[1] or not np.all(np.isfinite(query)):
        raise ValueError("query vector dimension or values do not match the index")
    query_norm = float(np.linalg.norm(query))
    if query_norm <= 1e-8:
        raise ValueError("query vector is zero")
    query = query / query_norm
    scores = vectors @ query
    if query_index is not None and exclude_self:
        scores[query_index] = -np.inf
    order = np.argsort(-scores)[: min(top_k, len(scores))]
    results = [{"rank": i + 1, "path": str(paths[int(idx)]),
                "cosine_similarity": float(scores[int(idx)])}
               for i, idx in enumerate(order) if np.isfinite(scores[int(idx)])]
    return {
        "record_type": "slo_label_free_similarity_search",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "index": str(index.resolve()),
        "index_model": header["model"],
        "index_size": len(vectors),
        "query": {"source": query_source, "index": query_index_value},
        "top_k": len(results),
        "results": results,
        "calibration": "uncalibrated_embedding_cosine_similarity",
        "safety": {
            "read_only": True,
            "semantic_labels_created": False,
            "ground_truth_read": False,
            "rename_actions": False,
            "source_audio_modified": False,
            "human_approval_required": True,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True)
    query = parser.add_mutually_exclusive_group(required=True)
    query.add_argument("--query-index", type=int)
    query.add_argument("--query-path", type=Path)
    parser.add_argument("--model", type=Path, help="required with --query-path")
    parser.add_argument("--device", choices=["cpu", "cuda", "mps"], default="cpu")
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--include-self", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = search(args.index, args.query_index, args.query_path, args.model,
                    args.device, args.top_k, not args.include_self)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(args.out), "top_k": result["top_k"], "read_only": True}, indent=2))


if __name__ == "__main__":
    main()
