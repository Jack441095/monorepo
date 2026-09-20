import unittest


class PopSectionHarmonyBiasTests(unittest.TestCase):
    def test_prechorus_pool_prefers_dominant_ending(self):
        from data.music_data import EmotionProfile, chord_progression_pool_for_section_role

        emo = EmotionProfile(
            name="test_pop",
            scale_intervals=[0, 2, 4, 5, 7, 9, 11],
            tempo_multiplier=1.0,
            velocity_multiplier=1.0,
            density=1.0,
            chord_progressions=[
                ["I", "V", "vi", "IV"],
                ["vi", "IV", "I", "V"],
                ["I", "iii", "IV", "I"],
                ["ii", "IV", "I", "V7"],
                ["I", "bII", "I", "bII"],
            ],
        )

        pool = chord_progression_pool_for_section_role(emo, "pre_chorus")
        self.assertTrue(pool)
        top = pool[0]
        self.assertTrue(str(top[-1]).startswith("V") or "7" in str(top[-1]) or "sus" in str(top[-1]).lower())

    def test_chorus_pool_prefers_tonic_open_and_close(self):
        from data.music_data import EmotionProfile, chord_progression_pool_for_section_role

        emo = EmotionProfile(
            name="test_pop",
            scale_intervals=[0, 2, 4, 5, 7, 9, 11],
            tempo_multiplier=1.0,
            velocity_multiplier=1.0,
            density=1.0,
            chord_progressions=[
                ["vi", "IV", "I", "V"],
                ["I", "V", "vi", "I"],
                ["I", "iii", "IV", "I"],
                ["ii", "V", "I", "I"],
                ["I", "bII", "V7", "I"],
            ],
        )

        pool = chord_progression_pool_for_section_role(emo, "b")
        self.assertTrue(pool)
        top = pool[0]
        self.assertTrue(str(top[0]).startswith(("I", "i")))
        self.assertTrue(str(top[-1]).startswith(("I", "i")))

    def test_pop_clean_role_avoids_harsh_major_extensions(self):
        from composition.engine import CompositionGenerator

        gen = CompositionGenerator(enable_perf_monitoring=False)
        cp = gen.chord_planner

        for _ in range(24):
            chord = cp.restore_chord_extension("I:maj", "neutral", section_role="b")
            lower = chord.lower()
            self.assertFalse(any(token in lower for token in ("#11", "b9", "#9", "b5", "#5", "maj13")))


if __name__ == "__main__":
    unittest.main()
