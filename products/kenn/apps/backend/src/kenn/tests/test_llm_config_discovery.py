"""A fresh checkout has to find the LLM's configuration, and be told when it has no model.

Discovery (Defect 1). .env.example ships at products/kenn/.env.example, so the obvious move for an
operator is to copy it to .env right there. load_env() read apps/backend and
apps/backend/src/kenn, both of which sit under apps/ and three directories short of that, so a fresh
clone loaded nothing at all: no model, no provider, no base URL, and the whole LLM subsystem looked
absent. tooling/scripts/deploy-and-run-notes.sh writes the four AUDIO_TOO_LLM_* keys the model needs
into a .env at the product root, so that config was being written to a file nobody read.

Diagnosis (Defect 2). The model default read "gpt-4o-mini", which cannot resolve in the default
configuration: the provider default is ollama on 127.0.0.1, so an operator who had not configured a
model was told "model gpt-4o-mini not found" and sent looking for cloud access instead of setting one
variable. The default is now empty, and the request boundary says which variable is missing.
"""

from __future__ import annotations

import os

import pytest

from kenn.llm import llm_rewrite

MESSAGES = [{"role": "user", "content": "How do I de-ess?"}]

# Everything config() and is_enabled() read. Cleared per test so a developer's own .env cannot decide
# what these tests mean.
LLM_ENV_VARS = (
    "KENN_LLM_MODEL", "AUDIO_TOO_LLM_MODEL", "KENN_LLM_MODEL_REWRITE", "AUDIO_TOO_LLM_MODEL_REWRITE",
    "KENN_LLM_PROVIDER", "AUDIO_TOO_LLM_PROVIDER", "KENN_LLM_PROVIDER_REWRITE",
    "AUDIO_TOO_LLM_PROVIDER_REWRITE", "KENN_LLM_BASE_URL", "AUDIO_TOO_LLM_BASE_URL",
    "KENN_LLM_API_KEY", "AUDIO_TOO_LLM_API_KEY", "KENN_LLM_ENABLED", "AUDIO_TOO_LLM_ENABLED",
    "KENN_USE_MLX",
)


def _unconfigured(monkeypatch, **env: str) -> None:
    """Leave nothing set, so the default really is the default under test."""
    for name in LLM_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(llm_rewrite, "load_env", lambda: None)
    for name, value in env.items():
        monkeypatch.setenv(name, value)


def _refuse_the_network(*_args, **_kwargs):
    raise AssertionError("a provider was asked for a model before KENN checked one was configured")


def _fresh_checkout(tmp_path, monkeypatch) -> tuple:
    """A products/kenn tree with nothing in it but the directory names, as a new clone has it."""
    product = tmp_path / "products" / "kenn"
    (product / "apps" / "backend" / "src" / "kenn" / "llm").mkdir(parents=True)
    monkeypatch.setattr(llm_rewrite, "PRODUCT_ROOT", product)
    monkeypatch.setattr(llm_rewrite, "PROJECT_ROOT", product / "apps" / "backend")
    monkeypatch.setattr(llm_rewrite, "ROOT", product / "apps" / "backend" / "src" / "kenn")
    return product


def test_load_env_reads_the_env_written_beside_the_shipped_env_example(tmp_path, monkeypatch) -> None:
    # The whole defect in one line: the .env an operator creates from .env.example sits three directories
    # above both places the loader used to look, so nothing it says was ever applied.
    product = _fresh_checkout(tmp_path, monkeypatch)
    (product / ".env.example").write_text("AUDIO_TOO_LLM_MODEL=kenn-brain-qwen3-8b\n", encoding="utf-8")
    (product / ".env").write_text(
        "AUDIO_TOO_LLM_MODEL=kenn-brain-qwen3-8b\nKENN_LLM_ENABLED=1\n", encoding="utf-8"
    )
    monkeypatch.delenv("AUDIO_TOO_LLM_MODEL", raising=False)
    monkeypatch.delenv("KENN_LLM_ENABLED", raising=False)

    llm_rewrite.load_env()

    assert os.environ["AUDIO_TOO_LLM_MODEL"] == "kenn-brain-qwen3-8b"
    assert os.environ["KENN_LLM_ENABLED"] == "1"


def test_a_product_root_env_only_fills_in_keys_the_backend_env_leaves_out(tmp_path, monkeypatch) -> None:
    # The loop is first-wins (a key already in os.environ is left alone), so the directory added for
    # Defect 1 goes last on purpose: a developer with a working apps/backend/.env must not have it
    # shadowed by a product-root file copied from the example and left half-filled.
    product = _fresh_checkout(tmp_path, monkeypatch)
    (product / "apps" / "backend" / ".env").write_text("KENN_LLM_MODEL=kenn-brain-qwen3-8b\n", encoding="utf-8")
    (product / ".env").write_text(
        "KENN_LLM_MODEL=wrong-model\nKENN_LLM_BASE_URL=http://127.0.0.1:11434/v1\n", encoding="utf-8"
    )
    monkeypatch.delenv("KENN_LLM_MODEL", raising=False)
    monkeypatch.delenv("KENN_LLM_BASE_URL", raising=False)

    llm_rewrite.load_env()

    assert os.environ["KENN_LLM_MODEL"] == "kenn-brain-qwen3-8b"
    assert os.environ["KENN_LLM_BASE_URL"] == "http://127.0.0.1:11434/v1"


