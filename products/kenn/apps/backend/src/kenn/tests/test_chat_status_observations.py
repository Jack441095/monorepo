"""Chat status describes configured inference and cached Live observations without I/O."""

from types import SimpleNamespace

import pytest

from kenn import ableton_osc_bridge
from kenn.core import chat_answer, project_memory_advisory
from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_backend import ControlDeckMCPBackend
from kenn.llm import llm_rewrite, mlx_inference_engine


@pytest.fixture
def status_state(monkeypatch):
    state = SimpleNamespace(
        cfg={"enabled": True, "provider": "ollama", "model": "fixture-qwen", "api_key": ""},
        mlx_selected=False,
        mlx_available=True,
        connection={"state": "disconnected", "last_successful_heartbeat": 0.0},
        attempted_io=[],
    )
    monkeypatch.setattr(project_memory_advisory, "evaluate_memory_chat_intent", lambda *args, **kwargs: None)
    monkeypatch.setattr(llm_rewrite, "config", lambda task="rewrite": dict(state.cfg))
    monkeypatch.setattr(llm_rewrite, "mlx_selected", lambda task="rewrite": state.mlx_selected)
    monkeypatch.setattr(mlx_inference_engine, "DEFAULT_MLX_MODEL", "fixture-mlx")
    engine_class = mlx_inference_engine.MLXInferenceEngine
    monkeypatch.setattr(engine_class, "_instance", None)
    monkeypatch.setattr(engine_class, "is_available", lambda: state.mlx_available)
    monkeypatch.setattr(chat_answer.time, "monotonic", lambda: 100.0)

    def forbidden(*args, **kwargs):
        state.attempted_io.append("inference or Live I/O")
        raise AssertionError("Status must read configuration and cached observations only.")

    monkeypatch.setattr(llm_rewrite, "_get_client", forbidden)
    for name in ("get_instance", "load_model", "get_memory_stats"):
        monkeypatch.setattr(engine_class, name, forbidden)
    # Construct only the object identity: no socket, watchdog or real OSC client is started.
    osc = object.__new__(ableton_osc_bridge.AbletonOSCClient)
    monkeypatch.setattr(osc, "get_connection_status", lambda: dict(state.connection))
    for name in ("ping", "probe_connection", "_query_args", "send_command"):
        monkeypatch.setattr(osc, name, forbidden)
    monkeypatch.setattr(ableton_osc_bridge, "live_client", osc)
    state.forbidden = forbidden
    yield state
    assert state.attempted_io == []


def _status(query="status"):
    payload = chat_answer.answer_payload(query, session_id="status-fixture", allow_llm=False)
    assert payload["route"] == "conversation"
    assert payload["requires_confirmation"] is False
    assert "proposal" not in payload
    return payload["answer"]


@pytest.mark.parametrize("query", ["status", "ping", "are you connected", "model status", "connection status"])
def test_status_aliases_report_the_configured_provider_without_claiming_health(status_state, query):
    # These public chat shortcuts used to claim operational MLX even for configured Ollama.
    answer = _status(query)

    assert "ollama / fixture-qwen" in answer
    assert "Provider health and model residency have not been checked" in answer
    assert "MLX" not in answer
    assert "fully online and operational" not in answer


def test_disabled_rewrite_does_not_claim_a_resident_model_is_active(status_state, monkeypatch):
    status_state.cfg["enabled"] = False
    status_state.mlx_selected = True
    monkeypatch.setattr(mlx_inference_engine.MLXInferenceEngine, "_instance", SimpleNamespace(
        _loaded=True, _model=object(), model_id="fixture-mlx",
    ))

    answer = _status()

    assert "LLM rewrite is disabled" in answer
    assert "ollama / fixture-qwen" in answer
    assert "loaded in this process" not in answer


def test_configured_ollama_does_not_report_an_unselected_mlx_model(status_state, monkeypatch):
    monkeypatch.setattr(mlx_inference_engine.MLXInferenceEngine, "_instance", SimpleNamespace(
        _loaded=True, _model=object(), model_id="previous-mlx-model",
    ))

    answer = _status()

    assert "ollama / fixture-qwen" in answer
    assert "previous-mlx-model" not in answer
    assert "MLX" not in answer


def test_ollama_without_a_model_reports_the_missing_configuration(status_state):
    status_state.cfg["model"] = ""

    answer = _status()

    assert "ollama" in answer
    assert "no model configured" in answer
    assert "operational" not in answer


