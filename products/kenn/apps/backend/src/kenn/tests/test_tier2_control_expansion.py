"""Tests for KENN Tier-2 and Tier-3 Ableton Live control expansion.

Verifies proposals, confirmation gating (HMAC-SHA256 tokens), idempotency,
receipt schemas, and execution for:
- Clip Launch / Clip Stop
- Scene Creation
- Loop Duplication
- Clip Warp Mode & Pitch Transposition
- Clip Deletion
- Browser Preset Loading (.adv/.adg)
- Resample Bounce Automation
"""

from __future__ import annotations

import unittest
from typing import Any
from kenn.core.live_action_service import (
    LiveActionService,
    CLIP_LAUNCH_PROPOSAL_SCHEMA,
    CLIP_LAUNCH_RECEIPT_SCHEMA,
    SCENE_CREATION_PROPOSAL_SCHEMA,
    SCENE_CREATION_RECEIPT_SCHEMA,
    LOOP_DUPLICATION_PROPOSAL_SCHEMA,
    LOOP_DUPLICATION_RECEIPT_SCHEMA,
    CLIP_WARP_PITCH_PROPOSAL_SCHEMA,
    CLIP_WARP_PITCH_RECEIPT_SCHEMA,
    CLIP_DELETION_PROPOSAL_SCHEMA,
    CLIP_DELETION_RECEIPT_SCHEMA,
    PRESET_LOAD_PROPOSAL_SCHEMA,
    PRESET_LOAD_RECEIPT_SCHEMA,
    RESAMPLE_BOUNCE_PROPOSAL_SCHEMA,
    RESAMPLE_BOUNCE_RECEIPT_SCHEMA,
)


