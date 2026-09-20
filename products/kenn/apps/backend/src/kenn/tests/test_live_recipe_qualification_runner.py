"""Tests for the proposal-only and reversible real-Live recipe runner."""

from __future__ import annotations

from scripts import qualify_ableton_live_recipe as runner


def _fake_get_factory(state: dict[str, float]):
    def fake_get(_endpoint: str, path: str) -> dict:
        if path.endswith("/api/ableton/osc/session"):
            return {
                "status": "connected",
                "tracks": [{"index": 3, "name": "4-Audio", "pan": state["pan"], "devices": [{"index": 0, "name": "EQ Eight"}]}],
            }
        return {
            "success": True,
            "device_name": "EQ Eight",
            "parameters": [{"index": 7, "name": "1 Gain A", "value": state["gain"], "min": -15.0, "max": 15.0}],
        }

    return fake_get


def test_recipe_runner_defaults_to_proposal_only(monkeypatch) -> None:
    state = {"pan": 0.0, "gain": 0.0}
    posts: list[tuple[str, dict]] = []

    def fake_post(_endpoint: str, path: str, payload: dict) -> dict:
        posts.append((path, payload))
        return {
            "status": "confirmation_required",
            "changed": False,
            "proposal": {"schema": "kenn.ableton_recipe_proposal.v1", "step_count": 2, "action_id": "recipe-1", "confirmation_token": "secret"},
        }

    monkeypatch.setattr(runner, "_get", _fake_get_factory(state))
    monkeypatch.setattr(runner, "_post", fake_post)
    result = runner.qualify(
        endpoint="http://kenn",
        track_index=3,
        device_index=0,
        parameter_name="1 Gain A",
        device_value=-3.0,
        pan_value=0.1,
        session_id="proposal-only",
    )

    assert result["status"] == "proposal_only"
    assert result["proposal"] == {"schema": "kenn.ableton_recipe_proposal.v1", "step_count": 2, "changed": False}
    assert len(posts) == 1
    assert state == {"pan": 0.0, "gain": 0.0}


def test_recipe_runner_applies_replays_undoes_and_restores(monkeypatch) -> None:
    state = {"pan": 0.0, "gain": 0.0}
    calls: list[tuple[str, dict]] = []
    proposal = {"schema": "kenn.ableton_recipe_proposal.v1", "step_count": 2, "action_id": "recipe-1", "confirmation_token": "secret"}
    receipt = {
        "schema": "kenn.ableton_recipe_receipt.v1",
        "receipt_id": "receipt-1",
        "status": "applied",
        "verified": True,
        "step_count": 2,
    }
    undo = {"schema": "kenn.ableton_recipe_proposal.v1", "step_count": 2, "action_id": "recipe-undo", "confirmation_token": "undo-secret"}
    command_confirmations = 0

    def fake_post(_endpoint: str, path: str, payload: dict) -> dict:
        nonlocal command_confirmations
        calls.append((path, payload))
        if path.endswith("/api/ableton/command") and "proposal" not in payload:
            return {"status": "confirmation_required", "proposal": proposal}
        if path.endswith("/api/ableton/command"):
            command_confirmations += 1
            if command_confirmations == 1:
                state["pan"], state["gain"] = 0.1, -3.0
                return {"ok": True, "status": "applied", "receipt": receipt}
            return {"ok": False, "status": "rejected", "error": "already used"}
        if "proposal" not in payload:
            return {"ok": True, "proposal": undo}
        state["pan"], state["gain"] = 0.0, 0.0
        return {"ok": True, "status": "applied", "receipt": {**receipt, "receipt_id": "receipt-undo"}}

    monkeypatch.setattr(runner, "_get", _fake_get_factory(state))
    monkeypatch.setattr(runner, "_post", fake_post)
    result = runner.qualify(
        endpoint="http://kenn",
        track_index=3,
        device_index=0,
        parameter_name="1 Gain A",
        device_value=-3.0,
        pan_value=0.1,
        session_id="apply-test",
        apply=True,
    )

    assert result["status"] == "passed"
    assert result["replay_rejected"] is True
    assert result["write"]["verified"] is True
    assert result["undo"]["verified"] is True
    assert result["restored_readback"] == {"pan": 0.0, "device_parameter": 0.0}
    assert len(calls) == 5
