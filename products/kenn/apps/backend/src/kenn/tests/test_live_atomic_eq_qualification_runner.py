"""Tests for the proposal-only and reversible atomic EQ qualification runner."""

from __future__ import annotations

import json

from scripts import qualify_ableton_live_atomic_eq as runner


def _session(state: dict) -> dict:
    return {
        "status": "connected",
        "tracks": [{
            "index": 5,
            "name": "Synth",
            "devices": [
                {"index": index, "name": name}
                for index, name in enumerate(state["devices"])
            ],
        }],
    }


def _proposal() -> dict:
    return {
        "schema": "kenn.ableton_device_setup_proposal.v1",
        "action_id": "eq-setup-1",
        "confirmation_token": "must-not-be-printed",
        "operation": "insert_eq_band_tuning_gain",
        "track_index": 5,
        "track_name": "Synth",
        "insertion_index": 0,
        "eq_band": "2A",
        "parameter_specs": [
            {"role": "enable", "name": "2 Filter On A", "display_value": 1.0, "unit": "boolean"},
            {"role": "frequency", "name": "2 Frequency A", "display_value": 5000.0, "unit": "Hz"},
            {"role": "gain", "name": "2 Gain A", "display_value": 3.0, "unit": "dB"},
        ],
    }


def test_atomic_eq_runner_defaults_to_proposal_only_and_preserves_chain(monkeypatch) -> None:
    state = {"devices": []}
    posts: list[tuple[str, dict]] = []

    def fake_get(_endpoint: str, _path: str) -> dict:
        return _session(state)

    def fake_post(_endpoint: str, path: str, payload: dict) -> dict:
        posts.append((path, payload))
        return {"status": "confirmation_required", "changed": False, "proposal": _proposal()}

    monkeypatch.setattr(runner, "_get", fake_get)
    monkeypatch.setattr(runner, "_post", fake_post)
    result = runner.qualify(
        endpoint="http://kenn",
        track_index=5,
        eq_band="2A",
        frequency_hz=5000.0,
        gain_db=3.0,
        session_id="proposal-only",
    )

    assert result["status"] == "proposal_only"
    assert result["proposal_preserved_device_chain"] is True
    assert result["proposal"]["parameter_names"] == ["2 Filter On A", "2 Frequency A", "2 Gain A"]
    assert len(posts) == 1
    assert "must-not-be-printed" not in json.dumps(result)
    assert state["devices"] == []


def test_atomic_eq_runner_applies_rejects_replay_undoes_and_restores(monkeypatch) -> None:
    state = {"devices": []}
    calls: list[tuple[str, dict]] = []
    proposal = _proposal()
    receipt = {
        "schema": "kenn.ableton_action_receipt.v1",
        "receipt_id": "receipt-eq-setup",
        "status": "applied",
        "verified": True,
        "operation": "insert_eq_band_tuning_gain",
        "parameter_results": [
            {"parameter_index": 14, "parameter_name": "2 Filter On A", "requested": 1.0, "readback": 1.0, "verified": True},
            {"parameter_index": 16, "parameter_name": "2 Frequency A", "requested": 0.807, "readback": 0.807, "verified": True},
            {"parameter_index": 17, "parameter_name": "2 Gain A", "requested": 3.0, "readback": 3.0, "verified": True},
        ],
    }
    undo = {"action_id": "undo-1", "confirmation_token": "undo-secret"}
    confirmations = 0

    def fake_get(_endpoint: str, _path: str) -> dict:
        return _session(state)

    def fake_post(_endpoint: str, path: str, payload: dict) -> dict:
        nonlocal confirmations
        calls.append((path, payload))
        if path.endswith("/api/ableton/command") and "proposal" not in payload:
            return {"status": "confirmation_required", "changed": False, "proposal": proposal}
        if path.endswith("/api/ableton/command"):
            confirmations += 1
            if confirmations == 1:
                state["devices"] = ["EQ Eight"]
                return {"ok": True, "status": "applied", "receipt": receipt}
            return {"ok": False, "status": "rejected", "error": "already used"}
        if "proposal" not in payload:
            return {"ok": True, "proposal": undo}
        state["devices"] = []
        return {
            "ok": True,
            "status": "applied",
            "receipt": {"schema": "kenn.ableton_action_receipt.v1", "receipt_id": "undo-receipt", "verified": True},
        }

    monkeypatch.setattr(runner, "_get", fake_get)
    monkeypatch.setattr(runner, "_post", fake_post)
    result = runner.qualify(
        endpoint="http://kenn",
        track_index=5,
        eq_band="2A",
        frequency_hz=5000.0,
        gain_db=3.0,
        session_id="apply",
        apply=True,
    )

    assert result["status"] == "passed"
    assert result["write"]["verified"] is True
    assert len(result["write"]["parameter_results"]) == 3
    assert result["replay_rejected"] is True
    assert result["undo"]["verified"] is True
    assert result["restored_readback"] == {"devices": []}
    assert "must-not-be-printed" not in json.dumps(result)
    assert "undo-secret" not in json.dumps(result)
    assert state["devices"] == []
    assert len(calls) == 5


def test_atomic_eq_runner_refuses_existing_eq_without_posting(monkeypatch) -> None:
    state = {"devices": ["EQ Eight"]}
    posts: list[dict] = []

    monkeypatch.setattr(runner, "_get", lambda _endpoint, _path: _session(state))
    monkeypatch.setattr(runner, "_post", lambda _endpoint, _path, payload: posts.append(payload) or {})
    result = runner.qualify(
        endpoint="http://kenn",
        track_index=5,
        eq_band="2A",
        frequency_hz=5000.0,
        gain_db=3.0,
        session_id="blocked-existing",
        apply=True,
    )

    assert result["status"] == "blocked"
    assert "already contains EQ Eight" in result["error"]
    assert posts == []
