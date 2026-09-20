"""Pure retrieval helpers for evaluating a staged index without activation."""
from __future__ import annotations

import json
from pathlib import Path

from kenn.core.chat_retrieval import asks_for_official_reference, has_manual_subject_overlap
from kenn.core.retrieval_index_candidate import candidate_version_dir
from kenn.retrieval.retrieval import bm25_search


def load_candidate_bundle(candidate_root: Path) -> tuple[list[dict], dict]:
    """Load a candidate's validated artifacts directly, never via CURRENT elsewhere."""
    version_dir = candidate_version_dir(candidate_root)
    chunks = [
        json.loads(line)
        for line in (version_dir / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    terms = json.loads((version_dir / "terms.json").read_text(encoding="utf-8"))
    return chunks, terms


def candidate_search(
    query: str, chunks: list[dict], terms: dict, *, limit: int = 8
) -> list[tuple[float, dict]]:
    """BM25-only mirror of explicit-manual selection, isolated from live state."""
    results = bm25_search(query, chunks, terms, limit=limit)
    if not asks_for_official_reference(query):
        return results
    official = bm25_search(
        query,
        chunks,
        terms,
        limit=max(3, limit),
        allowed=lambda chunk: (
            str(chunk.get("evidence_class") or "") == "official_ableton_manual"
            and has_manual_subject_overlap(query, chunk)
        ),
    )
    seen = {str(chunk.get("id") or "") for _score, chunk in results}
    results.extend(item for item in official if str(item[1].get("id") or "") not in seen)
    return results
