"""Unit tests for Multi-Parameter Batch Transactions & Atomic Rollback."""

from unittest.mock import MagicMock
from kenn.core.live_control_planner import LiveControlPlanner
from kenn.core.live_executor import LiveExecutor, BATCH_RECEIPT_SCHEMA
from kenn.plugin_actions import BATCH_SCHEMA


def build_mock_osc_client():
    mock = MagicMock()
    # Track 0, Device 0: Parameter 0 (Threshold, 0.0), Parameter 1 (Ratio, 2.0)
    # Track 1, Device 0: Parameter 0 (EQ Frequency, 1000.0)
    device_states = {
        (0, 0): {
            "success": True,
            "device_name": "Compressor",
            "parameters": [
                {"name": "Threshold", "value": -12.0, "min": -60.0, "max": 0.0},
                {"name": "Ratio", "value": 2.0, "min": 1.0, "max": 10.0},
            ],
        },
        (1, 0): {
            "success": True,
            "device_name": "EQ Eight",
            "parameters": [
                {"name": "Frequency", "value": 1000.0, "min": 20.0, "max": 20000.0},
            ],
        },
    }

    current_values = {(0, 0, 0): -12.0, (0, 0, 1): 2.0, (1, 0, 0): 1000.0}

    def get_params(t_idx, d_idx):
        if (t_idx, d_idx) not in device_states:
            return {"success": False, "error": "Device not found"}
        res = dict(device_states[(t_idx, d_idx)])
        # update dynamic parameter values
        updated_params = []
        for p_idx, p in enumerate(res["parameters"]):
            p_copy = dict(p)
            p_copy["value"] = current_values.get((t_idx, d_idx, p_idx), p["value"])
            updated_params.append(p_copy)
        res["parameters"] = updated_params
        return res

    def set_param(t_idx, d_idx, p_idx, value):
        current_values[(t_idx, d_idx, p_idx)] = float(value)
        return True

    mock.get_device_parameters.side_effect = get_params
    mock.set_device_parameter.side_effect = set_param
    return mock, current_values


def test_batch_proposal_generation():
    osc, _ = build_mock_osc_client()
    planner = LiveControlPlanner(osc_client=osc)

    changes = [
        {"track_index": 0, "device_index": 0, "parameter_index": 0, "proposed_value": -18.0, "parameter_name": "Threshold", "unit": "dB"},
        {"track_index": 1, "device_index": 0, "parameter_index": 0, "proposed_value": 300.0, "parameter_name": "Frequency", "unit": "Hz"},
    ]

    res = planner.propose_batch_parameter_changes(changes, reason="Vocals are boomy: cut EQ at 300Hz and lower compressor threshold.")
    assert res["ok"] is True
    proposal = res["proposal"]
    assert proposal["schema"] == BATCH_SCHEMA
    assert len(proposal["proposals"]) == 2
    assert "confirmation_token" in proposal


def test_batch_proposal_rejects_caller_name_that_disagrees_with_live_identity():
    osc, _ = build_mock_osc_client()
    planner = LiveControlPlanner(osc_client=osc)

    result = planner.propose_batch_parameter_changes([
        {
            "track_index": 0,
            "device_index": 0,
            "parameter_index": 1,
            "proposed_value": 4.0,
            "parameter_name": "Threshold",
        },
    ], reason="Unsafe stale parameter mapping")

    assert result["ok"] is False
    assert "does not match observed parameter 'Ratio'" in result["error"]


def test_batch_proposal_rejects_wrong_observed_device_family():
    osc, _ = build_mock_osc_client()
    planner = LiveControlPlanner(osc_client=osc)

    result = planner.propose_batch_parameter_changes([
        {
            "track_index": 0,
            "device_index": 0,
            "device_name_contains": "eq",
            "parameter_index": 0,
            "proposed_value": -18.0,
            "parameter_name": "Threshold",
        },
    ], reason="Do not bind an EQ recipe to a compressor")

    assert result["ok"] is False
    assert "does not match required device family 'eq'" in result["error"]


