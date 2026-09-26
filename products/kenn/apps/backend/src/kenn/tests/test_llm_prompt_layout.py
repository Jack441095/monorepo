"""The model KENN is configured to use is the one that answers."""

from __future__ import annotations

from kenn.llm.llm_rewrite import mlx_selected


def test_an_explicit_ollama_provider_is_never_replaced_by_mlx(monkeypatch) -> None:
    # Regression (26 Sept): with MLX installed, a Mac configured for Qwen3 8B on Ollama was answered by MLX's 1.5B.
    for name in ("KENN_USE_MLX", "AUDIO_TOO_LLM_PROVIDER", "KENN_LLM_PROVIDER_REWRITE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("KENN_LLM_PROVIDER", "ollama")
    assert mlx_selected() is False


def test_mlx_answers_when_chosen_or_when_nothing_is_configured(monkeypatch) -> None:
    for name in ("KENN_USE_MLX", "KENN_LLM_PROVIDER", "AUDIO_TOO_LLM_PROVIDER"):
        monkeypatch.delenv(name, raising=False)
    assert mlx_selected() is True
    monkeypatch.setenv("KENN_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("KENN_USE_MLX", "1")
    assert mlx_selected() is True
    monkeypatch.setenv("KENN_USE_MLX", "0")
    assert mlx_selected() is False
