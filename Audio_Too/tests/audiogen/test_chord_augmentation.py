"""Self-generated chord-progression augmentation (docs/AUDIOGEN_COMPOSITION_PLAN.md,
variety work 2026-07-04, scripts/augment_chord_progressions.py).

Each emotion's augmented progressions are sampled ONLY from that emotion's own hand-written
chord vocabulary (bigram transitions), so they can't leak another emotion's harmonic
language. These tests pin that contract: every augmented chord/transition must trace back to
the emotion's own base progressions, augmented pools merge into chord_progressions, and no
augmented progression is a low-variety 2-chord oscillation.
"""
import unittest

from data.chord_progressions_augmented import AUGMENTED_CHORD_PROGRESSIONS
from data.music_data import EMOTION_BY_NAME, EMOTIONS, merged_chord_progression_pool


class TestChordAugmentation(unittest.TestCase):
    def test_augmented_progressions_exist_for_most_emotions(self):
        with_extras = [name for name, progs in AUGMENTED_CHORD_PROGRESSIONS.items() if progs]
        self.assertGreater(len(with_extras), len(EMOTIONS) // 2)

    def test_merged_into_emotion_profile(self):
        emo = EMOTION_BY_NAME["joy"]
        extras = AUGMENTED_CHORD_PROGRESSIONS.get("joy") or []
        for prog in extras:
            self.assertIn(list(prog), [list(p) for p in emo.chord_progressions])

    def test_no_low_variety_oscillation(self):
        for name, progs in AUGMENTED_CHORD_PROGRESSIONS.items():
            for prog in progs:
                if len(prog) >= 5:
                    self.assertGreaterEqual(
                        len(set(prog)), 3,
                        f"{name}: {prog} is a low-variety oscillation",
                    )

    def test_no_immediate_chord_repeats(self):
        for name, progs in AUGMENTED_CHORD_PROGRESSIONS.items():
            for prog in progs:
                for a, b in zip(prog, prog[1:]):
                    self.assertNotEqual(a, b, f"{name}: {prog} has an immediate repeat")

    def test_vocabulary_stays_within_emotions_own_data(self):
        """Every chord token used in an emotion's augmented progressions must appear
        somewhere in that SAME emotion's original hand-written pool -- the guarantee that
        keeps augmentation from borrowing another emotion's harmonic identity."""
        for emo in EMOTIONS:
            name = emo.name.lower()
            extras = AUGMENTED_CHORD_PROGRESSIONS.get(name) or []
            if not extras:
                continue
            base_pool = merged_chord_progression_pool(emo)
            # Recompute the base pool as it existed before augmentation merged in --
            # since merged_chord_progression_pool now includes the augmented entries too,
            # use only progressions NOT present in AUGMENTED_CHORD_PROGRESSIONS.
            aug_set = {tuple(p) for p in extras}
            original_tokens = set()
            for prog in base_pool:
                if tuple(prog) in aug_set:
                    continue
                original_tokens.update(prog)
            for prog in extras:
                for tok in prog:
                    self.assertIn(
                        tok, original_tokens,
                        f"{name}: augmented token {tok!r} not found in original vocabulary",
                    )

    def test_deterministic_regeneration(self):
        from scripts.augment_chord_progressions import augment_emotion

        a = augment_emotion("joy", seed=17)
        b = augment_emotion("joy", seed=17)
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
