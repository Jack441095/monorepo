"""Tests for KENN Dual-Inference Router."""

import pytest
from kenn.llm.dual_inference_router import (
    DualInferenceRouter,
    PATH_FAST_LOCAL_MLX,
    PATH_DEEP_FRONTIER,
)


def test_fast_path_routing_for_greetings_and_status():
    router = DualInferenceRouter()
    decision = router.route("hello")
    assert decision.path == PATH_FAST_LOCAL_MLX
    assert decision.target_latency_budget_ms <= 100

    decision_status = router.route("status")
    assert decision_status.path == PATH_FAST_LOCAL_MLX


def test_deep_frontier_routing_for_multitrack_reasoning():
    router = DualInferenceRouter()
    decision = router.route("Balance the entire multitrack session and resolve low-end clashes")
    assert decision.path == PATH_DEEP_FRONTIER
    assert decision.target_latency_budget_ms > 1000

    decision_drop = router.route("Make the drop hit harder than the breakdown with sidechain")
    assert decision_drop.path == PATH_DEEP_FRONTIER


def test_zero_audio_privacy_guard():
    router = DualInferenceRouter()
    # Prompt with null bytes simulating binary PCM waveform data
    corrupt_audio_prompt = "Here is audio data: \x00\x01\x00\x02\x00\x03"
    with pytest.raises(ValueError, match="Zero-Audio Privacy Policy"):
        router.route(corrupt_audio_prompt)
