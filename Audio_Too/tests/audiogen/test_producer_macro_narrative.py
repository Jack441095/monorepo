import unittest


class ProducerMacroNarrativeTests(unittest.TestCase):
    def test_narrative_macro_enables_song_level_upgrades(self) -> None:
        from audiogen_core.config import ConfigurationManager

        cfg = ConfigurationManager()
        cfg.set_producer_macro("narrative", amount=0.8)

        c = cfg.composition
        self.assertTrue(bool(c.whole_song_rerank_enabled))
        self.assertTrue(bool(c.song_blueprint_enabled))
        self.assertTrue(bool(c.song_blueprint_apply_targets_enabled))
        self.assertTrue(bool(c.cadence_first_harmony_enabled))
        self.assertTrue(bool(c.motif_lifecycle_enabled))
        self.assertTrue(bool(c.arrangement_contracts_enabled))
        self.assertGreaterEqual(float(c.whole_song_rerank_blueprint_weight), 0.60)
        self.assertGreaterEqual(float(c.song_blueprint_target_strength), 0.74)
        self.assertGreaterEqual(float(c.cadence_first_harmony_strength), 0.80)
        self.assertGreaterEqual(float(c.motif_lifecycle_strength), 0.72)
        self.assertGreaterEqual(float(c.arrangement_contracts_strength), 0.74)
        self.assertGreaterEqual(int(c.section_k_samples), 3)
        self.assertGreaterEqual(float(c.section_pick_time_budget_s), 0.85)


if __name__ == "__main__":
    unittest.main()
