"""Unit tests and benchmarks for KENN Apple Silicon MLX Inference Engine."""

import pytest
from kenn.llm.mlx_inference_engine import MLXInferenceEngine


def _require_mlx_model():
    """Skip hardware/model tests when optional MLX runtime assets are absent."""
    if not MLXInferenceEngine.is_available():
        pytest.skip("MLX/MLX-LM is not installed in this environment")
    engine = MLXInferenceEngine.get_instance()
    if not engine.load_model():
        pytest.skip("KENN_MLX_MODEL is not available locally")
    return engine


def test_mlx_is_available_on_apple_silicon():
    """Verify MLX availability detection."""
    if not MLXInferenceEngine.is_available():
        pytest.skip("MLX/MLX-LM is not installed in this environment")


def test_format_chat_prompt():
    """Verify ChatML prompt formatting."""
    engine = MLXInferenceEngine()
    messages = [
        {"role": "user", "content": "How do I fix muddy low-mids?"},
    ]
    prompt = engine.format_chat_prompt(messages, system_prompt="You are KENN.")
    assert "<|im_start|>system\nYou are KENN.<|im_end|>\n" in prompt
    assert "<|im_start|>user\nHow do I fix muddy low-mids?<|im_end|>\n" in prompt
    assert prompt.endswith("<|im_start|>assistant\n")


def test_mlx_inference_latency_and_output():
    """Verify local MLX model loads and generates completion with metrics."""
    engine = _require_mlx_model()

    prompt = engine.format_chat_prompt(
        [{"role": "user", "content": "Explain high pass filter in one sentence."}],
        system_prompt="You are an audio engineering assistant.",
    )

    result = engine.generate(prompt, max_tokens=40, temperature=0.1)
    assert result["engine"] == "apple_silicon_mlx"
    assert len(result["text"]) > 10
    assert result["latency_ms"] > 0
    # Latency should be fast on warm model
    assert result["tokens_per_second"] > 5.0


def test_mlx_stream_generation():
    """Verify streaming tokens are yielded incrementally."""
    engine = _require_mlx_model()
    prompt = engine.format_chat_prompt(
        [{"role": "user", "content": "Count from 1 to 5."}],
    )

    chunks = list(engine.stream_generate(prompt, max_tokens=25, temperature=0.1))
    assert len(chunks) > 1
    combined = "".join(chunks)
    assert len(combined.strip()) > 0


def test_mlx_prewarm_and_memory_stats():
    """Verify prewarm triggers cleanly and memory stats return Metal allocations."""
    engine = _require_mlx_model()
    success = engine.prewarm(blocking=True)
    assert success is True

    stats = engine.get_memory_stats()
    assert stats["available"] is True
    assert stats["model_loaded"] is True
    assert stats["prewarmed"] is True
    assert "active_mb" in stats
    assert "peak_mb" in stats


def test_mlx_prompt_cache_generation():
    """Verify prompt cache creation and reuse in generation."""
    engine = _require_mlx_model()
    cache = engine.create_prompt_cache()
    assert cache is not None
    assert len(cache) > 0

    prompt = engine.format_chat_prompt(
        [{"role": "user", "content": "What is 2 + 2?"}],
        system_prompt="You are a studio engineer assistant.",
    )
    res = engine.generate(prompt, max_tokens=15, prompt_cache=cache)
    assert len(res["text"]) > 0
    assert res["engine"] == "apple_silicon_mlx"
