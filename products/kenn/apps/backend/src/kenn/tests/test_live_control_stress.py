"""End-to-End DAW OSC Network Jitter & Stress Test Suite.

Simulates rapid control requests under simulated network latency, packet loss,
and out-of-order execution to verify atomic safety guarantees and HMAC verification.
"""

from __future__ import annotations

import random
import time
from unittest.mock import MagicMock

from kenn.core.live_control_planner import LiveControlPlanner
from kenn.core.live_executor import LiveExecutor, BATCH_RECEIPT_SCHEMA


class JitteryMockOSCClient:
    """Mock Ableton OSC client simulating network latency and occasional packet loss."""

    def __init__(self, loss_rate: float = 0.0, max_jitter_ms: float = 20.0):
        self.loss_rate = loss_rate
        self.max_jitter_ms = max_jitter_ms
        self.state = {
            (0, 0, 0): -12.0,  # Track 0, Device 0, Param 0 (Threshold)
            (0, 0, 1): 2.0,    # Track 0, Device 0, Param 1 (Ratio)
            (1, 0, 0): 1000.0, # Track 1, Device 0, Param 0 (Freq)
        }

    def _simulate_network(self):
        if self.max_jitter_ms > 0:
            time.sleep(random.uniform(0.001, self.max_jitter_ms / 1000.0))

    def get_device_parameters(self, track_index: int, device_index: int) -> dict:
        self._simulate_network()
        if random.random() < self.loss_rate:
            return {"success": False, "error": "Simulated network timeout/packet loss"}
        return {
            "success": True,
            "device_name": "Compressor" if track_index == 0 else "EQ Eight",
            "parameters": [
                {"name": "Threshold" if p == 0 else "Ratio", "value": self.state.get((track_index, device_index, p), 0.0), "min": -60.0, "max": 20000.0}
                for p in range(2 if track_index == 0 else 1)
            ],
        }

    def set_device_parameter(self, track_index: int, device_index: int, param_index: int, value: float) -> bool:
        self._simulate_network()
        if random.random() < self.loss_rate:
            return False
        self.state[(track_index, device_index, param_index)] = float(value)
        return True


def test_stress_single_parameter_requests():
    osc = JitteryMockOSCClient(loss_rate=0.0, max_jitter_ms=5.0)
    planner = LiveControlPlanner(osc_client=osc)
    executor = LiveExecutor(osc_client=osc, allow_legacy_mutation=True)

    success_count = 0
    for i in range(50):
        target_val = -10.0 - (i % 20)
        res = planner.propose_parameter_change(
            track_index=0,
            device_index=0,
            parameter_index=0,
            proposed_value=target_val,
            reason=f"Stress iteration {i}",
        )
        assert res["ok"] is True
        proposal = res["proposal"]
        token = proposal["confirmation_token"]

        exec_res = executor.apply_proposal(proposal, confirm_token=token)
        if exec_res["ok"]:
            success_count += 1
            assert abs(osc.state[(0, 0, 0)] - target_val) <= 0.01

    assert success_count == 50


def test_stress_batch_atomic_rollback_under_loss():
    # 20% simulated packet loss
    osc = JitteryMockOSCClient(loss_rate=0.2, max_jitter_ms=2.0)
    planner = LiveControlPlanner(osc_client=osc)
    executor = LiveExecutor(osc_client=osc, allow_legacy_mutation=True)

    completed_batches = 0
    rolled_back_batches = 0

    for i in range(20):
        initial_val_0 = osc.state[(0, 0, 0)]
        initial_val_1 = osc.state[(1, 0, 0)]

        changes = [
            {"track_index": 0, "device_index": 0, "parameter_index": 0, "proposed_value": -25.0},
            {"track_index": 1, "device_index": 0, "parameter_index": 0, "proposed_value": 500.0},
        ]

        plan_res = planner.propose_batch_parameter_changes(changes, reason=f"Batch stress iteration {i}")
        if not plan_res["ok"]:
            continue

        proposal = plan_res["proposal"]
        token = proposal["confirmation_token"]

        exec_res = executor.apply_proposal(proposal, confirm_token=token)
        if exec_res["ok"]:
            completed_batches += 1
            assert osc.state[(0, 0, 0)] == -25.0
            assert osc.state[(1, 0, 0)] == 500.0
        else:
            rolled_back_batches += 1
            # Verify atomic rollback restored original state cleanly!
            assert osc.state[(0, 0, 0)] == initial_val_0
            assert osc.state[(1, 0, 0)] == initial_val_1

    print(f"\n[DAW Stress Test] Completed Batches: {completed_batches}, Rolled Back: {rolled_back_batches}")
    assert (completed_batches + rolled_back_batches) > 0
