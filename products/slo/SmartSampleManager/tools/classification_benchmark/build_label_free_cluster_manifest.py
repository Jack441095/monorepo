#!/usr/bin/env python3
"""Build an unsupervised, label-free discovery manifest from embeddings.

Clusters are hypotheses for taxonomy discovery and specialist routing.  The
tool never assigns semantic labels, reads ground truth, or modifies audio.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.cluster import DBSCAN
from sklearn.neighbors import NearestNeighbors, sort_graph_by_row_values


VERSION = "label_free_cluster_manifest_v1"


def _normalise(embeddings: np.ndarray) -> np.ndarray:
    matrix = np.asarray(embeddings, dtype=np.float32)
    if matrix.ndim != 2 or not matrix.shape[0] or not matrix.shape[1]:
        raise ValueError("embeddings must be a non-empty 2D matrix")
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    if np.any(norms <= 1e-8) or not np.all(np.isfinite(norms)):
        raise ValueError("embeddings contain zero or non-finite rows")
    return matrix / norms


def _cluster(matrix: np.ndarray, eps: float, min_samples: int) -> np.ndarray:
    if eps <= 0 or min_samples < 1:
        raise ValueError("eps must be positive and min_samples >= 1")
    # A sparse radius graph avoids materialising an O(n^2) dense distance
    # matrix for large libraries while DBSCAN still receives exact cosine
    # neighbourhoods.
    graph = NearestNeighbors(metric="cosine", radius=eps, n_jobs=-1).fit(matrix)
    distances = graph.radius_neighbors_graph(matrix, mode="distance")
    distances = sort_graph_by_row_values(distances, warn_when_not_sorted=False)
    model = DBSCAN(eps=eps, min_samples=min_samples, metric="precomputed", n_jobs=-1)
    return model.fit_predict(distances)


def build(embeddings_path: Path, out: Path, eps: float = 0.12,
          min_samples: int = 3, limit: int | None = None) -> dict[str, Any]:
    payload = np.load(embeddings_path, allow_pickle=True)
    if "embeddings" not in payload or "paths" not in payload:
        raise ValueError("embedding index must contain embeddings and paths")
    paths = [str(value) for value in payload["paths"].tolist()]
    matrix = np.asarray(payload["embeddings"], dtype=np.float32)
    if len(paths) != len(matrix):
        raise ValueError("embedding/path lengths differ")
    if limit is not None:
        count = max(0, min(int(limit), len(paths)))
        paths, matrix = paths[:count], matrix[:count]
    matrix = _normalise(matrix)
    cluster_ids = _cluster(matrix, eps, min_samples)
    clusters: dict[int, list[int]] = {}
    for index, cluster_id in enumerate(cluster_ids.tolist()):
        clusters.setdefault(int(cluster_id), []).append(index)
    rows: list[dict[str, Any]] = []
    cluster_summaries: list[dict[str, Any]] = []
    for cluster_id, members in sorted(clusters.items()):
        if cluster_id < 0:
            continue
        centroid = matrix[members].mean(axis=0)
        centroid /= max(float(np.linalg.norm(centroid)), 1e-8)
        ranked = sorted(members, key=lambda index: float(1.0 - np.dot(matrix[index], centroid)))
        cluster_summaries.append({
            "cluster_id": cluster_id,
            "size": len(members),
            "representative_paths": [paths[index] for index in ranked[:5]],
            "representative_distances": [
                float(1.0 - np.dot(matrix[index], centroid)) for index in ranked[:5]
            ],
            "semantic_label": None,
        })
    for index, (path, cluster_id) in enumerate(zip(paths, cluster_ids.tolist())):
        members = clusters[int(cluster_id)] if int(cluster_id) >= 0 else []
        if members:
            centroid = matrix[members].mean(axis=0)
            centroid /= max(float(np.linalg.norm(centroid)), 1e-8)
            distance = float(1.0 - np.dot(matrix[index], centroid))
        else:
            distance = None
        rows.append({
            "path": path,
            "cluster_id": int(cluster_id),
            "cluster_size": len(members),
            "distance_to_cluster_centroid": distance,
            "discovery_status": "cluster_hypothesis" if cluster_id >= 0 else "noise_review",
            "semantic_label": None,
        })
    rows.sort(key=lambda row: row["path"])
    non_noise = [int(value) for value in cluster_ids.tolist() if value >= 0]
    cluster_sizes = sorted((len(indexes) for cid, indexes in clusters.items() if cid >= 0), reverse=True)
    result = {
        "record_type": "slo_label_free_cluster_manifest",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "source_embedding_index": str(embeddings_path.resolve()),
        "source_embedding_index_sha256": hashlib.sha256(embeddings_path.read_bytes()).hexdigest(),
        "n_rows": len(rows),
        "n_clusters": len([cid for cid in clusters if cid >= 0]),
        "n_noise": len(rows) - len(non_noise),
        "largest_cluster": cluster_sizes[0] if cluster_sizes else 0,
        "cluster_summaries": cluster_summaries,
        "eps_cosine_distance": eps,
        "min_samples": min_samples,
        "rows": rows,
        "safety": {
            "read_only": True,
            "ground_truth_read": False,
            "semantic_labels_created": False,
            "training_data_created": False,
            "rename_actions": False,
            "source_audio_modified": False,
            "human_approval_required": True,
            "clusters_are_hypotheses": True,
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embeddings", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--eps", type=float, default=0.12)
    parser.add_argument("--min-samples", type=int, default=3)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    result = build(args.embeddings, args.out, args.eps, args.min_samples, args.limit)
    print(json.dumps({"out": str(args.out), "n_rows": result["n_rows"],
                      "n_clusters": result["n_clusters"], "n_noise": result["n_noise"],
                      "read_only": True}, indent=2))


if __name__ == "__main__":
    main()
