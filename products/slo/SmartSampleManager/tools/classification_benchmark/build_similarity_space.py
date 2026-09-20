#!/usr/bin/env python3
"""Build a deterministic 2-D visual similarity space from local embeddings.

The coordinates are an exploration aid for nearest-neighbour browsing and
label-queue design. They are not semantic predictions, taxonomy boundaries, or
rename instructions. No clustering or label assignment is performed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np


VERSION = "similarity_space_pca_v1"


def build_space(embeddings: np.ndarray, paths: list[str], n_components: int = 2) -> dict[str, Any]:
    if embeddings.ndim != 2 or len(embeddings) != len(paths):
        raise ValueError("embedding matrix and paths must have matching rows")
    if n_components != 2:
        raise ValueError("this visual artifact requires exactly two components")
    from sklearn.decomposition import PCA
    # PCA is deterministic and keeps the map reproducible across runs. The
    # embedding cache itself remains the source of truth for search.
    model = PCA(n_components=2, svd_solver="auto", random_state=0)
    coordinates = model.fit_transform(np.asarray(embeddings, dtype=np.float32))
    rows = [
        {"index": int(index), "path": os.path.abspath(str(path)),
         "x": float(coordinates[index, 0]), "y": float(coordinates[index, 1])}
        for index, path in enumerate(paths)
    ]
    return {
        "record_type": "slo_visual_similarity_space",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "n_points": len(rows),
        "embedding_dimensions": int(embeddings.shape[1]),
        "explained_variance_ratio": [float(value) for value in model.explained_variance_ratio_],
        "points": rows,
        "safety": {
            "read_only": True,
            "source_audio_modified": False,
            "labels_created": False,
            "clusters_created": False,
            "taxonomy_inferred": False,
            "rename_actions": False,
            "coordinates_are_not_class_probabilities": True,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embeddings", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    data = np.load(args.embeddings, allow_pickle=True)
    embeddings = np.asarray(data["emb"], dtype=np.float32)
    paths = [str(value) for value in data["paths"]]
    result = build_space(embeddings, paths)
    result["embedding_cache"] = {
        "path": str(args.embeddings.resolve()),
        "sha256": hashlib.sha256(args.embeddings.read_bytes()).hexdigest(),
    }
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"n_points": result["n_points"], "embedding_dimensions": result["embedding_dimensions"], "explained_variance_ratio": result["explained_variance_ratio"]}, indent=2))


if __name__ == "__main__":
    main()
