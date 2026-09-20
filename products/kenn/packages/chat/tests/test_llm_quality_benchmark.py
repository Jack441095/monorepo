"""Local LLM Diagnostic Quality Benchmark Suite.

Evaluates KENN's system prompt synthesis, acoustic translation injection,
and retrieval grounding across core studio engineering scenarios.
"""

from __future__ import annotations

import time
from kenn.core.acoustic_translator import analyze_acoustic_descriptors
from kenn.llm.llm_rewrite import build_system_prompt, config, is_enabled


BENCHMARK_SCENARIOS = [
    {
        "id": "muddy_vocal",
        "query": "How do I fix a muddy vocal without making it thin?",
        "expected_descriptors": {"muddy", "thin"},
        "expected_freqs": ["300 Hz", "150 Hz"],
        "answer_mode": "mix_diagnosis",
        "route": "production",
    },
    {
        "id": "kick_sub_clash",
        "query": "My kick drum is boomy and clashing with the sub bass.",
        "expected_descriptors": {"boomy"},
        "expected_freqs": ["40 Hz"],
        "answer_mode": "mix_diagnosis",
        "route": "production",
    },
    {
        "id": "harsh_headphones",
        "query": "Why does my mix sound harsh and strident on headphones?",
        "expected_descriptors": {"harsh", "strident"},
        "expected_freqs": ["3500 Hz", "4000 Hz"],
        "answer_mode": "mix_diagnosis",
        "route": "production",
    },
    {
        "id": "sibilant_vocal",
        "query": "How do I fix a sibilant lead vocal in Ableton?",
        "expected_descriptors": {"sibilant"},
        "expected_freqs": ["7000 Hz"],
        "answer_mode": "ableton_steps",
        "route": "ableton",
    },
    {
        "id": "boxy_snare",
        "query": "The snare drum sounds boxy and honky.",
        "expected_descriptors": {"boxy", "honky"},
        "expected_freqs": ["600 Hz", "1200 Hz"],
        "answer_mode": "mix_diagnosis",
        "route": "production",
    },
    {
        "id": "dark_master",
        "query": "My master render sounds dark and dull compared to references.",
        "expected_descriptors": {"dark", "dull"},
        "expected_freqs": ["10000 Hz", "8000 Hz"],
        "answer_mode": "mastering_safety",
        "route": "production",
    },
    {
        "id": "parallel_comp_ableton",
        "query": "How to set up parallel compression on drums in Ableton Live?",
        "expected_descriptors": set(),
        "expected_freqs": [],
        "answer_mode": "ableton_steps",
        "route": "ableton",
    },
    {
        "id": "streaming_lufs",
        "query": "What is the best integrated LUFS target for Spotify and Apple Music?",
        "expected_descriptors": set(),
        "expected_freqs": [],
        "answer_mode": "mastering_safety",
        "route": "production",
    },
]


def test_llm_system_prompt_benchmark():
    print("\n" + "=" * 80)
    print(" KENN Local LLM Diagnostic Quality Benchmark")
    print("=" * 80)

    cfg = config("rewrite")
    print(f"Provider: {cfg['provider']} | Model: {cfg['model']} | LLM Enabled: {is_enabled('rewrite')}")
    print("-" * 80)
    print(f"{'Scenario ID':<22} | {'Acoustic Descriptors':<25} | {'DSP Guidance Injected':<22} | {'Status'}")
    print("-" * 80)

    passed = 0
    total = len(BENCHMARK_SCENARIOS)

    for sc in BENCHMARK_SCENARIOS:
        sc_id = sc["id"]
        query = sc["query"]
        expected_desc = sc["expected_descriptors"]

        recs = analyze_acoustic_descriptors(query)
        detected_desc = {r.descriptor for r in recs}

        # Build dynamic system prompt
        sys_prompt = build_system_prompt(
            answer_mode=sc["answer_mode"],
            route=sc["route"],
            query=query,
        )

        has_acoustic_guidance = "Acoustic Translation Guidance:" in sys_prompt
        expected_guidance = len(expected_desc) > 0

        guidance_ok = has_acoustic_guidance if expected_guidance else not has_acoustic_guidance
        desc_match = expected_desc == detected_desc

        is_pass = desc_match and guidance_ok
        if is_pass:
            passed += 1

        desc_str = ", ".join(sorted(detected_desc)) if detected_desc else "(none)"
        guidance_str = "YES" if has_acoustic_guidance else "NO"
        status_str = "PASS" if is_pass else "FAIL"

        print(f"{sc_id:<22} | {desc_str:<25} | {guidance_str:<22} | {status_str}")

    print("-" * 80)
    print(f"Quality Benchmark Results: {passed}/{total} SCENARIOS PASSED ({passed/total*100:.1f}%)")
    print("=" * 80)

    assert passed == total

