from types import SimpleNamespace

import pytest

from kenn.llm import llm_rewrite
from kenn.llm.mlx_inference_engine import MLXInferenceEngine


@pytest.fixture
def configured_rewrite(monkeypatch):
    cfg = {
        "enabled": True,
        "provider": "ollama",
        "model": "kenn-brain-qwen3-8b",
        "base_url": "http://127.0.0.1:11434/v1",
        "api_key": "",
    }
    monkeypatch.setattr(llm_rewrite, "config", lambda task="rewrite": dict(cfg))
    monkeypatch.setattr(llm_rewrite, "_mlx_engine_answers", lambda task="rewrite": False)

    def forbidden(*args, **kwargs):
        raise AssertionError("Public status must not start inference or contact the provider.")

    monkeypatch.setattr(llm_rewrite, "_get_client", forbidden)
    monkeypatch.setattr(MLXInferenceEngine, "get_instance", forbidden)
    monkeypatch.setattr(MLXInferenceEngine, "load_model", forbidden)
    return cfg


def test_enabled_ollama_without_a_model_is_not_ready(configured_rewrite):
    # Enablement previously produced ready=True despite the missing-model error.
    configured_rewrite["model"] = ""

    status = llm_rewrite.public_status()

    assert status["enabled"] is True
    assert llm_rewrite.is_enabled() is True
    assert status["ready"] is False
    assert status["model"] == ""
    assert "No LLM model configured" in status["message"]


def test_configured_ollama_can_attempt_without_a_runtime_probe(configured_rewrite, monkeypatch):
    monkeypatch.setattr(MLXInferenceEngine, "_instance", SimpleNamespace(
        _loaded=True, model_id="another-model",
    ))

    status = llm_rewrite.public_status()

    assert status["ready"] is True
    assert status["provider"] == "ollama"
    assert status["model"] == "kenn-brain-qwen3-8b"


def test_disabled_rewrite_stays_disabled_with_a_configured_model(configured_rewrite):
    configured_rewrite["enabled"] = False

    status = llm_rewrite.public_status()

    assert status["enabled"] is False
    assert status["ready"] is False
    assert status["message"].startswith("LLM rewrite off")


def test_cloud_configuration_requires_its_key(configured_rewrite):
    configured_rewrite["provider"] = "openai"

    status = llm_rewrite.public_status()

    assert status["enabled"] is True
    assert status["ready"] is False
    assert "no API key" in status["message"]


def test_compatible_provider_can_attempt_an_unnamed_model(configured_rewrite):
    configured_rewrite.update(provider="openai", model="", api_key="fixture-key")

    status = llm_rewrite.public_status()

    assert status["ready"] is True
    assert status["model"] == ""


def test_selected_available_mlx_can_attempt_without_an_ollama_model(configured_rewrite, monkeypatch):
    configured_rewrite["model"] = ""
    monkeypatch.setattr(llm_rewrite, "_mlx_engine_answers", lambda task="rewrite": True)

    status = llm_rewrite.public_status()

    assert status["ready"] is True
    assert status["provider"] == "ollama"
    assert status["model"] == ""
