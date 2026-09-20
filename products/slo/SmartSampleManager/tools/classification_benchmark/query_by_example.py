#!/usr/bin/env python3
"""Search the local sample library by example, with aspect explanations.

The query must already have an embedding in the supplied derived cache. This
keeps the first implementation deterministic and avoids silently using a
different encoder. Results are for discovery/review only; no semantic label or
rename action is produced.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from typing import Any

import numpy as np


SD = Path(__file__).resolve().parent
VERSION = "query_by_example_v1"


def _full_sha256(path: str | os.PathLike[str]) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def verify_content_identity(path: str | os.PathLike[str], identity: dict[str, Any]) -> bool:
    expected = identity.get("content_sha256") if isinstance(identity, dict) else None
    if not isinstance(expected, str) or len(expected) != 64:
        raise ValueError("content identity has no valid SHA-256")
    actual = _full_sha256(path)
    if actual != expected:
        raise ValueError("query content changed since the content index was built")
    return True


def _load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SD / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _normalise_rows(x: np.ndarray) -> np.ndarray:
    return x / np.maximum(np.linalg.norm(x, axis=1, keepdims=True), 1e-12)


def rank_embeddings(embeddings: np.ndarray, query_index: int, top_k: int) -> list[tuple[int, float]]:
    """Return top neighbours using a corpus-fitted standardised cosine."""
    if embeddings.ndim != 2 or not (0 <= query_index < len(embeddings)):
        raise ValueError("invalid embedding matrix or query index")
    if top_k < 1:
        raise ValueError("top_k must be positive")
    from sklearn.preprocessing import StandardScaler

    scaled = StandardScaler().fit_transform(np.asarray(embeddings, dtype=np.float32))
    query = _normalise_rows(scaled[[query_index]])[0]
    scores = _normalise_rows(scaled) @ query
    scores[query_index] = -np.inf
    order = np.argsort(-scores)[:min(top_k, len(scores) - 1)]
    return [(int(i), float(scores[i])) for i in order]


def _load_cards_for_paths(paths: list[str], analyser) -> tuple[dict[str, dict], list[dict]]:
    cards: dict[str, dict] = {}
    errors: list[dict] = []
    for path in paths:
        try:
            cards[os.path.abspath(path)] = analyser.analyse_file(path)
        except Exception as exc:
            errors.append({"path": path, "error": str(exc)})
    return cards, errors


def dedupe_ranked_by_content(ranked: list[tuple[int, float]], paths: list[str],
                             content_by_path: dict[str, dict[str, Any]],
                             query_identity: dict[str, Any] | None,
                             top_k: int) -> list[tuple[int, float]]:
    """Keep one path per content hash and remove aliases of the query."""
    seen = set()
    if query_identity and query_identity.get("content_sha256"):
        seen.add(query_identity["content_sha256"])
    output = []
    for index, score in ranked:
        identity = content_by_path.get(paths[index])
        key = identity.get("content_sha256") if identity else f"path:{paths[index]}"
        if key in seen:
            continue
        seen.add(key)
        output.append((index, score))
        if len(output) >= top_k:
            break
    return output


def build_search(query_path: str | os.PathLike[str], embeddings_path: Path,
                 top_k: int, evidence_k: int,
                 content_index_path: Path | None = None,
                 dedupe_content: bool = False) -> dict[str, Any]:
    query_abs = os.path.abspath(str(query_path))
    if not os.path.isfile(query_abs):
        raise ValueError(f"query file does not exist: {query_abs}")
    data = np.load(embeddings_path, allow_pickle=True)
    paths = [os.path.abspath(str(p)) for p in data["paths"]]
    matches = [i for i, path in enumerate(paths) if path == query_abs]
    if len(matches) != 1:
        raise ValueError("query must occur exactly once in the supplied embedding cache")
    embeddings = np.asarray(data["emb"], dtype=np.float32)
    query_index = matches[0]
    ranked = rank_embeddings(embeddings, query_index, top_k)
    content_by_path: dict[str, dict[str, Any]] = {}
    content_index_payload = None
    if content_index_path is not None:
        content_index_payload = json.loads(content_index_path.read_text(encoding="utf-8"))
        if content_index_payload.get("record_type") != "slo_content_addressed_embedding_index":
            raise ValueError("content index has an unexpected record type")
        for record in content_index_payload.get("records", []):
            for path in record.get("paths", []):
                content_by_path[os.path.abspath(path)] = {
                    "content_sha256": record.get("content_sha256"),
                    "canonical_path": record.get("canonical_path"),
                    "alias_paths": record.get("paths", []),
                }
        missing = [path for path in paths if path not in content_by_path]
        if missing:
            raise ValueError(f"content index is missing {len(missing)} embedding paths")
        if dedupe_content:
            ranked = dedupe_ranked_by_content(ranked, paths, content_by_path, content_by_path.get(query_abs), top_k)
    selected_paths = [query_abs] + [paths[i] for i, _ in ranked[:evidence_k]]
    analyser = _load_module("audio_definition_card", "audio_definition_card.py")
    aspect = _load_module("aspect_similarity", "aspect_similarity.py")
    cards, errors = _load_cards_for_paths(selected_paths, analyser)
    query_card = cards.get(query_abs)
    query_identity = content_by_path.get(query_abs)
    query_content_verified = False
    if content_index_path is not None:
        if query_identity is None:
            raise ValueError("content index has no query identity")
        query_content_verified = verify_content_identity(query_abs, query_identity)
    rows = []
    for index, embedding_score in ranked:
        path = paths[index]
        row = {"path": path, "embedding_cosine": embedding_score}
        if content_index_path is not None:
            row["content_identity"] = content_by_path[path]
        if query_card is not None and path in cards:
            row["aspect_similarity"] = aspect.compare_cards(query_card, cards[path])["similarity"]
            row["definition_card"] = cards[path]
        else:
            row["aspect_similarity"] = None
        rows.append(row)
    result = {
        "record_type": "slo_query_by_example_results",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "query": {"path": query_abs, "index": query_index, "content_identity": query_identity, "definition_card": query_card},
        "results": rows,
        "safety": {
            "read_only": True,
            "source_files_modified": False,
            "semantic_labels_created": False,
            "rename_actions": False,
            "similarity_is_not_class_probability": True,
            "content_aliases_deduplicated": bool(dedupe_content),
            "query_content_verified": query_content_verified,
        },
        "errors": errors,
        "embedding_cache": {
            "path": str(embeddings_path.resolve()),
            "sha256": hashlib.sha256(embeddings_path.read_bytes()).hexdigest(),
            "n_indexed": len(paths),
        },
    }
    if content_index_path is not None:
        result["content_index"] = {
            "path": str(content_index_path.resolve()),
            "sha256": hashlib.sha256(content_index_path.read_bytes()).hexdigest(),
            "n_content_ids": content_index_payload.get("n_content_ids"),
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", type=Path, required=True)
    parser.add_argument("--embeddings", type=Path, required=True)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--evidence-k", type=int, default=10)
    parser.add_argument("--content-index", type=Path)
    parser.add_argument("--dedupe-content", action="store_true",
                        help="collapse exact-content aliases and exclude query aliases")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = build_search(args.query, args.embeddings, args.top_k, args.evidence_k, args.content_index, args.dedupe_content)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "query": result["query"]["path"],
        "results": len(result["results"]),
        "physical_evidence_rows": sum(r.get("aspect_similarity") is not None for r in result["results"]),
        "errors": len(result["errors"]),
    }, indent=2))


if __name__ == "__main__":
    main()
