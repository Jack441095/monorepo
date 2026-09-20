import unittest


class CountermelodyScriptTests(unittest.TestCase):
    def _counter(self, bar: int, beat: float = 0.0, midi: int = 72):
        st = float(bar * 4.0 + beat)
        return (5, int(midi), 70, st, 0.5, [int(midi)])

    def _lead(self, bar: int, beat: float = 0.0, midi: int = 84):
        st = float(bar * 4.0 + beat)
        return (2, int(midi), 90, st, 0.5, [int(midi)])

    def test_chorus_counter_waits_until_after_entry(self):
        from composition.counter_melody import apply_countermelody_script

        events = [self._counter(0), self._counter(1), self._counter(2)]
        out = apply_countermelody_script(
            events,
            bars=4,
            beats_per_bar=4.0,
            section_role="b",
            phrase_roles=["opening", "continuation", "continuation", "cadence"],
            cadence_window=[0.0, 0.0, 0.0, 1.0],
            strength=1.0,
        )
        bars = [int(float(ev[3]) // 4.0) for ev in out]
        self.assertNotIn(0, bars)
        self.assertIn(1, bars)

    def test_prechorus_counter_blooms_later(self):
        from composition.counter_melody import apply_countermelody_script

        events = [self._counter(0), self._counter(1), self._counter(2), self._counter(3)]
        out = apply_countermelody_script(
            events,
            bars=4,
            beats_per_bar=4.0,
            section_role="pre_chorus",
            phrase_roles=["opening", "continuation", "continuation", "cadence"],
            cadence_window=[0.0, 0.0, 0.0, 0.0],
            strength=1.0,
        )
        bars = [int(float(ev[3]) // 4.0) for ev in out]
        self.assertNotIn(0, bars)
        self.assertIn(2, bars)

    def test_answer_bar_stays_clear_when_lead_is_busy(self):
        from composition.counter_melody import apply_countermelody_script

        events = [self._counter(1)]
        lead = [self._lead(1, 0.0), self._lead(1, 1.0)]
        out = apply_countermelody_script(
            events,
            bars=4,
            beats_per_bar=4.0,
            section_role="a",
            lead_events=lead,
            phrase_roles=["opening", "answer", "continuation", "cadence"],
            cadence_window=[0.0, 0.0, 0.0, 0.0],
            strength=1.0,
        )
        self.assertEqual(out, [])


if __name__ == "__main__":
    unittest.main()
