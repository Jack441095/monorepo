#!/usr/bin/env python3
"""Build a non-mutating evidence packet for review-only rename suggestions.

Each row combines the existing prediction with a physical definition card and
the nearest labelled reference sample in the predicted class. It is intended
to make human review faster and more auditable; it cannot approve, rename, or
create a training label.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import tempfile
from pathlib import Path

import numpy as np


SD = Path(__file__).resolve().parent


def _load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SD / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def load_jsonl(path: Path) -> tuple[dict, list[dict]]:
    header = None
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if header is None and row.get("record_type") and "path" not in row:
                header = row
            else:
                rows.append(row)
    if header is None:
        raise ValueError(f"missing JSONL header in {path}")
    return header, rows


def _normalise_rows(x: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(x, axis=1, keepdims=True)
    return x / np.maximum(norm, 1e-12)


def nearest_references(candidate_paths: list[str], candidate_emb: np.ndarray,
                       corpus_paths: list[str], corpus_emb: np.ndarray,
                       corpus_labels: np.ndarray, predicted_labels: list[str]) -> list[dict]:
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler().fit(corpus_emb)
    c = _normalise_rows(scaler.transform(candidate_emb))
    r = _normalise_rows(scaler.transform(corpus_emb))
    corpus_abs_paths = np.asarray([os.path.abspath(path) for path in corpus_paths])
    out = []
    for i, predicted in enumerate(predicted_labels):
        eligible = np.flatnonzero(corpus_labels == predicted)
        # A suggestion can be a relabel/review row already present in the
        # corpus. Never use the same physical file as its own explanation
        # reference; that would create a perfect, circular aspect match.
        eligible = eligible[corpus_abs_paths[eligible] != os.path.abspath(candidate_paths[i])]
        reference_scope = "predicted_class"
        if not len(eligible):
            eligible = np.flatnonzero(corpus_abs_paths != os.path.abspath(candidate_paths[i]))
            reference_scope = "all_labelled_classes"
        scores = r[eligible] @ c[i]
        winner = int(eligible[int(np.argmax(scores))])
        out.append({
            "path": str(Path(corpus_paths[winner]).resolve()),
            "label": str(corpus_labels[winner]),
            "embedding_cosine": float(scores.max()),
            "scope": reference_scope,
        })
    return out


def build_packet(plan_path: Path, candidate_npz: Path, corpus_npz: Path,
                 out_path: Path, max_rows: int | None = None) -> dict:
    plan_header, plan_rows = load_jsonl(plan_path)
    suggestions = [row for row in plan_rows
                   if row.get("decision", {}).get("action") == "suggest"]
    if max_rows is not None:
        suggestions = suggestions[:max_rows]
    if not suggestions:
        raise ValueError("no review suggestions found in the supplied plan")

    candidate = np.load(candidate_npz, allow_pickle=True)
    candidate_paths = [str(Path(p).resolve()) for p in candidate["paths"]]
    candidate_index = {p: i for i, p in enumerate(candidate_paths)}
    missing = [row["path"] for row in suggestions if os.path.abspath(row["path"]) not in candidate_index]
    if missing:
        raise ValueError(f"candidate embedding missing {len(missing)} suggestion paths")
    candidate_indices = [candidate_index[os.path.abspath(row["path"])] for row in suggestions]

    corpus = np.load(corpus_npz, allow_pickle=True)
    corpus_paths = [str(p) for p in corpus["paths"]]
    corpus_emb = np.asarray(corpus["emb"], dtype=np.float32)
    corpus_labels = np.asarray(corpus["labels"]).astype(str)
    candidate_emb = np.asarray(candidate["emb"], dtype=np.float32)[candidate_indices]
    predicted_labels = [str(row.get("full_taxonomy_class") or row.get("predicted_class") or "")
                        for row in suggestions]
    references = nearest_references(
        [row["path"] for row in suggestions], candidate_emb,
        corpus_paths, corpus_emb, corpus_labels, predicted_labels,
    )

    definition = _load_module("audio_definition_card", "audio_definition_card.py")
    aspect = _load_module("aspect_similarity", "aspect_similarity.py")
    corpus_card_cache = {}
    cache_path = SD / "definition_cards_corpus_v3_v1.json"
    if cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        corpus_card_cache = {
            str(Path(p).resolve()): card
            for p, card in zip(cache.get("paths", []), cache.get("cards", []))
            if card is not None
        }
    rows = []
    errors = []
    for index, (row, ref) in enumerate(zip(suggestions, references)):
        try:
            card = definition.analyse_file(row["path"])
            ref_card = corpus_card_cache.get(ref["path"]) or definition.analyse_file(ref["path"])
            aspect_result = aspect.compare_cards(card, ref_card)
            rows.append({
                "path": row["path"],
                "prediction": {
                    "class": predicted_labels[index],
                    "confidence": row.get("full_taxonomy_confidence", 0.0),
                    "similarity": row.get("full_taxonomy_similarity", 0.0),
                    "filename_class": row.get("filename_class", ""),
                    "decision": row.get("decision", {}),
                },
                "definition_card": card,
                "nearest_labelled_reference": ref,
                "aspect_similarity_to_reference": aspect_result["similarity"],
                "review_safety": {
                    "review_only": True,
                    "human_approval_required": True,
                    "label_created": False,
                    "rename_applied": False,
                },
            })
        except Exception as exc:
            errors.append({"path": row["path"], "error": str(exc)})

    header = {
        "record_type": "slo_review_evidence_packet",
        "schema_version": "1.0.0",
        "source_plan": str(plan_path.resolve()),
        "source_plan_record_type": plan_header.get("record_type"),
        "n_suggestions_requested": len(suggestions),
        "n_rows": len(rows),
        "n_errors": len(errors),
        "model": "full_taxonomy_v3_plus_definition_card_v1",
        "safety": [
            "review-only; no automatic action is enabled",
            "source audio is read-only",
            "definition cards are physical evidence, not semantic ground truth",
            "nearest reference is an explanation aid, not a label transfer",
        ],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".review_evidence_", suffix=".jsonl",
                               dir=out_path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(header, sort_keys=True) + "\n")
            for row in rows:
                handle.write(json.dumps(row, sort_keys=True) + "\n")
            if errors:
                handle.write(json.dumps({"record_type": "errors", "errors": errors}) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, out_path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return header


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--candidate-embeddings", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--max-rows", type=int, default=None)
    args = parser.parse_args()
    header = build_packet(args.plan, args.candidate_embeddings, args.corpus,
                          args.out, args.max_rows)
    print(json.dumps(header, indent=2))


if __name__ == "__main__":
    main()
