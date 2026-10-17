import unittest


class BassEmotionPersonalityTests(unittest.TestCase):
    def test_sadness_bass_uses_descending_weight(self):
        from composition.engine import CompositionGenerator
        from data.music_data import EMOTION_BY_NAME

        gen = CompositionGenerator(enable_perf_monitoring=False)
        events = gen.harmony_manager.generate_bass_events(
            chords=["Am", "G"],
            roots=[57, 55],
            bars=2,
            beats_per_bar=4.0,
            chosen_bass=[45, 43],
            emotion=EMOTION_BY_NAME["sadness"],
            section_role="a",
            timeline_targets={"cadence_window": [0.0, 0.0], "breath_window": [0.0, 0.0]},
        )

        first_bar_notes = [int(ev[1]) for ev in events if len(ev) == 6 and int(ev[0]) == 0 and float(ev[3]) < 4.0]
        self.assertEqual(len(first_bar_notes), 2)
        self.assertLess(first_bar_notes[1], first_bar_notes[0])

    def test_fear_bass_pedals_root(self):
        from composition.engine import CompositionGenerator
        from data.music_data import EMOTION_BY_NAME

        gen = CompositionGenerator(enable_perf_monitoring=False)
        events = gen.harmony_manager.generate_bass_events(
            chords=["Cm", "Ab"],
            roots=[60, 56],
            bars=2,
            beats_per_bar=4.0,
            chosen_bass=[36, 32],
            emotion=EMOTION_BY_NAME["fear"],
            section_role="b",
            timeline_targets={},
        )

        first_bar_notes = [int(ev[1]) for ev in events if len(ev) == 6 and int(ev[0]) == 0 and float(ev[3]) < 4.0]
        self.assertEqual(first_bar_notes, [36, 36])


if __name__ == "__main__":
    unittest.main()
