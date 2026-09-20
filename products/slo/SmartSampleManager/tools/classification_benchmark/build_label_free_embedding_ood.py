#!/usr/bin/env python3
"""Compute a read-only leave-one-out embedding novelty signal.

The signal is corpus-relative, not a probability: a file unlike its nearest
supported-corpus neighbours receives a higher novelty score and should be
reviewed before any semantic candidate is trusted.  No labels or file actions
are created.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np


VERSION = "label_free_embedding_ood_v1"


def _load_embeddings(path: Path) -> tuple[dict[str, Any], np.ndarray, list[str]]:
    data = np.load(path, allow_pickle=True)
    if "embeddings" not in data or "paths" not in data:
        raise ValueError("embedding index must contain embeddings and paths")
    embeddings = np.asarray(data["embeddings"], dtype=np.float32)
    paths = [str(value) for value in data["paths"].tolist()]
    if embeddings.ndim != 2 or len(paths) != embeddings.shape[0] or not len(paths):
        raise ValueError("embedding index shapes are invalid")
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    if np.any(~np.isfinite(embeddings)) or np.any(norms <= 0):
        raise ValueError("embedding index contains non-finite or zero vectors")
    embeddings = embeddings / norms
    return {"record_type": str(data["record_type"].item()) if "record_type" in data else None,
            "method_version": str(data["method_version"].item()) if "method_version" in data else None,
            "safety": data["safety"].item() if "safety" in data else {}}, embeddings, paths


def _decision_map(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("record_type") != "slo_label_free_fused_decision_receipt":
        raise ValueError("decisions input is not a fused decision receipt")
    safety = payload.get("safety") or {}
    if (not safety.get("read_only") or safety.get("semantic_labels_created")
            or safety.get("rename_actions") or safety.get("auto_action_allowed")):
        raise ValueError("decisions input is not read-only")
    return {str(row["path"]): row for row in payload.get("rows", [])
            if isinstance(row, dict) and isinstance(row.get("path"), str)}


def build(embeddings: Path, out: Path, k: int = 5,
          decisions: Path | None = None, block_size: int = 512) -> dict[str, Any]:
    if k < 1 or block_size < 1:
        raise ValueError("k and block_size must be positive")
    source_meta, vectors, paths = _load_embeddings(embeddings)
    decision_by_path = _decision_map(decisions)
    n = vectors.shape[0]
    k_eff = min(k, max(1, n - 1))
    nearest = np.empty(n, dtype=np.float32)
    means = np.empty(n, dtype=np.float32)
    # Blocked matrix products keep peak memory bounded for the full 8.6k index.
    for start in range(0, n, block_size):
        stop = min(n, start + block_size)
        scores = vectors[start:stop] @ vectors.T
        local = np.arange(stop - start)
        scores[local, np.arange(start, stop)] = -np.inf
        top = np.partition(scores, scores.shape[1] - k_eff, axis=1)[:, -k_eff:]
        nearest[start:stop] = np.max(top, axis=1)
        means[start:stop] = np.mean(top, axis=1)
    rows: list[dict[str, Any]] = []
    for index, path in enumerate(paths):
        decision = decision_by_path.get(path)
        rows.append({
            "path": path,
            "semantic_label": None,
            "nearest_neighbor_cosine": float(nearest[index]),
            "knn_mean_cosine": float(means[index]),
            "novelty_score": float(1.0 - means[index]),
            "knn_k": k_eff,
            "fused_decision": decision.get("decision") if decision else None,
            "candidate_scope": decision.get("candidate_scope") if decision else None,
            "ood_action": "review" if float(1.0 - means[index]) >= 0.35 else "unchanged",
        })
    rows.sort(key=lambda row: (-row["novelty_score"], row["path"]))
    payload = {
        "record_type": "slo_label_free_embedding_ood_receipt",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "source_embeddings": str(embeddings.resolve()),
        "source_embeddings_sha256": hashlib.sha256(embeddings.read_bytes()).hexdigest(),
        "source_embedding_method_version": source_meta.get("method_version"),
        "source_decisions": str(decisions.resolve()) if decisions else None,
        "source_decisions_sha256": hashlib.sha256(decisions.read_bytes()).hexdigest() if decisions else None,
        "n_files": len(rows),
        "knn_k": k_eff,
        "novelty_review_threshold": 0.35,
        "n_novelty_review": sum(row["ood_action"] == "review" for row in rows),
        "n_joined_decisions": sum(row["fused_decision"] is not None for row in rows),
        "rows": rows,
        "calibration": "corpus_relative_leave_one_out_knn_novelty_uncalibrated",
        "accuracy_claim": None,
        "safety": {
            "read_only": True,
            "ground_truth_read": False,
            "semantic_labels_created": False,
            "rename_actions": False,
            "source_audio_modified": False,
            "auto_action_allowed": False,
            "human_approval_required": True,
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embeddings", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--decisions", type=Path)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--block-size", type=int, default=512)
    args = parser.parse_args()
    result = build(args.embeddings, args.out, args.k, args.decisions, args.block_size)
    print(json.dumps({"out": str(args.out), "n_files": result["n_files"],
                      "n_novelty_review": result["n_novelty_review"],
                      "read_only": True}, indent=2))


if __name__ == "__main__":
    main()
