import unittest


class JointDiagnosticsStrongBeatTests(unittest.TestCase):
    def test_strongbeat_tolerance_counts_near_downbeat(self):
        from scripts.joint_composition_diagnostics_fast import _is_strong_beat

        # Slightly off due to floaty durations.
        self.assertTrue(_is_strong_beat(0.0, 4.0, eps=0.06))
        self.assertTrue(_is_strong_beat(0.02, 4.0, eps=0.06))
        self.assertTrue(_is_strong_beat(3.98, 4.0, eps=0.06))  # wrap to bar end
        self.assertFalse(_is_strong_beat(0.20, 4.0, eps=0.06))

    def test_strongbeat_tolerance_counts_near_midbar(self):
        from scripts.joint_composition_diagnostics_fast import _is_strong_beat

        self.assertTrue(_is_strong_beat(2.0, 4.0, eps=0.06))
        self.assertTrue(_is_strong_beat(1.95, 4.0, eps=0.06))
        self.assertFalse(_is_strong_beat(1.7, 4.0, eps=0.06))


if __name__ == "__main__":
    unittest.main()

