import unittest


class MotifRhythmCellOverrideTests(unittest.TestCase):
    def test_hook_render_uses_rhythm_override(self):
        from composition.engine import CompositionGenerator
        from composition.motif_plan import MotifPlanManager, MotifSlot, SongHookMotif
        from data.music_data import EMOTIONS

        gen = CompositionGenerator(enable_perf_monitoring=False)
        m = MotifPlanManager(owner=gen)
        emotion = EMOTIONS[0]

        hook = SongHookMotif(intervals=[0, 1, -1, 2, -2, 1], rhythms=[0.5] * 6)
        slot = MotifSlot(start_beats=0.0, length_beats=4.0, strength=1.0)
        chords = ["Imaj7"] * 4
        roots = [60] * 4

        override = [1.0, 1.0, 1.0, 1.0]
        evs = m._render_hook_as_events(
            hook,
            emotion=emotion,
            chords=chords,
            roots=roots,
            bars=4,
            beats_per_bar=4.0,
            slot=slot,
            channel=2,
            octave_shift=0,
            rhythm_override=override,
        )
        self.assertTrue(evs)
        durs = [float(e[4]) for e in evs[:4] if len(e) == 6 and int(e[0]) == 2]
        self.assertEqual(durs, override)

    def test_prechorus_can_reuse_song_rhythm_cell(self):
        from composition.engine import CompositionGenerator
        from composition.motif_plan import MotifPlanManager, SongHookMotif
        from composition.section_plan import SectionPlan
        from data.music_data import EMOTIONS

        gen = CompositionGenerator(enable_perf_monitoring=False)
        m = MotifPlanManager(owner=gen)
        m._theme = SongHookMotif(intervals=[0, 1, -1, 0], rhythms=[0.5, 0.5, 0.5, 0.5])
        setattr(gen, "_song_rhythm_cell", [1.0, 1.0, 1.0, 1.0])

        emotion = EMOTIONS[0]
        plan = SectionPlan(emotion=emotion, root_note=60, bars=8)
        plan.beats_per_bar = 4.0
        plan.chords = ["Imaj7"] * 8
        plan.roots = [60] * 8
        plan.melody_events = []

        m.apply_to_section_plan(plan, role="pre_chorus", section_index=2)

        evs = [e for e in plan.melody_events if len(e) == 6 and int(e[0]) == 2]
        self.assertTrue(evs)
        durs = [float(e[4]) for e in sorted(evs, key=lambda e: float(e[3]))[:4]]
        self.assertEqual(durs, [1.0, 1.0, 1.0, 1.0])


if __name__ == "__main__":
    unittest.main()
