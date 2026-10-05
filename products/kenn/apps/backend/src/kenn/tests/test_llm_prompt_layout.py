"""The model KENN is configured to use is the one that answers."""

from __future__ import annotations

from kenn.llm import llm_rewrite
from kenn.llm.llm_rewrite import answering_model, mlx_selected


def test_an_explicit_ollama_provider_is_never_replaced_by_mlx(monkeypatch) -> None:
    # Regression (26 Sept): with MLX installed, a Mac configured for Qwen3 8B on Ollama was answered by MLX's 1.5B.
    for name in ("KENN_USE_MLX", "AUDIO_TOO_LLM_PROVIDER", "KENN_LLM_PROVIDER_REWRITE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("KENN_LLM_PROVIDER", "ollama")
    assert mlx_selected() is False


def test_mlx_answers_only_when_chosen(monkeypatch) -> None:
    # Regression (5 Oct): a .env naming only the model left no provider set, so the gate baseline ran on MLX's 1.5B.
    monkeypatch.setattr(llm_rewrite, "load_env", lambda: None)
    for name in ("KENN_USE_MLX", "KENN_LLM_PROVIDER", "AUDIO_TOO_LLM_PROVIDER"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AUDIO_TOO_LLM_MODEL", "kenn-brain-qwen3-8b")
    assert mlx_selected() is False
    monkeypatch.setenv("KENN_LLM_PROVIDER", "mlx")
    assert mlx_selected() is True
    monkeypatch.setenv("KENN_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("KENN_USE_MLX", "1")
    assert mlx_selected() is True
    monkeypatch.setenv("KENN_USE_MLX", "0")
    assert mlx_selected() is False


def test_health_names_the_model_that_will_answer(monkeypatch) -> None:
    monkeypatch.setattr(llm_rewrite, "load_env", lambda: None)
    for name in ("KENN_LLM_MODEL_REWRITE", "AUDIO_TOO_LLM_MODEL_REWRITE", "KENN_LLM_PROVIDER_REWRITE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("KENN_LLM_ENABLED", "0")
    assert answering_model()["enabled"] is False
    monkeypatch.setenv("KENN_LLM_ENABLED", "1")
    monkeypatch.setenv("KENN_USE_MLX", "0")
    monkeypatch.setenv("KENN_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("KENN_LLM_MODEL", "kenn-brain-qwen3-8b")
    assert answering_model() == {"enabled": True, "provider": "ollama", "model": "kenn-brain-qwen3-8b"}
    monkeypatch.setenv("KENN_USE_MLX", "1")
    monkeypatch.setattr(llm_rewrite, "_mlx_engine_answers", lambda task="rewrite": True)
    assert answering_model()["provider"] == "mlx"


def test_mlx_chosen_but_not_installed_reports_the_fallback(monkeypatch) -> None:
    # _chat_completion falls through to the provider when mlx_lm is missing, so health must say so too.
    monkeypatch.setattr(llm_rewrite, "load_env", lambda: None)
    monkeypatch.setattr(llm_rewrite, "_mlx_engine_answers", lambda task="rewrite": False)
    monkeypatch.setenv("KENN_LLM_ENABLED", "1")
    monkeypatch.setenv("KENN_USE_MLX", "1")
    monkeypatch.setenv("KENN_LLM_PROVIDER", "ollama")
    assert answering_model()["provider"] == "ollama"

