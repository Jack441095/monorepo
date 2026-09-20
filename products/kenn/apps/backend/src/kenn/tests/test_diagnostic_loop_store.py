from __future__ import annotations

from copy import deepcopy

from kenn.core.diagnostic_loop import record_diagnostic_result, start_diagnostic_loop
from kenn.core.diagnostic_loop_store import DiagnosticLoopStore
from kenn.core.session_context import build_session_context


def _context() -> dict:
    return build_session_context(
        session_id="diagnostic-session",
        snapshot={
            "status": "connected",
            "tracks": [{"index": 0, "name": "Bass", "type": "audio", "devices": []}],
        },
    )


def _loop() -> dict:
    return start_diagnostic_loop(
        goal="The mix gets muddy in the busiest section.",
        context=_context(),
    )["loop"]


def _result(loop: dict) -> dict:
    return {
        "schema": "kenn.diagnostic_test_result.v1",
        "hypothesis_id": loop["active_hypothesis_id"],
        "verdict": "contradicts",
        "source": "user_observation",
        "observation": "Muting that part did not clear the low mids.",
        "source_turn_id": "turn-2",
    }


def test_diagnostic_loop_survives_store_restart(tmp_path) -> None:
    path = tmp_path / "diagnostics.db"
    loop = _loop()

    started = DiagnosticLoopStore(path).start(loop)
    loaded = DiagnosticLoopStore(path).load(loop["loop_id"])

    assert started["ok"] is True
    assert loaded == loop


def test_diagnostic_loop_update_is_compare_and_swap(tmp_path) -> None:
    store = DiagnosticLoopStore(tmp_path / "diagnostics.db")
    loop = _loop()
    store.start(loop)
    updated = record_diagnostic_result(loop, _result(loop))["loop"]

    first = store.update(expected=loop, updated=updated)
    replay = store.update(expected=loop, updated=updated)

    assert first["ok"] is True
    assert replay["ok"] is False
    assert "concurrently" in replay["errors"][0]
    assert store.load(loop["loop_id"]) == updated


def test_diagnostic_loop_identity_cannot_change(tmp_path) -> None:
    store = DiagnosticLoopStore(tmp_path / "diagnostics.db")
    loop = _loop()
    store.start(loop)
    altered = deepcopy(loop)
    altered["loop_id"] = "diagnostic-forged"

    result = store.update(expected=loop, updated=altered)

    assert result["ok"] is False
    assert "identity cannot change" in result["errors"][0]
