"""Tests for KENN plug-in parameter bridging and synchronization APIs."""

import pytest
from kenn.plugin_handoff import (
    get_plugin_parameters,
    set_plugin_parameter,
    set_plugin_parameters,
    pop_pending_parameter_updates,
)


def test_get_plugin_parameters_defaults():
    session_id = "test-session-params-1"
    params = get_plugin_parameters(session_id)
    assert params["ok"] is True
    assert params["session_id"] == session_id
    assert params["parameters"]["target_lufs"] == -14.0
    assert params["parameters"]["assistant_mode"] == "suggest"
    assert params["parameters"]["analysis_enabled"] is True
    assert params["parameters"]["live_context_enabled"] is True
    assert params["pending_updates"] == {}


def test_set_and_pop_plugin_parameters():
    session_id = "test-session-params-2"
    # Set target_lufs
    res = set_plugin_parameter(session_id, "target_lufs", -12.5)
    assert res["ok"] is True
    assert res["value"] == -12.5

    # Set assistant_mode
    res_mode = set_plugin_parameter(session_id, "assistant_mode", "assist")
    assert res_mode["ok"] is True
    assert res_mode["value"] == "assist"

    # Check pending
    params = get_plugin_parameters(session_id)
    assert params["pending_updates"]["target_lufs"] == -12.5
    assert params["pending_updates"]["assistant_mode"] == "assist"

    # Pop pending
    popped = pop_pending_parameter_updates(session_id)
    assert popped["ok"] is True
    assert popped["pending_updates"]["target_lufs"] == -12.5
    assert popped["pending_updates"]["assistant_mode"] == "assist"

    # Verify pending cleared
    params_after = get_plugin_parameters(session_id)
    assert params_after["pending_updates"] == {}


def test_parameter_bounds_and_validation():
    session_id = "test-session-params-3"
    # Target LUFS too low
    low = set_plugin_parameter(session_id, "target_lufs", -26.0)
    assert low["ok"] is False
    assert "between -24.0 and -6.0" in low["error"]

    # Target LUFS too high
    high = set_plugin_parameter(session_id, "target_lufs", -4.0)
    assert high["ok"] is False
    assert "between -24.0 and -6.0" in high["error"]

    # Invalid assistant mode
    invalid_mode = set_plugin_parameter(session_id, "assistant_mode", "god_mode")
    assert invalid_mode["ok"] is False
    assert "assistant_mode must be one of" in invalid_mode["error"]

    # Unsupported parameter
    unsupported = set_plugin_parameter(session_id, "reverb_decay", 2.5)
    assert unsupported["ok"] is False
    assert "Unsupported plug-in parameter" in unsupported["error"]


def test_batch_set_plugin_parameters():
    session_id = "test-session-params-4"
    batch = {
        "target_lufs": -16.0,
        "assistant_mode": "auto",
        "live_context_enabled": True,
    }
    res = set_plugin_parameters(session_id, batch)
    assert res["ok"] is True
    assert res["parameters"]["target_lufs"] == -16.0
    assert res["parameters"]["assistant_mode"] == "auto"

    popped = pop_pending_parameter_updates(session_id)
    assert popped["pending_updates"]["target_lufs"] == -16.0
    assert popped["pending_updates"]["assistant_mode"] == "auto"