def test_provider_without_its_required_key_reports_why_rewrite_cannot_run(status_state):
    status_state.cfg["provider"] = "openai"

    answer = _status()

    assert "LLM rewrite cannot run" in answer
    assert "openai" in answer
    assert "no API key configured" in answer


@pytest.mark.parametrize("instance", [None, SimpleNamespace(_loaded=False, _model=None, model_id="fixture-mlx")])
def test_selected_mlx_does_not_claim_unloaded_weights_are_resident(status_state, monkeypatch, instance):
    status_state.mlx_selected = True
    monkeypatch.setattr(mlx_inference_engine.MLXInferenceEngine, "_instance", instance)

    answer = _status()

    assert "MLX / fixture-mlx" in answer
    assert "No MLX model is loaded in this process" in answer
    assert "Provider fallback configured: ollama / fixture-qwen" in answer


def test_selected_mlx_reports_the_loaded_model_without_claiming_inference_health(status_state, monkeypatch):
    status_state.mlx_selected = True
    monkeypatch.setattr(mlx_inference_engine.MLXInferenceEngine, "_instance", SimpleNamespace(
        _loaded=True, _model=object(), model_id="fixture-mlx",
    ))

    answer = _status()

    assert "MLX model loaded in this process: fixture-mlx" in answer
    assert "Inference health has not been checked" in answer
    assert "differs from configured model" not in answer


def test_selected_mlx_reports_a_resident_model_that_differs_from_configuration(status_state, monkeypatch):
    status_state.mlx_selected = True
    monkeypatch.setattr(mlx_inference_engine.MLXInferenceEngine, "_instance", SimpleNamespace(
        _loaded=True, _model=object(), model_id="previous-mlx-model",
    ))

    answer = _status()

    assert "MLX / fixture-mlx" in answer
    assert "MLX model loaded in this process: previous-mlx-model" in answer
    assert "Loaded MLX model differs from configured model" in answer


def test_unavailable_mlx_reports_its_provider_fallback_without_claiming_health(status_state):
    status_state.mlx_selected = True
    status_state.mlx_available = False

    answer = _status()

    assert "MLX runtime is unavailable" in answer
    assert "Provider fallback configured: ollama / fixture-qwen" in answer
    assert "health and model residency have not been checked" in answer


def test_osc_without_a_successful_reply_has_no_connection_evidence(status_state):
    status_state.connection["state"] = "connected"

    answer = _status()

    assert "AbletonOSC has no successful reply on record" in answer
    assert "Current connection has not been checked" in answer


@pytest.mark.parametrize("heartbeat, age", [(98.8, "1.2"), (40.0, "60.0")])
def test_recent_and_stale_osc_replies_remain_dated_observations(status_state, heartbeat, age):
    status_state.connection.update(state="connected", last_successful_heartbeat=heartbeat)

    answer = _status()

    assert "AbletonOSC cached state: connected" in answer
    assert f"last successful reply {age} s ago" in answer
    assert "Current connection has not been checked" in answer
    assert "fully online" not in answer


@pytest.mark.parametrize("connection_state", ["degraded", "disconnected"])
def test_cached_osc_failure_is_not_hidden_by_a_previous_success(status_state, connection_state):
    status_state.connection.update(state=connection_state, last_successful_heartbeat=80.0)

    answer = _status()

    assert f"AbletonOSC cached state: {connection_state}" in answer
    assert "last successful reply 20.0 s ago" in answer


def test_mcp_status_reads_only_its_cached_state_without_probing_or_claiming_osc(status_state, monkeypatch):
    backend = ControlDeckMCPBackend(status_state.forbidden)
    backend._connection_state = "connected"
    monkeypatch.setattr(backend, "get_connection_status", status_state.forbidden)
    monkeypatch.setattr(backend, "probe_connection", status_state.forbidden)
    monkeypatch.setattr(ableton_osc_bridge, "live_client", backend)

    answer = _status()

    assert "Live backend: ableton-control-deck-mcp; cached state: connected" in answer
    assert "Observation age is unavailable" in answer
    assert "Current connection has not been checked" in answer
    assert "AbletonOSC" not in answer


def test_fake_backend_is_named_as_a_test_fixture(status_state, monkeypatch):
    monkeypatch.setattr(ableton_osc_bridge, "live_client", object.__new__(FakeLiveBackend))

    answer = _status()

    assert "Live backend: fake (test fixture)" in answer
    assert "A real Ableton connection has not been checked" in answer
    assert "AbletonOSC" not in answer
