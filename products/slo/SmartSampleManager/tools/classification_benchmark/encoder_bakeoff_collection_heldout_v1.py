#!/usr/bin/env python3
"""Collection-held-out bake-off for cached MERT and AST encoders.

This is a research-only arm. It uses the corrected SLO corpus, identical
collection-held-out folds for every encoder, and local Hugging Face weights.
It never changes the production model, taxonomy, rename policy, or source
audio. Unlike the older encoder bake-off, this one does not use random CV.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import librosa
import numpy as np
import soundfile as sf
import torch


SD = Path(__file__).resolve().parent
MERT_ID = "m-a-p/MERT-v1-95M"
AST_ID = "MIT/ast-finetuned-audioset-10-10-0.4593"


def _path_hash(paths: list[str]) -> str:
    return hashlib.sha256("\n".join(paths).encode()).hexdigest()


def _load_wave(path: str, sr: int, seconds: float = 5.0) -> np.ndarray:
    wave, source_sr = sf.read(path, dtype="float32", always_2d=False)
    if wave.ndim > 1:
        wave = wave.mean(axis=1)
    if int(source_sr) != sr:
        wave = librosa.resample(wave, orig_sr=int(source_sr), target_sr=sr)
    n = int(sr * seconds)
    out = np.zeros(n, dtype=np.float32)
    out[: min(len(wave), n)] = wave[:n]
    return out


def _device() -> torch.device:
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def _mert(paths: list[str], batch: int, device: torch.device) -> np.ndarray:
    from transformers import AutoModel, Wav2Vec2FeatureExtractor

    extractor = Wav2Vec2FeatureExtractor.from_pretrained(
        MERT_ID, local_files_only=True, trust_remote_code=True
    )
    model = AutoModel.from_pretrained(
        MERT_ID, local_files_only=True, trust_remote_code=True
    ).eval().to(device)
    sr = int(extractor.sampling_rate)
    chunks: list[np.ndarray] = []
    with torch.no_grad():
        for start in range(0, len(paths), batch):
            waves = [_load_wave(path, sr) for path in paths[start : start + batch]]
            inputs = extractor(waves, sampling_rate=sr, return_tensors="pt", padding=True)
            inputs = {key: value.to(device) for key, value in inputs.items()}
            hidden = model(**inputs, output_hidden_states=False).last_hidden_state
            chunks.append(hidden.mean(dim=1).detach().cpu().numpy().astype(np.float32))
            if start and start % (batch * 20) == 0:
                print(f"  MERT {start}/{len(paths)}", flush=True)
    return np.concatenate(chunks, axis=0)


def _ast(paths: list[str], batch: int, device: torch.device) -> np.ndarray:
    from transformers import ASTFeatureExtractor, ASTModel

    extractor = ASTFeatureExtractor.from_pretrained(AST_ID, local_files_only=True)
    model = ASTModel.from_pretrained(AST_ID, local_files_only=True).eval().to(device)
    chunks: list[np.ndarray] = []
    with torch.no_grad():
        for start in range(0, len(paths), batch):
            waves = [_load_wave(path, 16000) for path in paths[start : start + batch]]
            inputs = extractor(waves, sampling_rate=16000, return_tensors="pt")
            inputs = {key: value.to(device) for key, value in inputs.items()}
            pooled = model(**inputs).pooler_output
            chunks.append(pooled.detach().cpu().numpy().astype(np.float32))
            if start and start % (batch * 20) == 0:
                print(f"  AST {start}/{len(paths)}", flush=True)
    return np.concatenate(chunks, axis=0)


def _load_or_extract(paths: list[str], cache_path: Path, batch: int, device: torch.device,
                     extract: bool) -> tuple[np.ndarray, np.ndarray]:
    ph = _path_hash(paths)
    if cache_path.exists():
        cached = np.load(cache_path, allow_pickle=True)
        if str(cached.get("paths_hash", "")) == ph and len(cached["paths"]) == len(paths):
            print(f"loaded cached MERT/AST embeddings: {cache_path}")
            return np.asarray(cached["mert"], dtype=np.float32), np.asarray(cached["ast"], dtype=np.float32)
    if not extract:
        raise SystemExit("FAIL CLOSED: MERT/AST cache is absent or does not match the corpus")
    print(f"extracting MERT locally on {device} for {len(paths)} files", flush=True)
    mert = _mert(paths, batch, device)
    print(f"extracting AST locally on {device} for {len(paths)} files", flush=True)
    ast = _ast(paths, batch, device)
    if len(mert) != len(paths) or len(ast) != len(paths):
        raise SystemExit("FAIL CLOSED: encoder output row count mismatch")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cache_path, paths=np.asarray(paths), paths_hash=ph, mert=mert, ast=ast)
    return mert, ast


def _predict(x_train: np.ndarray, y_train: np.ndarray, x_test: np.ndarray,
             classes: list[str]) -> tuple[np.ndarray, np.ndarray]:
    mean = x_train.mean(axis=0)
    scale = x_train.std(axis=0)
    scale[scale < 1e-8] = 1.0
    train = (x_train - mean) / scale
    test = (x_test - mean) / scale
    train /= np.linalg.norm(train, axis=1, keepdims=True) + 1e-9
    test /= np.linalg.norm(test, axis=1, keepdims=True) + 1e-9
    centroids = np.vstack([train[y_train == cls].mean(axis=0) for cls in classes])
    centroids /= np.linalg.norm(centroids, axis=1, keepdims=True) + 1e-9
    similarities = test @ centroids.T
    indices = similarities.argmax(axis=1)
    return np.asarray(classes)[indices], similarities.max(axis=1)


def _coverage(confidence: np.ndarray, correct: np.ndarray, target: float) -> float:
    order = np.argsort(-confidence)
    cumulative = np.cumsum(correct[order]) / np.arange(1, len(order) + 1)
    valid = np.where(cumulative >= target)[0]
    return float((valid[-1] + 1) / len(order)) if len(valid) else 0.0


def _evaluate(arms: dict[str, np.ndarray], labels: np.ndarray, groups: np.ndarray,
              classes: list[str], seeds: int, splits: int) -> dict[str, Any]:
    from sklearn.metrics import f1_score
    from sklearn.model_selection import StratifiedGroupKFold

    results: dict[str, Any] = {}
    for arm_name, features in arms.items():
        per_seed: list[dict[str, float]] = []
        for seed in range(seeds):
            oof = np.empty(len(labels), dtype=object)
            confidence = np.zeros(len(labels), dtype=np.float32)
            cv = StratifiedGroupKFold(n_splits=splits, shuffle=True, random_state=seed)
            for train_idx, test_idx in cv.split(features, labels, groups):
                overlap = set(groups[train_idx]) & set(groups[test_idx])
                if overlap:
                    raise AssertionError(f"collection leakage: {sorted(overlap)[:3]}")
                pred, conf = _predict(features[train_idx], labels[train_idx], features[test_idx], classes)
                oof[test_idx] = pred
                confidence[test_idx] = conf
            correct = (oof == labels).astype(float)
            per_seed.append({
                "accuracy": float(correct.mean()),
                "macro_f1": float(f1_score(labels, oof.astype(str), average="macro", zero_division=0)),
                "coverage_at_90_precision": _coverage(confidence, correct, 0.90),
                "coverage_at_95_precision": _coverage(confidence, correct, 0.95),
            })
        results[arm_name] = {
            "dimensions": int(features.shape[1]),
            "accuracy_mean": float(np.mean([row["accuracy"] for row in per_seed])),
            "accuracy_sd": float(np.std([row["accuracy"] for row in per_seed])),
            "macro_f1_mean": float(np.mean([row["macro_f1"] for row in per_seed])),
            "coverage_at_90_precision_mean": float(np.mean([row["coverage_at_90_precision"] for row in per_seed])),
            "coverage_at_95_precision_mean": float(np.mean([row["coverage_at_95_precision"] for row in per_seed])),
            "per_seed": per_seed,
        }
    baseline = results["perch_clap_control"]["accuracy_mean"]
    for value in results.values():
        value["delta_accuracy_pp_vs_perch_clap_control"] = 100.0 * (value["accuracy_mean"] - baseline)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=SD / "corpus_granularity_relabelled_v1.npz")
    parser.add_argument("--cache", type=Path, default=SD / "mert_ast_granularity_embeddings_v1.npz")
    parser.add_argument("--out", type=Path, default=SD / "results_encoder_bakeoff_collection_heldout_v1.json")
    parser.add_argument("--batch", type=int, default=4)
    parser.add_argument("--seeds", type=int, default=8)
    parser.add_argument("--splits", type=int, default=5)
    parser.add_argument("--min-examples", type=int, default=5)
    parser.add_argument("--min-collections", type=int, default=5)
    parser.add_argument("--extract", action="store_true")
    parser.add_argument("--skip-eval", action="store_true")
    args = parser.parse_args()
    if args.batch < 1 or args.seeds < 1 or args.splits < 2:
        raise SystemExit("FAIL CLOSED: batch/seeds/splits are invalid")

    full = __import__("importlib.util").util.spec_from_file_location("slo_full_taxonomy_eval", SD / "full_taxonomy_eval.py")
    module = __import__("importlib.util").util.module_from_spec(full)
    assert full and full.loader
    full.loader.exec_module(module)
    corpus = module.load(str(args.corpus))
    inventory = module.eligible_classes(corpus, args.min_examples, args.min_collections)
    classes = [name for name, info in inventory.items() if info["eligible"]]
    # Smoke extraction may intentionally use a tiny corpus that cannot satisfy
    # grouped-evaluation support thresholds; only the evaluation path needs
    # the eligible-class filter.
    keep = np.ones(len(corpus["labels"]), dtype=bool) if args.skip_eval else np.isin(corpus["labels"], classes)
    paths = [str(path) for path, flag in zip(corpus["paths"], keep) if flag]
    labels = np.asarray(corpus["labels"])[keep].astype(str)
    groups = np.asarray(corpus["vendor"])[keep].astype(str)
    if not args.skip_eval and len(set(groups)) < args.splits:
        raise SystemExit("FAIL CLOSED: fewer collections than grouped folds")

    mert, ast = _load_or_extract(paths, args.cache, args.batch, _device(), args.extract)
    if args.skip_eval:
        print(json.dumps({"n_files": len(paths), "mert_dimensions": int(mert.shape[1]), "ast_dimensions": int(ast.shape[1])}, indent=2))
        return 0

    base = np.asarray(corpus["X"])[keep].astype(np.float32)
    arms = {
        "perch_clap_control": base,
        "mert": mert,
        "ast": ast,
        "perch_clap_plus_mert": np.hstack([base, mert]),
        "perch_clap_plus_ast": np.hstack([base, ast]),
        "perch_clap_plus_mert_plus_ast": np.hstack([base, mert, ast]),
    }
    results = _evaluate(arms, labels, groups, classes, args.seeds, args.splits)
    payload = {
        "record_type": "slo_encoder_bakeoff_collection_heldout",
        "schema_version": "1.0.0",
        "method_version": "encoder_bakeoff_collection_heldout_v1",
        "safety": {"read_only": True, "source_audio_modified": False,
                   "production_model_changed": False, "rename_actions": False,
                   "gpu_1_touched": False},
        "protocol": {"split": "StratifiedGroupKFold by vendor/collection",
                     "seeds": args.seeds, "splits": args.splits,
                     "min_examples": args.min_examples,
                     "min_collections": args.min_collections,
                     "window_seconds": 5.0,
                     "feature_scaling": "fit standardisation on train fold, cosine nearest centroid",
                     "control": "same corrected corpus Perch+CLAP embeddings for every arm"},
        "corpus": {"path": str(args.corpus.resolve()), "path_hash": _path_hash(paths),
                   "n_files": len(paths), "n_classes": len(classes),
                   "n_collections": len(set(groups)), "classes": classes},
        "encoders": {"mert": MERT_ID, "ast": AST_ID,
                     "mert_dimensions": int(mert.shape[1]), "ast_dimensions": int(ast.shape[1])},
        "results": results,
        "decision": "research_only; no promotion unless a new arm clears the pre-registered +2pp gate and class/rejection gates",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({name: {key: value for key, value in data.items() if key.endswith("mean") or key.startswith("delta_")} for name, data in results.items()}, indent=2))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
