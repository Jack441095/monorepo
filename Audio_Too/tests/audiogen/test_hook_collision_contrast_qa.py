import unittest


class HookCollisionContrastQATests(unittest.TestCase):
    def _plan(self, role="b"):
        from composition.section_plan import SectionPlan
        from data.music_data import EMOTION_BY_NAME

        return SectionPlan(
            emotion=EMOTION_BY_NAME["neutral"],
            root_note=60,
            bars=4,
            beats_per_bar=4.0,
            section_role=role,
            chosen_chord=[[60, 64, 67] for _ in range(4)],
            roots=[60, 60, 60, 60],
        )

    def test_hook_strength_restates_weak_second_bar(self):
        from composition.event import Event
        from composition.section_planner.planner import SectionPlanner

        plan = self._plan("b")
        events = [
            Event(2, 72, 80, 0.0, 0.5, [72]),
            Event(2, 74, 78, 1.0, 0.5, [74]),
            Event(2, 76, 79, 2.0, 0.5, [76]),
            Event(1, 60, 70, 4.0, 2.0, [60, 64, 67]),
        ]
        out = SectionPlanner._apply_hook_strength_qa_typed(events, plan, strength=1.0)

        bar2_lead_starts = sorted(round(float(ev.start_beats) - 4.0, 2) for ev in out if int(ev.channel) == 2 and 4.0 <= float(ev.start_beats) < 8.0)
        self.assertEqual(bar2_lead_starts[:3], [0.0, 1.0, 2.0])

    def test_hook_strength_skips_verse(self):
        from composition.event import Event
        from composition.section_planner.planner import SectionPlanner

        plan = self._plan("a")
        events = [Event(2, 72, 80, 0.0, 0.5, [72]), Event(2, 74, 80, 1.0, 0.5, [74])]
        out = SectionPlanner._apply_hook_strength_qa_typed(events, plan, strength=1.0)

        self.assertEqual(len(out), len(events))

    def test_collision_manager_thins_arp_against_busy_lead(self):
        from composition.event import Event
        from composition.section_planner.planner import SectionPlanner

        plan = self._plan("b")
        events = [
            Event(2, 72, 82, 0.0, 0.4, [72]),
            Event(2, 74, 82, 1.0, 0.4, [74]),
            Event(3, 79, 58, 0.0, 0.25, [79]),
            Event(5, 67, 56, 1.0, 0.25, [67]),
            Event(3, 81, 58, 1.5, 0.25, [81]),
        ]
        out = SectionPlanner._apply_arrangement_collision_manager_typed(events, plan, strength=1.0)

        self.assertEqual(sum(1 for ev in out if int(ev.channel) == 2), 2)
        self.assertEqual(sum(1 for ev in out if int(ev.channel) in {3, 5}), 1)

    def test_section_contrast_accents_chorus_downbeat(self):
        from composition.event import Event
        from composition.section_planner.planner import SectionPlanner

        plan = self._plan("b")
        events = [Event(0, 36, 60, 0.0, 1.0, [36]), Event(3, 79, 50, 0.5, 0.25, [79])]
        out = SectionPlanner._apply_section_contrast_qa_typed(events, plan, strength=1.0)

        bass = [ev for ev in out if int(ev.channel) == 0][0]
        self.assertGreater(int(bass.velocity), 60)


if __name__ == "__main__":
    unittest.main()
