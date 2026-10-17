import unittest


class MotifMemoryFallbackTests(unittest.TestCase):
    def test_motif_plan_can_seed_theme_from_lead_section(self) -> None:
        from composition.engine import CompositionGenerator
        from composition.motif_plan import MotifPlanManager
        from composition.section_plan import SectionPlan
        from data.music_data import EMOTIONS

        gen = CompositionGenerator(enable_perf_monitoring=False, use_voice_leading=False)
        mgr = MotifPlanManager(owner=gen)
        emotion = EMOTIONS[0]
        root = 60
        scale = list(emotion.scale_intervals)

        plan = SectionPlan(emotion=emotion, root_note=root, bars=4)
        plan.beats_per_bar = 4.0
        plan.chords = ["Imaj7"] * 4
        plan.roots = [root] * 4
        degrees = [0, 1, 3, 2, 4]
        plan.melody_events = [
            (2, root + int(scale[d]), 88, float(i), 0.5, [root + int(scale[d])])
            for i, d in enumerate(degrees)
        ]

        seeded = mgr.seed_from_section_plan_if_needed(plan, role="a")

        self.assertTrue(seeded)
        self.assertIsNotNone(mgr.theme())
        self.assertGreater(sum(abs(int(v)) for v in mgr.theme().intervals), 1)
        self.assertTrue(getattr(gen, "_song_motif_hook_seeded", False))

    def test_apply_to_section_plan_uses_fallback_when_library_is_empty(self) -> None:
        from composition.engine import CompositionGenerator
        from composition.motif_plan import MotifPlanManager
        from composition.section_plan import SectionPlan
        from data.music_data import EMOTIONS

        gen = CompositionGenerator(enable_perf_monitoring=False, use_voice_leading=False)
        mgr = MotifPlanManager(owner=gen)
        emotion = EMOTIONS[0]
        root = 60
        scale = list(emotion.scale_intervals)

        plan = SectionPlan(emotion=emotion, root_note=root, bars=8)
        plan.beats_per_bar = 4.0
        plan.chords = ["Imaj7"] * 8
        plan.roots = [root] * 8
        degrees = [0, 1, 3, 2, 4, 3]
        plan.melody_events = [
            (2, root + int(scale[d]), 88, float(i), 0.5, [root + int(scale[d])])
            for i, d in enumerate(degrees)
        ]

        mgr.apply_to_section_plan(plan, role="a", section_index=1)

        self.assertIsNotNone(mgr.theme())
        evs = [e for e in plan.melody_events if len(e) == 6 and int(e[0]) == 2]
        self.assertTrue(evs)
        self.assertTrue(getattr(gen, "_song_motif_hook_seeded", False))


if __name__ == "__main__":
    unittest.main()
