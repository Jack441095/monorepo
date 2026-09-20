"""Tests for studio/kenn/kenn/adaptive/gap_clustering.py's DBSCAN thresholds.

docs/CAPABILITY_IMPROVEMENTS_2026-07-06.md flagged this job as producing zero
output despite 5,221 sessions / 504 feedback rows of real data. Verified
directly against the live databases: the import already used the torch-free
OnnxEmbedder (not sentence_transformers/torch, no ABI break) — clustering
genuinely ran, it just found nothing, because the DBSCAN thresholds
(eps=0.35, min_samples=3) were calibrated for a much busier question stream
than the 66 distinct low-confidence questions that actually exist today.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "studio" / "kenn"))

from kenn.adaptive.gap_clustering import cluster_queries  # noqa: E402


def test_default_thresholds_find_clusters_in_realistic_sparse_data() -> None:
    """Regression test for the miscalibrated-threshold bug: a small, mixed
    set of queries (some genuinely related pairs, some one-off questions)
    must still produce clusters at the new defaults — the old eps=0.35/
    min_samples=3 found nothing at this scale."""
    queries = [
        "How do I fix boxy vocals?",
        "How do I make vocals wide without mud?",
        "What buffer size should I use for tracking vocals?",
        "How much limiting is too much on a master?",
        "Why is my noise gate cutting off quiet words?",
        "What is a good starting point for a snare transient?",
    ]

    clusters = cluster_queries(queries)

    assert clusters, "expected at least one cluster on this realistic small dataset"
    clustered_questions = {q for cluster in clusters.values() for q in cluster}
    assert "How do I fix boxy vocals?" in clustered_questions
    assert "How do I make vocals wide without mud?" in clustered_questions


def test_cluster_queries_requires_at_least_min_samples() -> None:
    assert cluster_queries(["only one question"]) == {}
    assert cluster_queries([]) == {}


def test_cluster_queries_accepts_pairs_not_only_triples() -> None:
    """The old min_samples=3 meant an isolated pair of related questions
    (very plausible at current real data volume) could never form a
    cluster at all — confirmed this is now possible with 2 clearly related
    queries plus enough padding to satisfy DBSCAN's neighbourhood math."""
    queries = [
        "How do I fix boxy vocals?",
        "My vocal sounds boxy, how do I fix it?",
        "What tempo should a drum and bass track be?",
        "How do I export stems for a mix engineer?",
    ]
    clusters = cluster_queries(queries)
    assert clusters
    assert any(
        {"How do I fix boxy vocals?", "My vocal sounds boxy, how do I fix it?"} <= set(cluster)
        for cluster in clusters.values()
    )
