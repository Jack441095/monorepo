"""Joint-plan Markov chorus pitch cell lock."""

from __future__ import annotations

import unittest
from types import SimpleNamespace


class JointHookCellLockTests(unittest.TestCase):
    def test_chorus_lock_snaps_outliers_to_joint_cell(self) -> None:
        from ai.markov.melody.generation.phrase_generation import _lock_chorus_pitch_cell
        from audiogen_core.config import CONFIG

        CONFIG.composition.joint_plan_markov_conditioning_enabled = True
        gen = SimpleNamespace(_joint_hook_degrees=[0, 2, 4, 2])
        phrase = [(0, 1.0), (5, 0.5), (6, 0.5), (2, 1.0), (4, 1.0)]
        plan = SimpleNamespace(section_role="chorus")

        out = _lock_chorus_pitch_cell(phrase, plan=plan, gen=gen)
        degrees = {int(d) % 7 for d, _ in out if isinstance(d, int) and int(d) >= 0}
        self.assertTrue(degrees.issubset({0, 2, 4}))
        self.assertIn(0, degrees)
        self.assertIn(4, degrees)

    def test_phrase_planner_uses_joint_hook_degrees_on_chorus_opening(self) -> None:
        from ai.markov.melody.phrase_planner import PhrasePlanner

        planner = PhrasePlanner()
        emotion = SimpleNamespace(name="grief")
        plans = planner.generate_plans(
            ["arch"],
            bars=8,
            emotion=emotion,
            section_role="chorus",
            joint_hook_degrees=[0, 2, 4, 2],
        )
        self.assertEqual(len(plans), 1)
        self.assertEqual(int(plans[0].hook_anchor_degree), 0)
        wp = list(plans[0].arc_waypoints or [])
        self.assertGreaterEqual(len(wp), 2)
        self.assertEqual(int(wp[0][1]) % 7, 0)


if __name__ == "__main__":
    unittest.main()
