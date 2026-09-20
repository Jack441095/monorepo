#!/usr/bin/env python3
"""Build provenance-preserving nearest-neighbour evidence for audio queries.

The reference index may contain existing human taxonomy labels, so this branch
is explicitly *optional supervised-reference evidence*, not a claim of
label-free accuracy. Exact filename overlaps are detected and excluded from
the neighbour vote to reduce leakage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.neighbors import NearestNeighbors


VERSION = "label_free_retrieval_evidence_v1"


def _normalise(matrix: np.ndarray) -> np.ndarray:
    matrix = np.asarray(matrix, dtype=np.float32)
    if matrix.ndim != 2 or not matrix.shape[0] or not matrix.shape[1]:
        raise ValueError("embeddings must be a non-empty 2D matrix")
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    if np.any(norms <= 1e-8) or not np.all(np.isfinite(norms)):
        raise ValueError("embeddings contain zero or non-finite rows")
    return matrix / norms


def _scalar(payload: Any, key: str) -> str | None:
    if key not in payload.files:
        return None
    value = payload[key]
    if np.asarray(value).ndim == 0:
        return str(np.asarray(value).item())
    return None


def _load_query(path: Path) -> tuple[np.ndarray, list[str], str | None]:
    payload = np.load(path, allow_pickle=True)
    if "embeddings" not in payload or "paths" not in payload:
        raise ValueError("query index must contain embeddings and paths")
    matrix = np.asarray(payload["embeddings"], dtype=np.float32)
    paths = [str(value) for value in payload["paths"].tolist()]
    if len(paths) != len(matrix):
        raise ValueError("query embedding/path lengths differ")
    return _normalise(matrix), paths, _scalar(payload, "model")


def _load_reference(path: Path) -> tuple[np.ndarray, list[str], list[str], str | None]:
    payload = np.load(path, allow_pickle=True)
    keys = set(payload.files)
    if "embeddings" not in keys or "labels" not in keys or "filenames" not in keys:
        raise ValueError("reference index must contain embeddings, labels and filenames")
    matrix = np.asarray(payload["embeddings"], dtype=np.float32)
    labels = [str(value) for value in payload["labels"].tolist()]
    filenames = [str(value) for value in payload["filenames"].tolist()]
    if len(matrix) != len(labels) or len(matrix) != len(filenames):
        raise ValueError("reference embedding/label/filename lengths differ")
    return _normalise(matrix), labels, filenames, _scalar(payload, "model")


def _basename(path: str) -> str:
    return Path(str(path).replace("\\", "/")).name.casefold()


def build(query: Path, reference: Path, out: Path, top_k: int = 5,
          min_similarity: float = 0.45, min_margin: float = 0.02,
          limit: int | None = None) -> dict[str, Any]:
    if top_k < 1 or not 0.0 <= min_similarity <= 1.0 or min_margin < 0.0:
        raise ValueError("invalid retrieval thresholds")
    query_matrix, query_paths, query_model = _load_query(query)
    ref_matrix, ref_labels, ref_names, ref_model = _load_reference(reference)
    if not query_model or not ref_model:
        raise ValueError("query and reference indexes must declare the same model identity")
    if query_model != ref_model:
        raise ValueError("query and reference indexes use different feature spaces")
    if limit is not None:
        count = max(0, min(int(limit), len(query_paths)))
        query_matrix, query_paths = query_matrix[:count], query_paths[:count]
    index = NearestNeighbors(metric="cosine", n_neighbors=min(len(ref_matrix), top_k + 16),
                             n_jobs=-1).fit(ref_matrix)
    distances, indices = index.kneighbors(query_matrix)
    ref_by_name: dict[str, list[int]] = defaultdict(list)
    for idx, name in enumerate(ref_names):
        ref_by_name[_basename(name)].append(idx)
    rows: list[dict[str, Any]] = []
    n_overlap = 0
    for row_index, path in enumerate(query_paths):
        overlap_names = set(ref_by_name.get(_basename(path), []))
        if overlap_names:
            n_overlap += 1
        neighbours: list[dict[str, Any]] = []
        totals: dict[str, float] = defaultdict(float)
        for distance, ref_index in zip(distances[row_index], indices[row_index]):
            ref_index = int(ref_index)
            if ref_index in overlap_names:
                continue
            similarity = float(1.0 - distance)
            item = {"label": ref_labels[ref_index], "similarity": similarity,
                    "filename": ref_names[ref_index]}
            neighbours.append(item)
            # Positive cosine similarity is used as a conservative vote weight.
            totals[ref_labels[ref_index]] += max(0.0, similarity)
            if len(neighbours) >= top_k:
                break
        ranked = sorted(totals.items(), key=lambda pair: (-pair[1], pair[0]))
        candidate = ranked[0][0] if ranked else None
        candidate_score = ranked[0][1] / max(sum(totals.values()), 1e-12) if ranked else None
        second_score = ranked[1][1] / max(sum(totals.values()), 1e-12) if len(ranked) > 1 else 0.0
        margin = (candidate_score - second_score) if candidate_score is not None else None
        best_similarity = neighbours[0]["similarity"] if neighbours else None
        status = ("suggest" if candidate is not None and best_similarity is not None
                  and best_similarity >= min_similarity and (margin or 0.0) >= min_margin
                  else "review")
        rows.append({
            "path": path,
            "semantic_label": None,
            "status": status,
            "retrieval_candidate_label": candidate,
            "retrieval_similarity": best_similarity,
            "retrieval_vote_confidence": candidate_score,
            "retrieval_margin": margin,
            "retrieval_neighbors": neighbours,
            "exact_filename_overlap_excluded": bool(overlap_names),
            "calibration": "uncalibrated_reference_embedding_vote",
        })
    rows.sort(key=lambda row: row["path"])
    result = {
        "record_type": "slo_label_free_retrieval_evidence",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "source_query_index": str(query.resolve()),
        "source_query_index_sha256": hashlib.sha256(query.read_bytes()).hexdigest(),
        "source_reference_index": str(reference.resolve()),
        "source_reference_index_sha256": hashlib.sha256(reference.read_bytes()).hexdigest(),
        "feature_space_model": query_model,
        "n_queries": len(rows),
        "n_reference_rows": len(ref_matrix),
        "n_exact_filename_overlaps": n_overlap,
        "n_suggest": sum(row["status"] == "suggest" for row in rows),
        "n_review": sum(row["status"] == "review" for row in rows),
        "top_k": top_k,
        "min_similarity": min_similarity,
        "min_margin": min_margin,
        "rows": rows,
        "safety": {
            "read_only": True,
            "ground_truth_read": False,
            "reference_taxonomy_labels_read": True,
            "semantic_labels_created": False,
            "training_data_created": False,
            "rename_actions": False,
            "source_audio_modified": False,
            "auto_action_allowed": False,
            "human_approval_required": True,
        },
        "limitations": [
            "reference labels are existing taxonomy supervision, not label-free evidence",
            "nearest-neighbour votes are uncalibrated and review-only",
            "exact filename overlaps are excluded but near-duplicate leakage may remain",
        ],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--min-similarity", type=float, default=0.45)
    parser.add_argument("--min-margin", type=float, default=0.02)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    result = build(args.query, args.reference, args.out, args.top_k,
                   args.min_similarity, args.min_margin, args.limit)
    print(json.dumps({"out": str(args.out), "n_queries": result["n_queries"],
                      "n_suggest": result["n_suggest"],
                      "n_exact_filename_overlaps": result["n_exact_filename_overlaps"],
                      "read_only": True}, indent=2))


if __name__ == "__main__":
    main()
