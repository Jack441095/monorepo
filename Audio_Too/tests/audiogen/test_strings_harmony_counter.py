import unittest


class _Emotion:
    def __init__(self):
        self.scale_intervals = [0, 2, 4, 5, 7, 9, 11]
        self.velocity_multiplier = 1.0


class StringsHarmonyCounterTests(unittest.TestCase):
    def test_strings_harmony_generates_sustained_counter_events(self):
        from composition.counter_melody import CounterMelodyConfig, generate_counter_melody_events

        events = generate_counter_melody_events(
            emotion=_Emotion(),
            chords=["I", "V", "vi", "IV"],
            roots=[60, 60, 60, 60],
            bars=4,
            beats_per_bar=4.0,
            cfg=CounterMelodyConfig(start_bar=0, end_bar=4),
            mode="strings_harmony",
            strings_hold_beats=3.5,
        )
        self.assertEqual(len(events), 4)
        self.assertTrue(all(int(ev[0]) == 5 for ev in events))
        self.assertTrue(all(abs(float(ev[4]) - 3.5) < 1e-6 for ev in events))

    def test_strings_harmony_respects_cadence_skip(self):
        from composition.counter_melody import CounterMelodyConfig, generate_counter_melody_events

        events = generate_counter_melody_events(
            emotion=_Emotion(),
            chords=["I", "V", "vi", "IV"],
            roots=[60, 60, 60, 60],
            bars=4,
            beats_per_bar=4.0,
            cadence_window=[0.0, 1.0, 0.0, 0.0],
            cfg=CounterMelodyConfig(start_bar=0, end_bar=4),
            mode="strings_harmony",
            strings_hold_beats=2.0,
        )
        starts = [float(ev[3]) for ev in events]
        self.assertNotIn(4.0, starts)  # bar 1 (cadence-marked) should be skipped.


if __name__ == "__main__":
    unittest.main()
