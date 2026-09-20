import unittest


class PhraseVocalGrammarAndQATests(unittest.TestCase):
    def _plan(self, role="a"):
        from composition.section_plan import SectionPlan
        from data.music_data import EMOTION_BY_NAME

        plan = SectionPlan(
            emotion=EMOTION_BY_NAME["neutral"],
            root_note=60,
            bars=4,
            beats_per_bar=4.0,
            section_role=role,
            chosen_chord=[[60, 64, 67], [62, 65, 69], [64, 67, 71], [65, 69, 72]],
            roots=[60, 62, 64, 65],
        )
        plan.timeline_targets = {
            "phrase_role_by_bar": ["opening", "answer", "continuation", "cadence"],
            "breath_window": [0.0, 0.0, 0.8, 0.0],
            "cadence_window": [0.0, 0.0, 0.0, 1.0],
        }
        return plan

    def test_vocal_grammar_extends_cadence_note(self):
        from composition.event import Event
        from composition.section_planner.planner import SectionPlanner

        plan = self._plan("a")
        events = [Event(2, 72, 80, 15.0, 0.25, [72])]
        out = SectionPlanner._apply_phrase_vocal_grammar_typed(events, plan, strength=1.0)

        lead = [ev for ev in out if ev.channel == 2][0]
        self.assertGreaterEqual(float(lead.duration_beats), 0.9)

    def test_qa_repairs_empty_core_lead_bars(self):
        from composition.event import Event
        from composition.section_planner.planner import SectionPlanner

        plan = self._plan("pre_chorus")
        events = [Event(2, 72, 80, 0.0, 0.5, [72])]
        out = SectionPlanner._apply_post_generation_qa_typed(events, plan, strength=1.0)

        lead_bars = {int(float(ev.start_beats) // 4.0) for ev in out if ev.channel == 2}
        self.assertGreaterEqual(len(lead_bars), 2)

    def test_qa_skips_intro_repairs(self):
        from composition.event import Event
        from composition.section_planner.planner import SectionPlanner

        plan = self._plan("intro")
        events = [Event(2, 72, 80, 0.0, 0.5, [72])]
        out = SectionPlanner._apply_post_generation_qa_typed(events, plan, strength=1.0)

        self.assertEqual(len(out), 1)


if __name__ == "__main__":
    unittest.main()
