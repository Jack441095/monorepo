import random
import unittest


class HookMelodyUpgradeTests(unittest.TestCase):
    def test_hook_anchor_degree_can_anchor_injected_motif(self):
        from audiogen_core.config import CONFIG
        from composition.engine import CompositionGenerator
        from composition.motif_plan import MotifPlanManager, SongHookMotif
        from composition.section_plan import SectionPlan
        from data.music_data import EMOTIONS

        # Snapshot and restore config to avoid cross-test pollution.
        prev = getattr(CONFIG.composition, "hook_anchor_degree_strength", 0.0)
        try:
            setattr(CONFIG.composition, "hook_anchor_degree_strength", 1.0)

            gen = CompositionGenerator(enable_perf_monitoring=False)
            m = MotifPlanManager(owner=gen)
            # Pre-seed theme motif (skip library dependency).
            m._theme = SongHookMotif(intervals=[0, 0, 0, 0], rhythms=[0.5, 0.5, 0.5, 0.5])

            emotion = EMOTIONS[0]
            root_note = 60
            bars = 16
            plan = SectionPlan(emotion=emotion, root_note=root_note, bars=bars)
            plan.beats_per_bar = 4.0
            plan.chords = ["Imaj7"] * bars
            plan.roots = [root_note] * bars
            plan.melody_events = []

            # Fake phrase plan output from MelodyGenerator.PhrasePlanner.
            class _PP:
                phrase_role = "opening"
                # Use a chord-tone degree for I chord so chord-tone snapping
                # doesn't legitimately nudge it away (keeps this test focused).
                hook_anchor_degree = 2

            setattr(gen.melody_gen, "_last_phrase_plans", [_PP(), _PP(), _PP(), _PP()])

            m.apply_to_section_plan(plan, role="b", section_index=0)
            self.assertTrue(plan.melody_events)

            # The motif starts at bar 0. With intervals=[0,0,0,0], the first injected note degree
            # should equal hook_anchor_degree (2).
            first = min([e for e in plan.melody_events if len(e) == 6 and int(e[0]) == 2], key=lambda e: float(e[3]))
            midi = int(first[1])
            scale = list(getattr(emotion, "scale_intervals", []) or [])
            self.assertTrue(scale)
            # Role "b" lifts the motif by an octave in MotifPlanManager.
            from midi.midi_range_limiter import RANGE_LIMITER

            expected_raw = int(root_note + int(scale[int(2) % len(scale)]) + 12)
            expected = int(RANGE_LIMITER.clamp_note(int(expected_raw), 2))
            self.assertEqual(midi, expected)
        finally:
            setattr(CONFIG.composition, "hook_anchor_degree_strength", prev)

    def test_motif_transform_choice_is_deterministic_under_seed(self):
        from ai.markov.melody.motif_manager import MotifManager

        choices = ["augment", "diminish", "fragment", "invert", "retrograde", "sequence", "transpose"]

        r1 = random.Random(123)
        m1 = MotifManager(rng=r1)
        a = m1._pick_variation_type(
            variation_choices=list(choices),
            section_role="b",
            development=0.25,
            strength=1.0,
        )

        r2 = random.Random(123)
        m2 = MotifManager(rng=r2)
        b = m2._pick_variation_type(
            variation_choices=list(choices),
            section_role="b",
            development=0.25,
            strength=1.0,
        )

        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()

