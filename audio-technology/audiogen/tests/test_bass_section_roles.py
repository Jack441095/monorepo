import unittest


def _bass_events(events):
    return [ev for ev in events if len(ev) == 6 and int(ev[0]) == 0]


class BassSectionRoleTests(unittest.TestCase):
    def test_chorus_bass_is_busier_than_verse(self):
        from composition.engine import CompositionGenerator
        from data.music_data import EMOTION_BY_NAME

        emotion = EMOTION_BY_NAME["neutral"]

        verse_gen = CompositionGenerator(enable_perf_monitoring=False)
        verse_gen.reseed(301)
        verse = verse_gen.generate_section(
            emotion,
            root_note=60,
            bars=8,
            temperature=0.5,
            target_notes_per_bar=4.0,
            melody_style="auto",
            humanization_scale=0.0,
            section_index=1,
        )

        chorus_gen = CompositionGenerator(enable_perf_monitoring=False)
        chorus_gen.reseed(301)
        chorus = chorus_gen.generate_section(
            emotion,
            root_note=60,
            bars=8,
            temperature=0.5,
            target_notes_per_bar=4.0,
            melody_style="auto",
            humanization_scale=0.0,
            section_index=3,
        )

        self.assertLess(len(_bass_events(verse)), len(_bass_events(chorus)))

    def test_prechorus_bass_uses_more_than_one_onset_per_bar(self):
        from composition.engine import CompositionGenerator
        from data.music_data import EMOTION_BY_NAME

        emotion = EMOTION_BY_NAME["neutral"]
        gen = CompositionGenerator(enable_perf_monitoring=False)
        gen.reseed(302)
        events = gen.generate_section(
            emotion,
            root_note=60,
            bars=8,
            temperature=0.5,
            target_notes_per_bar=4.0,
            melody_style="auto",
            humanization_scale=0.0,
            section_index=2,
        )
        bass = _bass_events(events)
        starts_by_bar = {}
        for ev in bass:
            bar = int(float(ev[3]) // 4.0)
            starts_by_bar.setdefault(bar, 0)
            starts_by_bar[bar] += 1
        self.assertTrue(any(v >= 2 for v in starts_by_bar.values()))

    def test_prechorus_bass_walks_across_all_quarter_notes(self):
        from composition.engine import CompositionGenerator
        from data.music_data import EMOTION_BY_NAME

        gen = CompositionGenerator(enable_perf_monitoring=False)
        events = gen.harmony_manager.generate_bass_events(
            chords=["C", "G"],
            roots=[60, 67],
            bars=2,
            beats_per_bar=4.0,
            chosen_bass=[36, 43],
            emotion=EMOTION_BY_NAME["neutral"],
            section_role="pre_chorus",
            timeline_targets={},
        )

        starts_bar0 = sorted(float(ev[3]) for ev in events if len(ev) == 6 and int(ev[0]) == 0 and float(ev[3]) < 4.0)
        self.assertEqual(starts_bar0, [0.0, 1.0, 2.0, 3.0])

    def test_verse_family_shapes_prechorus_climb_cell(self):
        from composition.engine import CompositionGenerator
        from data.music_data import EMOTION_BY_NAME

        gen = CompositionGenerator(enable_perf_monitoring=False)
        neutral = EMOTION_BY_NAME["neutral"]

        gen.harmony_manager.generate_bass_events(
            chords=["Am", "Am"],
            roots=[57, 57],
            bars=2,
            beats_per_bar=4.0,
            chosen_bass=[33, 33],
            emotion=neutral,
            section_role="a",
            timeline_targets={},
        )
        events = gen.harmony_manager.generate_bass_events(
            chords=["Am", "G"],
            roots=[57, 55],
            bars=2,
            beats_per_bar=4.0,
            chosen_bass=[33, 43],
            emotion=neutral,
            section_role="pre_chorus",
            timeline_targets={},
        )

        notes = [int(ev[1]) for ev in events if len(ev) == 6 and int(ev[0]) == 0 and float(ev[3]) < 4.0]
        self.assertEqual(notes[:2], [33, 33])

    def test_tag_reuses_chorus_bass_motif_family(self):
        from composition.engine import CompositionGenerator
        from data.music_data import EMOTION_BY_NAME

        gen = CompositionGenerator(enable_perf_monitoring=False)
        neutral = EMOTION_BY_NAME["neutral"]

        chorus = gen.harmony_manager.generate_bass_events(
            chords=["C", "C"],
            roots=[60, 60],
            bars=2,
            beats_per_bar=4.0,
            chosen_bass=[36, 36],
            emotion=neutral,
            section_role="b",
            timeline_targets={},
        )
        tag = gen.harmony_manager.generate_bass_events(
            chords=["C", "C"],
            roots=[60, 60],
            bars=2,
            beats_per_bar=4.0,
            chosen_bass=[36, 36],
            emotion=neutral,
            section_role="tag",
            timeline_targets={},
        )

        chorus_notes = [int(ev[1]) for ev in chorus if len(ev) == 6 and int(ev[0]) == 0 and float(ev[3]) < 4.0]
        tag_notes = [int(ev[1]) for ev in tag if len(ev) == 6 and int(ev[0]) == 0 and float(ev[3]) < 4.0]
        self.assertEqual(chorus_notes, tag_notes)


if __name__ == "__main__":
    unittest.main()
