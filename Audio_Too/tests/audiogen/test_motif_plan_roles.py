import unittest


class MotifPlanRoleTests(unittest.TestCase):
    def test_default_form_16bar_slots_are_role_aware(self):
        from composition.motif_plan import MotifPlanManager

        m = MotifPlanManager(owner=None)
        # Verse: should schedule short hint + answer.
        a_slots = m.slots_for_section(form_mode="default", role="a", bars=16, beats_per_bar=4.0)
        self.assertEqual(len(a_slots), 2)
        self.assertLessEqual(a_slots[0].length_beats, 4.0 + 1e-6)

        # Pre-chorus: single setup slot near the end.
        pre_slots = m.slots_for_section(form_mode="default", role="pre_chorus", bars=16, beats_per_bar=4.0)
        self.assertEqual(len(pre_slots), 1)

        # Chorus: strong restatement + late quote.
        b_slots = m.slots_for_section(form_mode="default", role="b", bars=16, beats_per_bar=4.0)
        self.assertEqual(len(b_slots), 2)
        self.assertGreaterEqual(b_slots[0].strength, 0.9)

        # Intro: no forced motif.
        intro_slots = m.slots_for_section(form_mode="default", role="intro", bars=16, beats_per_bar=4.0)
        self.assertEqual(intro_slots, [])

    def test_default_form_8bar_slots_are_role_aware(self):
        from composition.motif_plan import MotifPlanManager

        m = MotifPlanManager(owner=None)

        a_slots = m.slots_for_section(form_mode="default", role="a", bars=8, beats_per_bar=4.0)
        self.assertEqual(len(a_slots), 2)
        self.assertLessEqual(a_slots[0].length_beats, 2.0 + 1e-6)

        pre_slots = m.slots_for_section(form_mode="default", role="pre_chorus", bars=8, beats_per_bar=4.0)
        self.assertEqual(len(pre_slots), 1)
        self.assertGreaterEqual(pre_slots[0].start_beats, 24.0 - 1e-6)

        b_slots = m.slots_for_section(form_mode="default", role="b", bars=8, beats_per_bar=4.0)
        self.assertEqual(len(b_slots), 2)
        self.assertGreaterEqual(b_slots[0].strength, 0.9)

        a_prime_slots = m.slots_for_section(form_mode="default", role="a_prime", bars=8, beats_per_bar=4.0)
        self.assertEqual(len(a_prime_slots), 1)
        self.assertGreaterEqual(a_prime_slots[0].strength, 0.9)

    def test_development_snapshot_is_json_safe_and_counts_variants(self):
        from composition.motif_plan import MotifPlanManager, SongHookMotif

        m = MotifPlanManager(owner=None)
        m._theme = SongHookMotif(intervals=[0, 1, -1, 2], rhythms=[0.5, 0.5, 1.0, 1.0], contour="arch")
        m._family_counts = {"main": 2}
        snap = m.development_snapshot(
            role="b",
            section_index=3,
            section_variant="statement",
            motif_id="theme",
            slot_tags=[
                {
                    "motif_variant": "statement",
                    "motif_family": "main",
                    "start_beats": 0.0,
                    "length_beats": 4.0,
                },
                {
                    "motif_variant": "answer",
                    "motif_family": "answer",
                    "start_beats": 16.0,
                    "length_beats": 2.0,
                },
            ],
        )
        self.assertEqual(snap["role"], "b")
        self.assertEqual(snap["motif_id"], "theme")
        self.assertEqual(snap["slot_count"], 2)
        self.assertEqual(snap["variants"], {"answer": 1, "statement": 1})
        self.assertEqual(snap["families"], {"answer": 1, "main": 1})
        self.assertEqual(snap["theme"]["contour"], "arch")


if __name__ == "__main__":
    unittest.main()
