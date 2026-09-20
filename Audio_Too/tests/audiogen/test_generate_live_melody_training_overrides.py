import unittest


class GenerateLiveMelodyTrainingOverridesTests(unittest.TestCase):
    def test_set_composition_coerces_float_like_existing(self) -> None:
        from scripts.generate_live_melody_training_jsonl import _apply_composition_overrides
        from audiogen_core.config import CONFIG

        self.assertTrue(hasattr(CONFIG.composition, "melody_strongbeat_chord_tone_mult"))
        before = float(getattr(CONFIG.composition, "melody_strongbeat_chord_tone_mult"))

        _apply_composition_overrides(["melody_strongbeat_chord_tone_mult=3.25"])
        after = float(getattr(CONFIG.composition, "melody_strongbeat_chord_tone_mult"))
        self.assertAlmostEqual(after, 3.25, places=8)

        setattr(CONFIG.composition, "melody_strongbeat_chord_tone_mult", before)

    def test_set_composition_rejects_unknown_key(self) -> None:
        from scripts.generate_live_melody_training_jsonl import _apply_composition_overrides

        with self.assertRaises(AttributeError):
            _apply_composition_overrides(["definitely_not_a_real_config_key=1"])


if __name__ == "__main__":
    unittest.main()