def test_the_search_path_still_points_at_the_directory_the_example_ships_in() -> None:
    # The tmp-tree tests above prove the loader reads a product-root .env. This one keeps the premise
    # honest: move .env.example and the search path is wrong again.
    assert (llm_rewrite.PRODUCT_ROOT / ".env.example").is_file()


def test_an_unconfigured_install_says_it_has_no_model_rather_than_naming_a_cloud_one(monkeypatch) -> None:
    _unconfigured(monkeypatch)
    cfg = llm_rewrite.config("rewrite")

    # Provider and base URL keep their loopback defaults. They are what made "gpt-4o-mini" impossible
    # to satisfy, so they have to be read together with the model default, not changed separately.
    assert cfg["provider"] == "ollama"
    assert cfg["base_url"] == "http://127.0.0.1:11434/v1"
    assert cfg["model"] == ""

    message = llm_rewrite.missing_model_message(cfg, "rewrite")
    assert "no llm model configured" in message.lower()
    assert "KENN_LLM_MODEL" in message
    assert "gpt-4o-mini" not in message


def test_the_request_fails_with_that_message_before_ollama_is_asked_for_anything(monkeypatch) -> None:
    _unconfigured(monkeypatch, KENN_LLM_ENABLED="1")
    monkeypatch.setattr(llm_rewrite, "mlx_selected", lambda task="rewrite": False)
    monkeypatch.setattr(llm_rewrite, "_cache_get", lambda key: None)
    monkeypatch.setattr(llm_rewrite, "_get_client", _refuse_the_network)

    with pytest.raises(RuntimeError) as caught:
        llm_rewrite._chat_completion(MESSAGES, "rewrite")

    assert "no llm model configured" in str(caught.value).lower()
    assert "gpt-4o-mini" not in str(caught.value)


def test_the_streaming_path_fails_the_same_way_before_the_first_token(monkeypatch) -> None:
    # Chat streams, so this is the path an operator actually hits: the raise reaches
    # enhance_stream's handler, which prints it and hands the producer the template answer.
    _unconfigured(monkeypatch, KENN_LLM_ENABLED="1")
    monkeypatch.setattr(llm_rewrite, "mlx_selected", lambda task="rewrite": False)
    monkeypatch.setattr(llm_rewrite, "_cache_get", lambda key: None)
    monkeypatch.setattr(llm_rewrite, "_get_client", _refuse_the_network)

    stream = llm_rewrite.chat_completion_stream(MESSAGES, "rewrite")
    with pytest.raises(RuntimeError) as caught:
        next(stream)

    assert "no llm model configured" in str(caught.value).lower()


def test_query_routing_falls_through_to_keywords_and_says_why(monkeypatch, capsys) -> None:
    # Routing has always degraded to its keyword matcher on any LLM failure rather than raising, so it
    # reports this one the same way instead of making chat_routing guard against a misconfigured model.
    _unconfigured(monkeypatch, KENN_LLM_ENABLED="1")
    monkeypatch.setattr(llm_rewrite, "_get_client", _refuse_the_network)

    assert llm_rewrite.llm_route_query("how do I set up an aux bus") is None

    printed = capsys.readouterr().out
    assert "no llm model configured" in printed.lower()
    assert "keyword routing" in printed


def test_the_status_line_names_the_missing_variable_instead_of_printing_an_empty_model(monkeypatch) -> None:
    # This is the line chat_cli prints at startup, so it is where a producer meets the problem.
    _unconfigured(monkeypatch, KENN_LLM_ENABLED="1")

    message = llm_rewrite.status_message()

    assert "no llm model configured" in message.lower()
    assert "KENN_LLM_MODEL" in message
    assert "gpt-4o-mini" not in message


def test_a_cloud_provider_is_still_unreachable_without_its_own_api_key(monkeypatch) -> None:
    # The safety-relevant half of defaulting the model to "". An empty name must never be what makes a
    # request look allowed: is_enabled() asks for the key and nothing else, on any provider.
    _unconfigured(monkeypatch, KENN_LLM_ENABLED="1", KENN_LLM_PROVIDER="openai")

    assert llm_rewrite.is_enabled("rewrite") is False
    # Not a cloud error either. An OpenAI-compatible server may ignore the model field or serve it under
    # an alias, so an unnamed model is left to the provider rather than turned into a hard failure.
    assert llm_rewrite.missing_model_message(llm_rewrite.config("rewrite")) == ""

    monkeypatch.setenv("KENN_LLM_API_KEY", "sk-not-a-real-key")
    assert llm_rewrite.is_enabled("rewrite") is True


def test_a_configured_local_model_reports_nothing_missing(monkeypatch) -> None:
    _unconfigured(monkeypatch, KENN_LLM_ENABLED="1", KENN_LLM_MODEL="kenn-brain-qwen3-8b")
    cfg = llm_rewrite.config("rewrite")

    assert llm_rewrite.missing_model_message(cfg, "rewrite") == ""
    assert llm_rewrite.status_message().startswith("LLM rewrite on — kenn-brain-qwen3-8b")
