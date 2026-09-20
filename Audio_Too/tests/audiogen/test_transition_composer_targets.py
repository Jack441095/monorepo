import unittest


class TransitionComposerTargetTests(unittest.TestCase):
    def test_verse_to_prechorus_builds_end_tension(self):
        from composition.section_planner import _make_timeline_targets

        curve = {
            "melody_density_mult": 1.0,
            "chord_rhythm_mult": 1.0,
            "motif_prob_mult": 1.0,
        }
        plain = _make_timeline_targets("a", 8, dict(curve))
        built = _make_timeline_targets("a", 8, dict(curve), next_role="pre_chorus")

        self.assertGreaterEqual(float(built["tension"][-1]), float(plain["tension"][-1]))
        self.assertGreaterEqual(float(built["motif_strength"][-1]), float(plain["motif_strength"][-1]))

    def test_prechorus_to_chorus_opens_final_landing_and_adds_breath(self):
        from composition.section_planner import _make_timeline_targets

        curve = {
            "melody_density_mult": 1.0,
            "chord_rhythm_mult": 1.0,
            "motif_prob_mult": 1.0,
        }
        plain = _make_timeline_targets("pre_chorus", 8, dict(curve))
        led = _make_timeline_targets("pre_chorus", 8, dict(curve), next_role="b")

        self.assertLessEqual(float(led["cadence_window"][-1]), float(plain["cadence_window"][-1]))
        self.assertGreaterEqual(float(led["breath_window"][-2]), float(plain["breath_window"][-2]))
        self.assertGreaterEqual(float(led["tension"][-1]), float(plain["tension"][-1]))

    def test_chorus_to_verse_releases_final_bar(self):
        from composition.section_planner import _make_timeline_targets

        curve = {
            "melody_density_mult": 1.0,
            "chord_rhythm_mult": 1.0,
            "motif_prob_mult": 1.0,
        }
        plain = _make_timeline_targets("b", 8, dict(curve))
        released = _make_timeline_targets("b", 8, dict(curve), next_role="a")

        self.assertLessEqual(float(released["tension"][-1]), float(plain["tension"][-1]))
        self.assertLessEqual(float(released["melody_density"][-1]), float(plain["melody_density"][-1]))
        self.assertGreaterEqual(float(released["breath_window"][-1]), float(plain["breath_window"][-1]))


if __name__ == "__main__":
    unittest.main()
