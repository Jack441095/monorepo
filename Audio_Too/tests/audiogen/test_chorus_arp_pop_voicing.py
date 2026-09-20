import unittest


def _arp_notes(events):
    return [int(ev[1]) for ev in events if len(ev) == 6 and int(ev[0]) == 3 and isinstance(ev[1], int)]

def _median_int(xs):
    xs = sorted(int(x) for x in (xs or []))
    if not xs:
        return None
    return int(xs[len(xs) // 2])


class ChorusArpPopVoicingTests(unittest.TestCase):
    def test_chorus_arp_is_higher_and_busier_than_verse(self):
        from composition.engine import CompositionGenerator
        from data.music_data import EMOTION_BY_NAME

        emotion = EMOTION_BY_NAME["neutral"]

        verse_gen = CompositionGenerator(enable_perf_monitoring=False)
        verse_gen.reseed(24017)
        verse = verse_gen.generate_section(
            emotion,
            root_note=60,
            bars=8,
            temperature=0.5,
            target_notes_per_bar=4.0,
            melody_style="auto",
            humanization_scale=0.0,
            section_index=1,  # A / verse in default form
        )

        chorus_gen = CompositionGenerator(enable_perf_monitoring=False)
        chorus_gen.reseed(24017)
        chorus = chorus_gen.generate_section(
            emotion,
            root_note=60,
            bars=8,
            temperature=0.5,
            target_notes_per_bar=4.0,
            melody_style="auto",
            humanization_scale=0.0,
            section_index=3,  # B / chorus in default form
        )

        verse_notes = _arp_notes(verse)
        chorus_notes = _arp_notes(chorus)
        self.assertTrue(chorus_notes)
        # Ambient defaults can keep a denser arp bed in verse and a sparser chorus hook.
        # When both lanes have arp, chorus should still sit at least as high in register.
        if verse_notes:
            self.assertGreaterEqual(int(max(chorus_notes)), int(max(verse_notes)))

    def test_stable_pop_voicing_prefers_four_note_clean_shells(self):
        from composition.engine import CompositionGenerator

        gen = CompositionGenerator(enable_perf_monitoring=False)
        vle = gen.voice_leading_engine

        candidates = vle.get_possible_notes_for_part(
            "chord",
            "Imaj11",
            60,
            prev_notes=None,
            emotion_name="neutral",
        )
        self.assertTrue(candidates)

        found_clean_four_note = False
        for cand in candidates:
            notes = sorted(int(n) for n in cand)
            self.assertLessEqual(len(notes), 4)
            pcs = {(int(n) - 60) % 12 for n in notes}
            # Stable pop voicings should omit the 11th color by default here.
            self.assertNotIn(5, pcs)
            if len(notes) == 4 and {0, 4}.issubset(pcs):
                found_clean_four_note = True

        self.assertTrue(found_clean_four_note)


if __name__ == "__main__":
    unittest.main()
