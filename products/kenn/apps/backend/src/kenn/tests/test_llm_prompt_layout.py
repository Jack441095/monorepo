"""The model KENN is configured to use is the one that answers."""

from __future__ import annotations

from pathlib import Path

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
    monkeypatch.setenv("KENN_USE_MLX", "0")
    monkeypatch.setenv("KENN_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("KENN_LLM_MODEL", "kenn-brain-qwen3-8b")
    assert answering_model() == {"provider": "ollama", "model": "kenn-brain-qwen3-8b"}
    monkeypatch.setenv("KENN_USE_MLX", "1")
    assert answering_model()["provider"] == "mlx"


def test_the_shipped_launch_agent_runs_the_8b_brain_on_ollama() -> None:
    plist = (Path(__file__).resolve().parents[5] / "apps/desktop/launchd/com.shenrendao.kenn.companion.plist").read_text()
    assert "<key>KENN_USE_MLX</key>\n        <string>0</string>" in plist
    assert "<string>kenn-brain-qwen3-8b</string>" in plist
