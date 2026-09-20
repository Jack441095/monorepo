"""Knowledge graph cross-linking for KENN.

Builds an in-memory concept graph from note tags and section headings.
When a user asks about concept A (e.g. "Saturator"), this module can
suggest related concepts (e.g. "Glue Compressor — soft clipping",
"Utility — gain staging") to surface as cross-links in the answer.

The graph is built lazily from the loaded chunks and cached until the
index is reloaded.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _build_graph(chunks: list[dict]) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Build a bidirectional concept→source graph from chunks.

    Uses both ``tags`` and ``topics`` fields to build the graph, since topics
    are richly populated on all chunk types while tags may be sparse.

    Returns a tuple of (concept_to_sources, source_to_concepts).
    """
    concept_to_sources: dict[str, set[str]] = defaultdict(set)
    source_to_concepts: dict[str, set[str]] = defaultdict(set)

    for chunk in chunks:
        source = chunk.get("source") or ""
        concepts: set[str] = set()
        for tag in (chunk.get("tags") or []):
            norm = tag.strip().lower()
            if norm and len(norm) > 1:
                concepts.add(norm)
        for topic in (chunk.get("topics") or []):
            norm = topic.strip().lower()
            if norm and len(norm) > 1:
                concepts.add(norm)
        for concept in concepts:
            concept_to_sources[concept].add(source)
            source_to_concepts[source].add(concept)

    return dict(concept_to_sources), dict(source_to_concepts)


_lock = threading.Lock()
_graph_cache: dict | None = None
_graph_chunk_count: int = 0


def _get_graph(chunks: list[dict]) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Return the cached graph, rebuilding if the chunk count changed."""
    global _graph_cache, _graph_chunk_count
    if _graph_cache is not None and _graph_chunk_count == len(chunks):
        return _graph_cache
    with _lock:
        if _graph_cache is not None and _graph_chunk_count == len(chunks):
            return _graph_cache
        tag_to_sources, source_to_tags = _build_graph(chunks)
        _graph_cache = (tag_to_sources, source_to_tags)
        _graph_chunk_count = len(chunks)
        return _graph_cache


def related_sources(
    query_source: str,
    chunks: list[dict],
    *,
    limit: int = 5,
) -> list[dict]:
    """Find sources related to ``query_source`` via shared tags.

    Returns a list of dicts with keys ``source``, ``shared_tags``, ``score``
    (number of shared tags), sorted by score descending.
    """
    tag_to_sources, source_to_tags = _get_graph(chunks)

    query_tags = source_to_tags.get(query_source, set())
    if not query_tags:
        return []

    # Score each other source by the number of shared tags
    scores: dict[str, set[str]] = defaultdict(set)
    for tag in query_tags:
        for other_source in tag_to_sources.get(tag, set()):
            if other_source != query_source:
                scores[other_source].add(tag)

    ranked = sorted(scores.items(), key=lambda x: len(x[1]), reverse=True)
    return [
        {"source": src, "shared_tags": sorted(tags), "score": len(tags)}
        for src, tags in ranked[:limit]
    ]


def cross_links_for_results(
    results: list[tuple[float, dict]],
    chunks: list[dict],
    *,
    limit: int = 3,
) -> list[dict]:
    """Given retrieval results, find cross-linked sources not already in the results.

    Returns a list of related source suggestions the answer can reference.
    """
    if not results:
        return []

    # Collect sources already in results
    result_sources = {chunk.get("source") for _, chunk in results}

    # Find related sources for the top result
    top_source = results[0][1].get("source", "")
    if not top_source:
        return []

    related = related_sources(top_source, chunks, limit=limit + len(result_sources))

    # Filter out sources already shown
    return [r for r in related if r["source"] not in result_sources][:limit]


def reset_graph_cache() -> None:
    """Clear the cached graph (for testing or after index reload)."""
    global _graph_cache, _graph_chunk_count
    with _lock:
        _graph_cache = None
        _graph_chunk_count = 0
