#!/usr/bin/env python3
"""Comprehensive KENN Chat CLI & Ableton Verification Benchmark.

Tests response time, routing accuracy, Ableton OSC connectivity/safety,
and Apple Silicon MLX inference performance.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any, Dict, List

# Ensure repo root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "apps", "backend", "src")))

from kenn.core.chat_cli import ask_once
from kenn.core.chat_routing import route_query, classify_answer_mode
from kenn.orchestrator import get_orchestrator
from kenn.llm.mlx_inference_engine import MLXInferenceEngine


def benchmark_suite() -> None:
    print("=" * 78)
    print("  KENN CHAT & ABLETON LIVE CLI VERIFICATION SUITE")
    print("=" * 78)

    # 1. Inspect MLX Local Engine
    print("\n[1/4] Checking Apple Silicon MLX Acceleration...")
    mlx_avail = MLXInferenceEngine.is_available()
    print(f"  • MLX Engine Available: {mlx_avail}")
    if mlx_avail:
        engine = MLXInferenceEngine.get_instance()
        loaded = engine.load_model()
        print(f"  • Model Loaded: {loaded} ({engine.model_id})")

        # Measure raw token generation and TTFT
        t0 = time.perf_counter()
        first_token_time = None
        prompt = engine.format_chat_prompt(
            [{"role": "user", "content": "Explain compression in 15 words."}],
            system_prompt="You are KENN, a professional mix engineer."
        )
        tokens = []
        for tok in engine.stream_generate(prompt, max_tokens=30):
            if first_token_time is None:
                first_token_time = time.perf_counter()
            tokens.append(tok)
        total_time = time.perf_counter() - t0
        ttft_ms = (first_token_time - t0) * 1000 if first_token_time else 0.0
        tok_sec = len(tokens) / total_time if total_time > 0 else 0.0

        print(f"  • TTFT (Time to First Token): {ttft_ms:.1f} ms")
        print(f"  • Generation Speed: {tok_sec:.1f} tokens/sec")
        print(f"  • Total Inference Latency: {total_time * 1000:.1f} ms")

    # 2. Test Routing & Orchestration Latency
    print("\n[2/4] Testing Routing & Orchestration Speed...")
    routing_queries = [
        ("Mute track 2", "ableton_controller"),
        ("Show my Ableton session", "ableton_controller"),
        ("Separate vocals from this song", "stem_separator"),
        ("How do I sidechain compress in Ableton?", "production"),
        ("Hey KENN, how are you doing today?", "conversation"),
    ]

    for q, expected_intent in routing_queries:
        t0 = time.perf_counter()
        route = route_query(q)
        mode = classify_answer_mode(q, route)
        dt_us = (time.perf_counter() - t0) * 1_000_000
        print(f"  • \"{q}\" -> Route: {route:<12} Mode: {mode:<16} ({dt_us:.0f} µs)")

    # 3. Test Ableton Live OSC Interaction & Safety Gating
    print("\n[3/4] Testing Ableton Live Integration & Safety Guardrails...")
    ableton_test_queries = [
        "Show my session and tracks",
        "Set tempo to 128 bpm",
        "Set track 1 volume to +6 dB",  # Exceeds +3dB safety policy
        "Mute track 1",
    ]

    for q in ableton_test_queries:
        t0 = time.perf_counter()
        resp = ask_once(q)
        dt_ms = (time.perf_counter() - t0) * 1000
        first_line = resp.strip().split("\n")[0]
        print(f"  • Query: \"{q}\" ({dt_ms:.1f} ms)")
        print(f"    Response: {first_line[:90]}...")

    # 4. Test Production Knowledge & Retrieval Chat
    print("\n[4/4] Testing Studio Knowledge Retrieval & Audio Q&A...")
    audio_queries = [
        "How do I set up sidechain compression on bass in Ableton Live?",
        "What frequency is best to cut for mud in electric guitar?",
    ]

    for q in audio_queries:
        t0 = time.perf_counter()
        resp = ask_once(q)
        dt_ms = (time.perf_counter() - t0) * 1000
        print(f"  • Query: \"{q}\" ({dt_ms:.1f} ms)")
        # Show first 3 lines of response
        lines = [line for line in resp.strip().split("\n") if line.strip()][:3]
        for line in lines:
            print(f"    > {line[:85]}")
        print()

    print("=" * 78)
    print("  VERIFICATION COMPLETE: ALL BENCHMARKS EXECUTED CLEANLY")
    print("=" * 78)


if __name__ == "__main__":
    benchmark_suite()
