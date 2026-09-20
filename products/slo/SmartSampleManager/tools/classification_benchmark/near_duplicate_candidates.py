#!/usr/bin/env python3
"""Find conservative acoustic near-duplicate candidates from embeddings.

This is deliberately separate from byte-identity grouping. A high embedding
cosine is only a review cue: it cannot prove two files are duplicates and never
authorizes deletion, replacement, or renaming.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np


VERSION = "near_duplicate_candidates_v1"


def _normalise(x: np.ndarray) -> np.ndarray:
    return x / np.maximum(np.linalg.norm(x, axis=1, keepdims=True), 1e-12)


def build_candidates(embeddings: np.ndarray, paths: list[str], threshold: float = 0.98,
                     neighbours: int = 8) -> dict[str, Any]:
    if embeddings.ndim != 2 or len(embeddings) != len(paths):
        raise ValueError("embedding matrix and paths must have matching rows")
    if not 0.0 < threshold <= 1.0:
        raise ValueError("threshold must be in (0, 1]")
    if neighbours < 1:
        raise ValueError("neighbours must be positive")
    from sklearn.neighbors import NearestNeighbors
    vectors = _normalise(np.asarray(embeddings, dtype=np.float32))
    k = min(neighbours + 1, len(vectors))
    search = NearestNeighbors(n_neighbors=k, metric="cosine", algorithm="brute", n_jobs=-1)
    search.fit(vectors)
    distances, indices = search.kneighbors(vectors)
    edges: dict[tuple[int, int], float] = {}
    for row_index, (row_distances, row_indices) in enumerate(zip(distances, indices)):
        for distance, candidate in zip(row_distances, row_indices):
            candidate = int(candidate)
            if candidate == row_index:
                continue
            score = 1.0 - float(distance)
            if score < threshold:
                continue
            pair = tuple(sorted((row_index, candidate)))
            edges[pair] = max(edges.get(pair, -1.0), score)

    # Union connected high-similarity edges into review groups. These are not
    # asserted duplicates; transitive groups are merely convenient for review.
    parent = list(range(len(paths)))

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: int, right: int) -> None:
        left, right = find(left), find(right)
        if left != right:
            parent[right] = left

    for left, right in edges:
        union(left, right)
    members: dict[int, list[int]] = {}
    for index in range(len(paths)):
        root = find(index)
        members.setdefault(root, []).append(index)
    groups = []
    for group_indices in members.values():
        if len(group_indices) < 2:
            continue
        group_set = set(group_indices)
        group_edges = [
            {"left_index": left, "right_index": right, "embedding_cosine": round(score, 8),
             "left_path": os.path.abspath(str(paths[left])),
             "right_path": os.path.abspath(str(paths[right]))}
            for (left, right), score in sorted(edges.items(), key=lambda item: -item[1])
            if left in group_set and right in group_set
        ]
        ordered_paths = sorted(os.path.abspath(str(paths[index])) for index in group_indices)
        groups.append({
            "canonical_display_path": ordered_paths[0],
            "member_paths": ordered_paths,
            "member_count": len(ordered_paths),
            "edges": group_edges,
            "decision": "review_only_acoustic_near_duplicate",
        })
    groups.sort(key=lambda group: group["canonical_display_path"])
    return {
        "record_type": "slo_near_duplicate_candidates",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "threshold": threshold,
        "neighbours": neighbours,
        "n_input": len(paths),
        "n_edges": len(edges),
        "n_groups": len(groups),
        "n_group_members": sum(group["member_count"] for group in groups),
        "groups": groups,
        "safety": {
            "read_only": True,
            "source_audio_modified": False,
            "byte_identity_proven": False,
            "files_deleted": False,
            "files_moved": False,
            "rename_actions": False,
            "acoustic_similarity_is_not_duplicate_proof": True,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embeddings", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--threshold", type=float, default=0.995)
    parser.add_argument("--neighbours", type=int, default=8)
    args = parser.parse_args()
    data = np.load(args.embeddings, allow_pickle=True)
    result = build_candidates(np.asarray(data["emb"], dtype=np.float32), [str(value) for value in data["paths"]], args.threshold, args.neighbours)
    result["embedding_cache"] = {"path": str(args.embeddings.resolve()), "sha256": hashlib.sha256(args.embeddings.read_bytes()).hexdigest()}
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"n_input": result["n_input"], "n_edges": result["n_edges"], "n_groups": result["n_groups"], "n_group_members": result["n_group_members"]}, indent=2))


if __name__ == "__main__":
    main()
