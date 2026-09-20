import unittest


class TimelineCadenceRoleTests(unittest.TestCase):
    def test_prechorus_and_chorus_endings_are_stronger_than_verse(self):
        from composition.section_planner import _make_timeline_targets

        curve = {
            "melody_density_mult": 1.0,
            "chord_rhythm_mult": 1.0,
            "motif_prob_mult": 1.0,
        }
        verse = _make_timeline_targets("a", 8, dict(curve))
        pre = _make_timeline_targets("pre_chorus", 8, dict(curve))
        chorus = _make_timeline_targets("b", 8, dict(curve))

        self.assertLess(float(verse["cadence_window"][-1]), float(pre["cadence_window"][-1]))
        self.assertLess(float(verse["cadence_window"][-1]), float(chorus["cadence_window"][-1]))
        self.assertLess(float(verse["cadence_window"][-2]), float(pre["cadence_window"][-2]))

    def test_prechorus_gets_more_breath_before_final_landing_than_verse(self):
        from composition.section_planner import _make_timeline_targets

        curve = {
            "melody_density_mult": 1.0,
            "chord_rhythm_mult": 1.0,
            "motif_prob_mult": 1.0,
        }
        verse = _make_timeline_targets("a", 8, dict(curve))
        pre = _make_timeline_targets("pre_chorus", 8, dict(curve))
        outro = _make_timeline_targets("outro", 8, dict(curve))

        self.assertLess(float(verse["breath_window"][-2]), float(pre["breath_window"][-2]))
        self.assertLess(float(pre["breath_window"][-2]), float(outro["breath_window"][-2]))


if __name__ == "__main__":
    unittest.main()
