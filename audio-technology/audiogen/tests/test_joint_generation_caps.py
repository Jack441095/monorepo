import unittest


class JointGenerationCapsTests(unittest.TestCase):
    def test_joint_generation_does_not_persist_overrides(self):
        from audiogen_core.config import CONFIG
        from composition.engine import CompositionGenerator
        from data.music_data import EMOTIONS

        gen = CompositionGenerator(enable_perf_monitoring=False)
        emotion = EMOTIONS[0]

        # Force section picker to run (k>1), but keep the budget tiny.
        old_k = getattr(CONFIG.composition, "section_k_samples", 1)
        old_budget = getattr(CONFIG.composition, "section_pick_time_budget_s", 0.35)

        # Values that the joint loop might temporarily override.
        old_mask = getattr(CONFIG.composition, "masking_constraints_strength", 0.70)
        old_gl = getattr(CONFIG.composition, "arp_melody_groove_link_strength", 0.0)
        old_fd = getattr(CONFIG.composition, "arp_density_follow_melody", 0.0)
        old_sep = getattr(CONFIG.composition, "arp_melody_register_separation_semitones", 5)

        old_joint = getattr(CONFIG.composition, "joint_generation_enabled", False)
        old_joint_max = getattr(CONFIG.composition, "joint_generation_max_iters", 3)
        old_joint_ms = getattr(CONFIG.composition, "joint_generation_budget_ms", 120.0)
        old_wall = getattr(CONFIG.composition, "section_pick_use_wall_clock", False)
        old_joint_wall = getattr(CONFIG.composition, "joint_generation_use_wall_clock", False)

        try:
            CONFIG.composition.section_k_samples = 2
            CONFIG.composition.section_pick_time_budget_s = 0.10
            CONFIG.composition.section_pick_use_wall_clock = True
            CONFIG.composition.joint_generation_enabled = True
            CONFIG.composition.joint_generation_max_iters = 3
            CONFIG.composition.joint_generation_budget_ms = 15.0
            CONFIG.composition.joint_generation_use_wall_clock = True

            evs = gen.section_planner.build_section(
                emotion=emotion,
                root_note=60,
                bars=4,
                key_changes=None,
                temperature=1.0,
                target_notes_per_bar=8.0,
                melody_style="auto",
                humanization_scale=0.0,
                chord_progression=None,
                melody_styles=None,
                section_index=0,
            )
            self.assertIsInstance(evs, list)
            self.assertTrue(evs)
        finally:
            CONFIG.composition.section_k_samples = old_k
            CONFIG.composition.section_pick_time_budget_s = old_budget

            CONFIG.composition.joint_generation_enabled = old_joint
            CONFIG.composition.joint_generation_max_iters = old_joint_max
            CONFIG.composition.joint_generation_budget_ms = old_joint_ms
            CONFIG.composition.section_pick_use_wall_clock = old_wall
            CONFIG.composition.joint_generation_use_wall_clock = old_joint_wall

            # Assert we didn't persist any temporary overrides.
            self.assertEqual(getattr(CONFIG.composition, "masking_constraints_strength", None), old_mask)
            self.assertEqual(getattr(CONFIG.composition, "arp_melody_groove_link_strength", None), old_gl)
            self.assertEqual(getattr(CONFIG.composition, "arp_density_follow_melody", None), old_fd)
            self.assertEqual(getattr(CONFIG.composition, "arp_melody_register_separation_semitones", None), old_sep)


if __name__ == "__main__":
    unittest.main()

