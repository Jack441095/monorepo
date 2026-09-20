from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT / "studio" / "kenn") not in sys.path:
    sys.path.insert(0, str(ROOT / "studio" / "kenn"))

import time

import pytest
from kenn.core.session_memory import (
    SEMANTIC_CACHE_TTL_SECONDS,
    _get_db,
    get_semantic_cache_hit,
    save_to_semantic_cache,
)

def setup_function():
    # Clear cache before each test
    conn = _get_db()
    conn.execute("DELETE FROM semantic_cache")
    conn.commit()

def teardown_function():
    # Clear cache after each test
    conn = _get_db()
    conn.execute("DELETE FROM semantic_cache")
    conn.commit()

def test_semantic_cache_exact_and_semantic_hit() -> None:
    query = "How do I reduce harshness in the high end of my mix?"
    events = [
        {"event": "metadata", "data": {"answer": "Cut 2.5kHz.", "confidence": "high", "llm_enhanced": True}},
        {"event": "token", "token": "Cut 2.5kHz."}
    ]
    
    # Verify miss initially
    assert get_semantic_cache_hit(query) is None
    
    # Save to cache
    save_to_semantic_cache(query, events)
    
    # 1. Exact query match hit
    hit = get_semantic_cache_hit(query)
    assert hit == events
    
    # Exact match case-insensitive
    hit_lower = get_semantic_cache_hit(query.lower())
    assert hit_lower == events
    
    # 2. Semantic query match hit (highly similar wording)
    similar_query = "How to reduce harshness in the high end of mix?"
    hit_similar = get_semantic_cache_hit(similar_query, threshold=0.95)
    assert hit_similar == events

    # 3. Distinct query match miss
    distinct_query = "how to warp audio clips in Ableton"
    hit_miss = get_semantic_cache_hit(distinct_query)
    assert hit_miss is None


# ── TTL / staleness ──────────────────────────────────────────────────────
#
# Live-tested 2026-08-04: this cache had no expiration at all -- a query
# tested during a bug investigation got cached (any confidence: "high"
# answer qualifies), and kept serving that exact stale answer verbatim
# after the underlying bug was fixed in code, with zero visible error or
# indication anything was cached. A TTL is the one safety net that covers
# every kind of staleness (code fixes, content edits, index rebuilds),
# not just one specific cause.

def test_expired_entry_is_not_served() -> None:
    query = "How do I tame a boxy vocal?"
    events = [
        {"event": "metadata", "data": {"answer": "Cut around 300-500 Hz.", "confidence": "high"}},
        {"event": "token", "token": "Cut around 300-500 Hz."},
    ]
    save_to_semantic_cache(query, events)
    assert get_semantic_cache_hit(query) == events

    # Simulate the entry aging past the TTL without waiting for real time.
    conn = _get_db()
    stale_created_at = int(time.time()) - SEMANTIC_CACHE_TTL_SECONDS - 1
    conn.execute(
        "UPDATE semantic_cache SET created_at = ? WHERE LOWER(query) = ?",
        (stale_created_at, query.lower()),
    )
    conn.commit()

    assert get_semantic_cache_hit(query) is None


def test_fresh_entry_within_ttl_is_still_served() -> None:
    query = "How do I tame a boxy vocal without losing presence?"
    events = [
        {"event": "metadata", "data": {"answer": "Cut around 300-500 Hz.", "confidence": "high"}},
        {"event": "token", "token": "Cut around 300-500 Hz."},
    ]
    save_to_semantic_cache(query, events)

    conn = _get_db()
    fresh_created_at = int(time.time()) - (SEMANTIC_CACHE_TTL_SECONDS - 60)
    conn.execute(
        "UPDATE semantic_cache SET created_at = ? WHERE LOWER(query) = ?",
        (fresh_created_at, query.lower()),
    )
    conn.commit()

    assert get_semantic_cache_hit(query) == events


def test_save_prunes_expired_entries() -> None:
    old_query = "How do I set up a return track?"
    conn = _get_db()
    old_created_at = int(time.time()) - SEMANTIC_CACHE_TTL_SECONDS - 100
    from kenn.retrieval.retrieval import embed_text
    import json as _json
    emb = embed_text(old_query)
    conn.execute(
        """
        INSERT OR REPLACE INTO semantic_cache (query, embedding_json, events_json, created_at, last_used_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (old_query, _json.dumps(emb.tolist()), _json.dumps([{"event": "token", "token": "x"}]), old_created_at, old_created_at),
    )
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM semantic_cache WHERE LOWER(query) = ?", (old_query.lower(),)).fetchone()[0] == 1

    save_to_semantic_cache("an unrelated fresh query", [{"event": "token", "token": "y"}])

    assert conn.execute("SELECT COUNT(*) FROM semantic_cache WHERE LOWER(query) = ?", (old_query.lower(),)).fetchone()[0] == 0