def test_batch_proposal_uses_explicit_live_parameter_index_when_present():
    osc = MagicMock()
    osc.get_device_parameters.return_value = {
        "success": True,
        "device_name": "Compressor",
        "parameters": [
            {"index": 9, "name": "Ratio", "value": 2.0, "min": 1.0, "max": 10.0},
            {"index": 4, "name": "Threshold", "value": -12.0, "min": -60.0, "max": 0.0},
        ],
    }
    planner = LiveControlPlanner(osc_client=osc)

    result = planner.propose_batch_parameter_changes([
        {
            "track_index": 0,
            "device_index": 0,
            "parameter_index": 4,
            "proposed_value": -18.0,
            "parameter_name": "Threshold",
        },
    ], reason="Use stable Live identity")

    assert result["ok"] is True
    assert result["proposal"]["proposals"][0]["parameter_index"] == 4
    assert result["proposal"]["proposals"][0]["parameter"] == "Threshold"


def test_batch_proposal_can_resolve_one_observed_parameter_name_to_live_index():
    osc = MagicMock()
    osc.get_device_parameters.return_value = {
        "success": True,
        "device_name": "Compressor",
        "parameters": [
            {"index": 9, "name": "Ratio", "value": 2.0, "min": 1.0, "max": 10.0},
            {"index": 4, "name": "Threshold", "value": -12.0, "min": -60.0, "max": 0.0},
        ],
    }
    planner = LiveControlPlanner(osc_client=osc)

    result = planner.propose_batch_parameter_changes([
        {
            "track_index": 0,
            "device_index": 0,
            "parameter_index": 0,
            "parameter_name": "Threshold",
            "resolve_parameter_by_name": True,
            "proposed_value": -18.0,
        },
    ], reason="Resolve the current Live parameter identity")

    assert result["ok"] is True
    assert result["proposal"]["proposals"][0]["parameter_index"] == 4


def test_batch_name_resolution_rejects_duplicate_parameter_names():
    osc = MagicMock()
    osc.get_device_parameters.return_value = {
        "success": True,
        "device_name": "Rack",
        "parameters": [
            {"index": 2, "name": "Gain", "value": 0.0, "min": -12.0, "max": 12.0},
            {"index": 7, "name": "Gain", "value": 0.0, "min": -12.0, "max": 12.0},
        ],
    }
    planner = LiveControlPlanner(osc_client=osc)

    result = planner.propose_batch_parameter_changes([
        {
            "track_index": 0,
            "device_index": 0,
            "parameter_name": "Gain",
            "resolve_parameter_by_name": True,
            "proposed_value": -2.0,
        },
    ], reason="Ambiguous parameter")

    assert result["ok"] is False
    assert "found 2" in result["error"]


def test_batch_planner_fails_closed_on_malformed_request_and_live_state():
    osc, _ = build_mock_osc_client()
    planner = LiveControlPlanner(osc_client=osc)

    malformed_request = planner.propose_batch_parameter_changes(
        [{"track_index": "not-an-index", "proposed_value": object()}],
        reason="Malformed request",
    )
    negative_index = planner.propose_batch_parameter_changes(
        [{"track_index": -1, "device_index": 0, "parameter_index": 0, "proposed_value": 0}],
        reason="Negative index",
    )
    not_an_object = planner.propose_batch_parameter_changes(["change"], reason="Wrong shape")

    assert malformed_request == {"ok": False, "error": "Batch change 1 has invalid numeric fields."}
    assert negative_index == {"ok": False, "error": "Batch change 1 has a negative Live index."}
    assert not_an_object == {"ok": False, "error": "Batch change 1 must be an object."}

    osc.get_device_parameters.return_value = None
    osc.get_device_parameters.side_effect = None
    invalid_response = planner.propose_batch_parameter_changes([
        {"track_index": 0, "device_index": 0, "parameter_index": 0, "proposed_value": 0},
    ], reason="Invalid bridge response")
    assert invalid_response["ok"] is False
    assert invalid_response["error"] == "Failed to inspect device at track 0, device 0."


