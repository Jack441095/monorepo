import unittest


class PresetCompositionOverrideTests(unittest.TestCase):
    def test_apply_preset_can_set_hook_safe_mode_and_composition_overrides(self):
        from audiogen_core.config import ConfigurationManager
        from presets.config_applier import apply_preset_to_config
        from presets.presets import PresetV1

        cfg = ConfigurationManager()
        preset = PresetV1(
            name="smooth-test",
            arrangement_style="pop_ext",
            metadata={
                "hook_safe_mode": True,
                "composition_overrides": {
                    "transition_blend_bars": 8,
                    "modulation_probability": 0.15,
                },
            },
        )

        apply_preset_to_config(cfg, preset)

        self.assertEqual(str(cfg.composition.arranged_song_mode), "pop_ext")
        self.assertTrue(bool(cfg.composition.hook_safe_mode))
        self.assertEqual(int(cfg.composition.transition_blend_bars), 8)
        self.assertAlmostEqual(float(cfg.composition.modulation_probability), 0.15, places=6)


if __name__ == "__main__":
    unittest.main()
