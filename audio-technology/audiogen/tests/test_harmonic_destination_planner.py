import unittest


class HarmonicDestinationPlannerTests(unittest.TestCase):
    def test_prechorus_to_chorus_targets_open_dominant_arrival(self):
        from composition.engine import CompositionGenerator

        gen = CompositionGenerator(enable_perf_monitoring=False)
        dest = gen.chord_planner.section_harmonic_destination(
            section_role="pre_chorus",
            next_role="b",
            is_last_section=False,
        )
        self.assertEqual(int(dest["target_degree"]), 4)
        self.assertEqual(str(dest["arrival_type"]), "open")
        self.assertLess(float(dest["cadence_bias_mult"]), 1.0)

    def test_final_chorus_targets_closed_arrival(self):
        from composition.engine import CompositionGenerator

        gen = CompositionGenerator(enable_perf_monitoring=False)
        dest = gen.chord_planner.section_harmonic_destination(
            section_role="b",
            next_role="outro",
            is_last_section=True,
        )
        self.assertEqual(int(dest["target_degree"]), 0)
        self.assertEqual(str(dest["arrival_type"]), "closed")
        self.assertGreater(float(dest["cadence_bias_mult"]), 1.0)


if __name__ == "__main__":
    unittest.main()
