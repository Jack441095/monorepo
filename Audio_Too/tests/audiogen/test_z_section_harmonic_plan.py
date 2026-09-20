"""Tests for :class:`composition.harmonic_plan.HarmonicPlan`.

The ``test_z_`` prefix keeps this module after ``test_section_generation_snapshots.py``
under default ``pytest`` ordering so section RNG goldens stay stable.
"""
import unittest


class HarmonicPlanTests(unittest.TestCase):
    def test_from_section_plan_and_validate(self):
        from composition.harmonic_plan import HarmonicPlan
        from composition.section_plan import SectionPlan
        from data.music_data import EMOTIONS

        emo = EMOTIONS[0]
        p = SectionPlan(emotion=emo, root_note=60, bars=4, beats_per_bar=4.0)
        p.chords = ["I", "IV", "V", "I"]
        p.roots = [60, 60, 60, 60]
        p.chosen_bass = [36, 36, 37, 36]
        p.chosen_melody = [72, 72, 71, 72]
        p.chosen_chord = [[60, 64, 67], [65, 69, 72], [67, 71, 74], [60, 64, 67]]

        hp = HarmonicPlan.from_section_plan(p)
        hp.validate()
        self.assertEqual(hp.bars, 4)
        self.assertEqual(len(hp.chords), 4)
        self.assertEqual(len(hp.chosen_chord), 4)

    def test_validate_rejects_misaligned_chords(self):
        from composition.harmonic_plan import HarmonicPlan

        hp = HarmonicPlan(
            chords=["I", "IV"],
            roots=[60, 60],
            bars=4,
            beats_per_bar=4.0,
            chosen_bass=[36, 36, 36, 36],
            chosen_melody=[72, 72, 72, 72],
        )
        with self.assertRaises(ValueError):
            hp.validate()

    def test_validate_beats_per_bar_positive(self):
        from composition.harmonic_plan import HarmonicPlan

        hp = HarmonicPlan(
            chords=("I", "I", "I", "I"),
            roots=(60, 60, 60, 60),
            bars=4,
            beats_per_bar=0.0,
            chosen_bass=(36, 36, 36, 36),
            chosen_melody=(72, 72, 72, 72),
        )
        with self.assertRaises(ValueError):
            hp.validate()

    def test_slice_for_bar_range(self):
        from composition.harmonic_plan import HarmonicPlan

        hp = HarmonicPlan(
            chords=("I", "IV", "V", "I"),
            roots=(60, 65, 67, 60),
            bars=4,
            beats_per_bar=4.0,
            chosen_bass=(36, 36, 37, 36),
            chosen_melody=(72, 72, 71, 72),
            chosen_chord=((60, 64, 67), (65, 69, 72), (67, 71, 74), (60, 64, 67)),
        )
        sub = hp.slice_for_bar_range(1, 2)
        self.assertEqual(sub.bars, 2)
        self.assertEqual(sub.chords, ("IV", "V"))
        self.assertEqual(sub.roots, (65, 67))
        self.assertEqual(sub.chosen_melody, (72, 71))
        self.assertEqual(len(sub.chosen_chord), 2)
        sub.validate()

    def test_post_init_coerces_lists(self):
        from composition.harmonic_plan import HarmonicPlan

        hp = HarmonicPlan(
            chords=["I", "I"],
            roots=[60, 60],
            bars=2,
            beats_per_bar=4.0,
            chosen_bass=[36, 36],
            chosen_melody=[72, 72],
            chosen_chord=[[60, 64, 67], [60, 64, 67]],
        )
        self.assertIsInstance(hp.chords, tuple)
        self.assertIsInstance(hp.chosen_chord[0], tuple)

    def test_refresh_harmonic_plan_on_section_plan(self):
        from composition.harmonic_plan import HarmonicPlan
        from composition.section_plan import SectionPlan
        from data.music_data import EMOTIONS

        p = SectionPlan(emotion=EMOTIONS[0], root_note=60, bars=2, beats_per_bar=4.0)
        p.chords = ["I", "V"]
        p.roots = [60, 67]
        p.chosen_bass = [36, 35]
        p.chosen_melody = [72, 71]
        p.chosen_chord = [[60, 64, 67], [67, 71, 74]]
        p.refresh_harmonic_plan()
        self.assertIsInstance(p.harmonic_plan, HarmonicPlan)
        p.harmonic_plan.validate()

    def test_harmonic_plan_comping_tracks_post_trim_voicing(self):
        from composition.harmonic_plan import HarmonicPlan
        from composition.section_plan import SectionPlan
        from data.music_data import EMOTIONS

        p = SectionPlan(emotion=EMOTIONS[0], root_note=60, bars=2, beats_per_bar=4.0)
        p.chords = ["I", "I"]
        p.roots = [60, 60]
        p.chosen_bass = [36, 36]
        p.chosen_melody = [72, 72]
        p.chosen_chord = [[60, 64, 67, 71, 74], [60, 64, 67, 69, 72]]
        p.refresh_harmonic_plan()
        self.assertEqual(len(p.harmonic_plan.chosen_chord[0]), 5)
        # Simulate busy-section trim (shell voicing)
        p.chosen_chord = [[60, 67, 74], [60, 64, 72]]
        p.refresh_harmonic_plan_comping()
        self.assertIsInstance(p.harmonic_plan_comping, HarmonicPlan)
        p.harmonic_plan_comping.validate()
        self.assertEqual(len(p.harmonic_plan_comping.chosen_chord[0]), 3)
        self.assertEqual(len(p.harmonic_plan.chosen_chord[0]), 5)

    def test_voicing_changes_degree_weights_vs_symbol_only(self):
        from ai.markov.melody.utils import build_chord_weights_per_bar

        chords = ["I", "I"]
        roots = [60, 60]
        scale = [0, 2, 4, 5, 7, 9, 11]
        sym = build_chord_weights_per_bar(chords, roots, scale, None)
        # Triad symbol weights omit the 6th (A); include A in the voicing so degree 5 appears.
        voiced = [[60, 64, 67, 69], [60, 64, 67]]
        v = build_chord_weights_per_bar(chords, roots, scale, voiced)
        self.assertIn(5, v[0])
        self.assertNotIn(5, sym[0])


if __name__ == "__main__":
    unittest.main()