class MockLiveOSCClient:
    """Mock AbletonOSC client capturing all Tier-2/3 control calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.preset_load_result = {"success": True, "track_index": 0, "preset_name": "Punchy_Kick.adg"}
        self.create_scene_result = {"success": True, "scene_index": 2, "scene_name": "Drop 1"}
        self.create_audio_track_result = True

    def launch_clip(self, track_index: int, clip_slot_index: int) -> bool:
        self.calls.append(("launch_clip", track_index, clip_slot_index))
        return True

    def stop_clip(self, track_index: int, clip_slot_index: int) -> bool:
        self.calls.append(("stop_clip", track_index, clip_slot_index))
        return True

    def create_scene(self, name: str = "") -> dict[str, Any]:
        self.calls.append(("create_scene", name))
        return self.create_scene_result

    def duplicate_loop(self, track_index: int, clip_slot_index: int) -> bool:
        self.calls.append(("duplicate_loop", track_index, clip_slot_index))
        return True

    def set_clip_warp_mode(self, track_index: int, clip_slot_index: int, warp_mode: int) -> bool:
        self.calls.append(("set_clip_warp_mode", track_index, clip_slot_index, warp_mode))
        return True

    def set_clip_pitch_coarse(self, track_index: int, clip_slot_index: int, semitones: int) -> bool:
        self.calls.append(("set_clip_pitch_coarse", track_index, clip_slot_index, semitones))
        return True

    def delete_clip_slot(self, track_index: int, clip_slot_index: int) -> bool:
        self.calls.append(("delete_clip_slot", track_index, clip_slot_index))
        return True

    def load_browser_preset(self, track_index: int, preset_name: str) -> dict[str, Any]:
        self.calls.append(("load_browser_preset", track_index, preset_name))
        return self.preset_load_result

    def create_audio_track(self, insertion_index: int = -1) -> bool:
        self.calls.append(("create_audio_track", insertion_index))
        return self.create_audio_track_result

    def set_track_arm(self, track_index: int, armed: bool) -> bool:
        self.calls.append(("set_track_arm", track_index, armed))
        return True

    def set_track_mute(self, track_index: int, muted: bool) -> bool:
        self.calls.append(("set_track_mute", track_index, muted))
        return True

    def get_track_realtime_meters(self, track_index: int) -> dict[str, Any]:
        return {"track_index": track_index, "output_meter_left": 0.65, "output_meter_right": 0.64}


class TestTier2ControlExpansion(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_client = MockLiveOSCClient()
        self.service = LiveActionService(self.mock_client)
        self.session_id = "test-session-tier2"

    def test_clip_launch_and_stop(self) -> None:
        # 1. Propose Clip Launch
        prop_res = self.service.propose_clip_launch(track_index=0, clip_slot_index=1, session_id=self.session_id)
        self.assertTrue(prop_res["ok"])
        proposal = prop_res["proposal"]
        self.assertEqual(proposal["schema"], CLIP_LAUNCH_PROPOSAL_SCHEMA)
        self.assertEqual(proposal["action"], "launch_clip")
        self.assertIn("confirmation_token", proposal)

        # 2. Execute with invalid confirmation token -> Rejection
        bad_exec = self.service.execute(proposal, confirm_token="invalid-token", session_id=self.session_id)
        self.assertFalse(bad_exec["ok"])
        self.assertIn("Invalid or expired confirmation token", bad_exec["error"])

        # 3. Execute with valid confirmation token -> Success
        valid_exec = self.service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id=self.session_id)
        self.assertTrue(valid_exec["ok"])
        self.assertEqual(valid_exec["receipt"]["schema"], CLIP_LAUNCH_RECEIPT_SCHEMA)
        self.assertEqual(valid_exec["receipt"]["action"], "launch_clip")
        self.assertIn(("launch_clip", 0, 1), self.mock_client.calls)

        # 4. Propose Clip Stop
        stop_prop = self.service.propose_clip_launch(track_index=0, clip_slot_index=1, stop=True, session_id=self.session_id)
        self.assertTrue(stop_prop["ok"])
        self.assertEqual(stop_prop["proposal"]["action"], "stop_clip")
        stop_exec = self.service.execute(stop_prop["proposal"], confirm_token=stop_prop["proposal"]["confirmation_token"], session_id=self.session_id)
        self.assertTrue(stop_exec["ok"])
        self.assertEqual(stop_exec["receipt"]["action"], "stop_clip")
        self.assertIn(("stop_clip", 0, 1), self.mock_client.calls)

    def test_scene_creation(self) -> None:
        prop_res = self.service.propose_scene_creation(name="Breakdown", session_id=self.session_id)
        self.assertTrue(prop_res["ok"])
        proposal = prop_res["proposal"]
        self.assertEqual(proposal["schema"], SCENE_CREATION_PROPOSAL_SCHEMA)

        exec_res = self.service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id=self.session_id)
        self.assertTrue(exec_res["ok"])
        receipt = exec_res["receipt"]
        self.assertEqual(receipt["schema"], SCENE_CREATION_RECEIPT_SCHEMA)
        self.assertEqual(receipt["scene_name"], "Drop 1")
        self.assertIn(("create_scene", "Breakdown"), self.mock_client.calls)

    def test_loop_duplication(self) -> None:
        prop_res = self.service.propose_loop_duplication(track_index=1, clip_slot_index=0, session_id=self.session_id)
        self.assertTrue(prop_res["ok"])
        proposal = prop_res["proposal"]
        self.assertEqual(proposal["schema"], LOOP_DUPLICATION_PROPOSAL_SCHEMA)

        exec_res = self.service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id=self.session_id)
        self.assertTrue(exec_res["ok"])
        self.assertEqual(exec_res["receipt"]["schema"], LOOP_DUPLICATION_RECEIPT_SCHEMA)
        self.assertIn(("duplicate_loop", 1, 0), self.mock_client.calls)

    def test_clip_warp_and_pitch(self) -> None:
        prop_res = self.service.propose_clip_warp_pitch(
            track_index=2, clip_slot_index=0, warp_mode=4, pitch_coarse=-5, session_id=self.session_id
        )
        self.assertTrue(prop_res["ok"])
        proposal = prop_res["proposal"]
        self.assertEqual(proposal["schema"], CLIP_WARP_PITCH_PROPOSAL_SCHEMA)
        self.assertEqual(proposal["warp_mode"], 4)
        self.assertEqual(proposal["pitch_coarse"], -5)

        exec_res = self.service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id=self.session_id)
        self.assertTrue(exec_res["ok"])
        self.assertEqual(exec_res["receipt"]["schema"], CLIP_WARP_PITCH_RECEIPT_SCHEMA)
        self.assertIn(("set_clip_warp_mode", 2, 0, 4), self.mock_client.calls)
        self.assertIn(("set_clip_pitch_coarse", 2, 0, -5), self.mock_client.calls)

    def test_clip_deletion(self) -> None:
        prop_res = self.service.propose_clip_deletion(track_index=1, clip_slot_index=3, session_id=self.session_id)
        self.assertTrue(prop_res["ok"])
        proposal = prop_res["proposal"]
        self.assertEqual(proposal["schema"], CLIP_DELETION_PROPOSAL_SCHEMA)

        exec_res = self.service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id=self.session_id)
        self.assertTrue(exec_res["ok"])
        self.assertEqual(exec_res["receipt"]["schema"], CLIP_DELETION_RECEIPT_SCHEMA)
        self.assertIn(("delete_clip_slot", 1, 3), self.mock_client.calls)

    def test_preset_loading(self) -> None:
        prop_res = self.service.propose_load_preset(track_index=0, preset_name="Sub_Bass.adv", session_id=self.session_id)
        self.assertTrue(prop_res["ok"])
        proposal = prop_res["proposal"]
        self.assertEqual(proposal["schema"], PRESET_LOAD_PROPOSAL_SCHEMA)

        exec_res = self.service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id=self.session_id)
        self.assertTrue(exec_res["ok"])
        self.assertEqual(exec_res["receipt"]["schema"], PRESET_LOAD_RECEIPT_SCHEMA)
        self.assertIn(("load_browser_preset", 0, "Sub_Bass.adv"), self.mock_client.calls)

    def test_resample_bounce_workflow(self) -> None:
        prop_res = self.service.propose_resample_bounce(source_track_index=3, session_id=self.session_id)
        self.assertTrue(prop_res["ok"])
        proposal = prop_res["proposal"]
        self.assertEqual(proposal["schema"], RESAMPLE_BOUNCE_PROPOSAL_SCHEMA)

        exec_res = self.service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id=self.session_id)
        self.assertTrue(exec_res["ok"])
        self.assertEqual(exec_res["receipt"]["schema"], RESAMPLE_BOUNCE_RECEIPT_SCHEMA)
        self.assertIn(("create_audio_track", -1), self.mock_client.calls)
        self.assertIn(("set_track_arm", 3, False), self.mock_client.calls)
        self.assertIn(("set_track_mute", 3, True), self.mock_client.calls)

    def test_idempotency_prevents_replay(self) -> None:
        prop_res = self.service.propose_clip_launch(track_index=0, clip_slot_index=0, session_id=self.session_id)
        proposal = prop_res["proposal"]
        token = proposal["confirmation_token"]

        exec1 = self.service.execute(proposal, confirm_token=token, session_id=self.session_id)
        self.assertTrue(exec1["ok"])

        # Attempt replay with the same action_id
        exec2 = self.service.execute(proposal, confirm_token=token, session_id=self.session_id)
        self.assertFalse(exec2["ok"])


if __name__ == "__main__":
    unittest.main()
