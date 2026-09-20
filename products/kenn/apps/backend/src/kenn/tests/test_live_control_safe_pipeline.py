"""Unit tests for KENN safe Live control pipeline (Propose -> Confirm -> Execute -> Readback -> Undo)."""

from __future__ import annotations

import unittest
import time
from pathlib import Path
from unittest.mock import MagicMock

from kenn.core.confirmation import verify_confirmation
from kenn.core.live_control_planner import LiveControlPlanner
from kenn.core.live_executor import LiveExecutor
from kenn.autonomous_agent import tool_set_ableton_parameter
from kenn.plugin_actions import SCHEMA


class TestLiveControlSafePipeline(unittest.TestCase):

    def test_planner_registry_expires_and_bounds_pending_proposals(self):
        from kenn.core import live_control_planner as planner_module

        previous = dict(planner_module._PROPOSALS_BY_TOKEN)
        try:
            planner_module._PROPOSALS_BY_TOKEN.clear()
            planner_module._store_proposal(
                "expired",
                {"id": "expired", "confirmation_meta": {"expires_at": 1}},
            )
            self.assertIsNone(LiveControlPlanner.proposal_for_token("expired"))

            future = int(time.time()) + 3600
            for index in range(planner_module.MAX_PENDING_PROPOSALS + 1):
                planner_module._store_proposal(
                    f"token-{index}",
                    {"id": f"proposal-{index}", "confirmation_meta": {"expires_at": future}},
                )

            self.assertEqual(
                len(planner_module._PROPOSALS_BY_TOKEN),
                planner_module.MAX_PENDING_PROPOSALS,
            )
            self.assertIsNone(LiveControlPlanner.proposal_for_token("token-0"))
            self.assertEqual(
                LiveControlPlanner.proposal_for_token(
                    f"token-{planner_module.MAX_PENDING_PROPOSALS}"
                )["id"],
                f"proposal-{planner_module.MAX_PENDING_PROPOSALS}",
            )
        finally:
            planner_module._PROPOSALS_BY_TOKEN.clear()
            planner_module._PROPOSALS_BY_TOKEN.update(previous)

    def test_legacy_audiogen_paths_do_not_bypass_live_safety_service(self):
        source_root = Path(__file__).resolve().parents[2]
        for relative_path in ("orchestrator.py", "core/chat_routing.py"):
            source = (source_root / "kenn" / relative_path).read_text(encoding="utf-8")
            self.assertNotIn("live_client.load_clip", source)

    def setUp(self):
        import os
        os.environ["AUDIO_TOO_ALLOW_DAW_CONTROL"] = "1"
        self.mock_osc_client = MagicMock()
        # Default device parameters for track 0, device 0
        self.mock_osc_client.get_device_parameters.return_value = {
            "success": True,
            "device_name": "Compressor",
            "parameters": [
                {"index": 0, "name": "Threshold", "value": -12.0, "min": -40.0, "max": 0.0},
                {"index": 1, "name": "Ratio", "value": 4.0, "min": 1.0, "max": 20.0},
                {"index": 2, "name": "Attack", "value": 10.0, "min": 0.1, "max": 100.0},
            ],
        }
        self.mock_osc_client.set_device_parameter.return_value = True
        self.mock_osc_client.query_session_state.return_value = {
            "status": "connected",
            "tracks": [{"index": 0, "name": "Vocal", "devices": ["Compressor"]}],
        }

    def test_planner_generates_valid_proposal_and_hmac_token(self):
        planner = LiveControlPlanner(osc_client=self.mock_osc_client)
        res = planner.propose_parameter_change(
            track_index=0,
            device_index=0,
            parameter_index=0,
            proposed_value=-14.0,
            reason="Lower vocal compressor threshold by 2 dB",
            session_id="test_session",
            unit="dB",
        )

        self.assertTrue(res.get("ok"))
        proposal = res.get("proposal", {})
        self.assertEqual(proposal.get("schema"), SCHEMA)
        self.assertEqual(proposal.get("operation"), "set_device_parameter")
        self.assertEqual(proposal.get("before"), -12.0)
        self.assertEqual(proposal.get("after"), -14.0)
        self.assertTrue(proposal.get("requires_confirmation"))

        token = proposal.get("confirmation_token")
        self.assertIsNotNone(token)
        req_text = "set_device_parameter:0:0:0:-14.0"
        self.assertTrue(verify_confirmation(token, session_id="test_session", service_id="ableton_control", text=req_text))

    def test_parse_and_propose_converts_qualified_display_units_before_raw_proposal(self):
        self.mock_osc_client.get_device_parameters.return_value = {
            "success": True,
            "device_name": "Hybrid Reverb",
            "parameters": [
                {"index": 7, "name": "Dry/Wet", "value": 0.5, "min": 0.0, "max": 1.0},
            ],
        }
        self.mock_osc_client.query_session_state.return_value = {
            "status": "connected",
            "tracks": [{"index": 0, "name": "Hi Hat", "devices": [{"name": "Hybrid Reverb"}]}],
        }
        planner = LiveControlPlanner(osc_client=self.mock_osc_client)
        result = planner.parse_and_propose(
            "set Hybrid Reverb Dry/Wet to 25% on track 1",
            session_id="display-unit-session",
        )

        self.assertTrue(result.get("ok"), result)
        proposal = result["proposal"]
        self.assertEqual(proposal["parameter_index"], 7)
        self.assertEqual(proposal["before"], 0.5)
        self.assertAlmostEqual(proposal["after"], 0.25)
        self.assertEqual(proposal["unit"], "%")

    def test_parse_and_propose_rejects_unverified_discrete_display_values(self):
        self.mock_osc_client.get_device_parameters.return_value = {
            "success": True,
            "device_name": "Glue Compressor",
            "parameters": [
                {"index": 3, "name": "Attack", "value": 3.0, "min": 0.0, "max": 6.0},
            ],
        }
        self.mock_osc_client.query_session_state.return_value = {
            "status": "connected",
            "tracks": [{"index": 0, "name": "Drums", "devices": [{"name": "Glue Compressor"}]}],
        }
        planner = LiveControlPlanner(osc_client=self.mock_osc_client)
        result = planner.parse_and_propose(
            "set Glue Compressor Attack to 2ms on track 1",
            session_id="display-unit-session",
        )

        self.assertFalse(result.get("ok"))
        self.assertIn("clarification", result.get("error", "").lower())
        self.assertIn("verified steps", " ".join(result.get("intent", {}).get("ambiguity", [])).lower())

    def test_executor_rejects_invalid_confirmation_token(self):
        planner = LiveControlPlanner(osc_client=self.mock_osc_client)
        res = planner.propose_parameter_change(
            track_index=0,
            device_index=0,
            parameter_index=0,
            proposed_value=-14.0,
            reason="Lower threshold",
            session_id="test_session",
        )
        proposal = res.get("proposal")

        executor = LiveExecutor(osc_client=self.mock_osc_client, allow_legacy_mutation=True)
        exec_res = executor.apply_proposal(proposal, confirm_token="invalid.token.str", session_id="test_session")
        self.assertFalse(exec_res.get("ok"))
        self.assertIn("Invalid, mismatched, or expired confirmation token", exec_res.get("error"))

    def test_executor_applies_proposal_and_performs_readback_verification(self):
        planner = LiveControlPlanner(osc_client=self.mock_osc_client)
        res = planner.propose_parameter_change(
            track_index=0,
            device_index=0,
            parameter_index=0,
            proposed_value=-14.0,
            reason="Lower threshold",
            session_id="test_session",
        )
        proposal = res.get("proposal")
        token = proposal.get("confirmation_token")

        # Mock post-write readback response sequences
        self.mock_osc_client.get_device_parameters.side_effect = [
            # Pre-write lookup
            {"success": True, "device_name": "Compressor", "parameters": [{"index": 0, "name": "Threshold", "value": -12.0}]},
            # Post-write readback lookup
            {"success": True, "device_name": "Compressor", "parameters": [{"index": 0, "name": "Threshold", "value": -14.0}]},
            # Undo post-write readback lookup
            {"success": True, "device_name": "Compressor", "parameters": [{"index": 0, "name": "Threshold", "value": -12.0}]},
        ]

        executor = LiveExecutor(osc_client=self.mock_osc_client, allow_legacy_mutation=True)
        exec_res = executor.apply_proposal(proposal, confirm_token=token, session_id="test_session")

        self.assertTrue(exec_res.get("ok"))
        receipt = exec_res.get("receipt", {})
        self.assertEqual(receipt.get("schema"), "kenn.execution_receipt.v1")
        self.assertTrue(receipt.get("verified"))
        self.assertEqual(receipt.get("before_value"), -12.0)
        self.assertEqual(receipt.get("requested_value"), -14.0)

        # Test Undo
        undo_payload = receipt.get("undo_payload")
        self.assertIsNotNone(undo_payload)
        undo_res = executor.undo_action(undo_payload)
        self.assertTrue(undo_res.get("ok"))
        self.assertEqual(undo_res.get("status"), "undone")


    def test_tool_set_ableton_parameter_gating_behavior(self):
        from unittest.mock import patch
        with patch("kenn.core.live_control_planner.live_client", self.mock_osc_client), \
             patch("kenn.core.live_executor.live_client", self.mock_osc_client), \
             patch("kenn.core.live_action_service.live_client", self.mock_osc_client):
            # 1. Calling without confirm token requires confirmation
            res = tool_set_ableton_parameter(0, 0, 0, -15.0)
            self.assertEqual(res.get("status"), "confirmation_required")
            self.assertTrue(res.get("confirmation_required"))
            proposal = res.get("proposal")
            self.assertIsNotNone(proposal)

            # 2. Calling with valid confirm token executes change
            token = res.get("confirm_token")
            self.assertIsNotNone(token)
            exec_res = tool_set_ableton_parameter(0, 0, 0, -15.0, confirm_token=token)
            # The mock acknowledges the write but does not update its
            # readback value. KENN must expose that as a verification failure
            # rather than falsely claiming a successful Live mutation.
            self.assertEqual(exec_res.get("status"), "failed")
            self.assertIn("read-back verification failed", exec_res.get("error", ""))



if __name__ == "__main__":
    unittest.main()
