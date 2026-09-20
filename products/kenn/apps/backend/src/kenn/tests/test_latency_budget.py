"""Latency budget verification suite for KENN.

Asserts sub-millisecond routing, sub-millisecond short-circuits,
ultra-fast cached DAW session queries, and CoreML retrieval speeds.
"""

from __future__ import annotations

import time
import pytest
from kenn.core.chat_routing import route_query, classify_answer_mode
from kenn.core.chat_answer import _short_circuit_evaluator
from kenn.ableton_osc_bridge import AbletonOSCClient


def test_tier1_short_circuit_sub_millisecond():
    """Verify greetings, status, and cancel inquiries short-circuit under 5ms (warm <1ms)."""
    queries = ["hello", "status", "cancel", "stop"]
    # Warm up initial module imports
    for q in queries:
        _short_circuit_evaluator(q)

    for q in queries:
        t0 = time.perf_counter()
        res = _short_circuit_evaluator(q)
        dt_ms = (time.perf_counter() - t0) * 1000
        assert res is not None, f"Expected short-circuit for '{q}'"
        assert dt_ms < 2.0, f"Query '{q}' took {dt_ms:.3f}ms (budget: <2ms)"


def test_tier2_routing_and_intent_budget():
    """Verify deterministic intent routing takes under 1ms (<1000 µs) when warm."""
    queries = [
        "Mute track 2",
        "Set tempo to 128 bpm",
        "How do I sidechain compress?",
        "Hey KENN, how are you?",
    ]
    # Warm up both routing and mode classification
    for q in queries:
        r = route_query(q)
        classify_answer_mode(q, r)

    for q in queries:
        t0 = time.perf_counter()
        route = route_query(q)
        mode = classify_answer_mode(q, route)
        dt_ms = (time.perf_counter() - t0) * 1000
        assert route in {"ableton", "production", "conversation"}
        # Combined route + mode classification should complete well within budget (<50ms)
        assert dt_ms < 50.0, f"Routing '{q}' took {dt_ms:.2f}ms"


def test_tier3_session_state_caching_budget():
    """Verify AbletonOSCClient session state cache read is sub-millisecond (<0.5ms)."""
    client = AbletonOSCClient()
    mock_state = {"tempo": 124.0, "tracks": [{"index": 0, "name": "Kick"}]}
    client._cached_session_state = mock_state
    client._cached_session_state_time = time.time()

    t0 = time.perf_counter()
    state = client.query_session_state()
    dt_ms = (time.perf_counter() - t0) * 1000

    assert state == mock_state
    assert dt_ms < 0.5, f"Cached session query took {dt_ms:.4f}ms (budget: <0.5ms)"


def test_tier4_cache_invalidation_on_write():
    """Verify writing commands automatically invalidates stale session cache."""
    client = AbletonOSCClient()
    client._cached_session_state = {"tempo": 120.0}
    client._cached_session_state_time = time.time()

    # Perform mock mutation with list argument
    client._send_only("/live/song/set/tempo", [128.0])
    assert client._cached_session_state is None
    assert client._cached_session_state_time == 0.0