def test_batch_planner_rejects_invalid_parameter_arrays_and_ranges():
    osc = MagicMock()
    planner = LiveControlPlanner(osc_client=osc)
    change = {"track_index": 0, "device_index": 0, "parameter_index": 0, "proposed_value": 0}

    osc.get_device_parameters.return_value = {
        "success": True, "device_name": "Broken", "parameters": "not-a-list",
    }
    invalid_array = planner.propose_batch_parameter_changes([change], reason="Invalid list")

    osc.get_device_parameters.return_value = {
        "success": True,
        "device_name": "Broken",
        "parameters": [{"index": 0, "name": "Gain", "value": "nan", "min": 1, "max": 0}],
    }
    invalid_range = planner.propose_batch_parameter_changes([change], reason="Invalid range")

    assert invalid_array["ok"] is False
    assert "invalid parameter list" in invalid_array["error"]
    assert invalid_range == {"ok": False, "error": "Live returned invalid numeric state for 'Gain'."}


def test_batch_proposal_execution_and_undo():
    osc, current_vals = build_mock_osc_client()
    planner = LiveControlPlanner(osc_client=osc)
    executor = LiveExecutor(osc_client=osc, allow_legacy_mutation=True)

    changes = [
        {"track_index": 0, "device_index": 0, "parameter_index": 0, "proposed_value": -18.0},
        {"track_index": 1, "device_index": 0, "parameter_index": 0, "proposed_value": 300.0},
    ]

    plan_res = planner.propose_batch_parameter_changes(changes, reason="Multi-parameter batch tweak")
    proposal = plan_res["proposal"]
    token = proposal["confirmation_token"]

    # Execute batch proposal
    exec_res = executor.apply_proposal(proposal, confirm_token=token)
    assert exec_res["ok"] is True
    receipt = exec_res["receipt"]
    assert receipt["schema"] == BATCH_RECEIPT_SCHEMA
    assert receipt["step_count"] == 2
    assert current_vals[(0, 0, 0)] == -18.0
    assert current_vals[(1, 0, 0)] == 300.0

    # Undo batch action
    undo_res = executor.undo_action(receipt["undo_payload"])
    assert undo_res["ok"] is True
    assert undo_res["undone_steps"] == 2
    assert current_vals[(0, 0, 0)] == -12.0
    assert current_vals[(1, 0, 0)] == 1000.0


def test_batch_atomic_rollback_on_step_failure():
    osc, current_vals = build_mock_osc_client()
    planner = LiveControlPlanner(osc_client=osc)
    executor = LiveExecutor(osc_client=osc, allow_legacy_mutation=True)

    changes = [
        {"track_index": 0, "device_index": 0, "parameter_index": 0, "proposed_value": -18.0},
        {"track_index": 1, "device_index": 0, "parameter_index": 0, "proposed_value": 300.0},
    ]

    plan_res = planner.propose_batch_parameter_changes(changes, reason="Test atomic rollback")
    proposal = plan_res["proposal"]
    token = proposal["confirmation_token"]

    # Make step 1 set_device_parameter fail dynamically
    def failing_set_param(t_idx, d_idx, p_idx, value):
        if t_idx == 1:  # step 1 fails!
            return False
        current_vals[(t_idx, d_idx, p_idx)] = float(value)
        return True

    osc.set_device_parameter.side_effect = failing_set_param

    exec_res = executor.apply_proposal(proposal, confirm_token=token)
    assert exec_res["ok"] is False
    assert exec_res.get("rolled_back") is True
    # Verify track 0 parameter was rolled back to initial value -12.0!
    assert current_vals[(0, 0, 0)] == -12.0
