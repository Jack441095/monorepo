import unittest


class TransitionArrangementGestureTests(unittest.TestCase):
    def _plan(self, role="pre_chorus"):
        from composition.section_plan import SectionPlan
        from data.music_data import EMOTION_BY_NAME

        return SectionPlan(
            emotion=EMOTION_BY_NAME["neutral"],
            root_note=60,
            bars=4,
            beats_per_bar=4.0,
            section_role=role,
            chosen_bass=[36, 38, 40, 41],
            chosen_chord=[[60, 64, 67], [62, 65, 69], [64, 67, 71], [65, 69, 72]],
            roots=[60, 62, 64, 65],
        )

    def test_prechorus_to_chorus_adds_audible_pickup_gestures(self):
        from composition.event import Event
        from composition.section_planner.planner import SectionPlanner

        plan = self._plan("pre_chorus")
        events = [
            Event(1, 0, 70, 12.0, 4.0, [65, 69, 72]),
            Event(0, 41, 58, 12.0, 4.0, [41]),
            Event(3, 76, 58, 15.25, 0.2, [76]),
        ]

        out = SectionPlanner._apply_section_transition_gestures_typed(
            events,
            plan,
            next_role="b",
            strength=1.0,
        )

        bass_pickups = [ev for ev in out if ev.channel == 0 and ev.start_beats >= 15.0]
        arp_fill = [ev for ev in out if ev.channel == 3 and ev.start_beats >= 15.0]
        chord_hits = [ev for ev in out if ev.channel == 1 and abs(ev.start_beats - 15.5) < 0.05]
        self.assertGreaterEqual(len(bass_pickups), 2)
        self.assertGreaterEqual(len(arp_fill), 2)
        self.assertTrue(chord_hits)

    def test_chorus_to_verse_thins_late_busy_layers(self):
        from composition.event import Event
        from composition.section_planner.planner import SectionPlanner

        plan = self._plan("b")
        events = [
            Event(1, 0, 78, 12.0, 4.0, [65, 69, 72]),
            Event(3, 76, 70, 15.25, 0.2, [76]),
            Event(5, 72, 68, 15.5, 0.2, [72]),
            Event(2, 72, 76, 15.5, 0.4, [72]),
        ]

        out = SectionPlanner._apply_section_transition_gestures_typed(
            events,
            plan,
            next_role="a",
            strength=1.0,
        )

        late_clutter = [ev for ev in out if ev.channel in {3, 5} and ev.start_beats >= 15.0]
        lead = [ev for ev in out if ev.channel == 2]
        self.assertFalse(late_clutter)
        self.assertEqual(len(lead), 1)


if __name__ == "__main__":
    unittest.main()
