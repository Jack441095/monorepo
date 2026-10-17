import random
import unittest


class MelodyGeneratorIntegrationTests(unittest.TestCase):
    def test_train_then_generate_with_phrases_smoke(self) -> None:
        from data.music_data import EMOTIONS

        from ai.markov.melody.generator import MelodyGenerator

        rng = random.Random(123)
        g = MelodyGenerator(rng=rng)
        g.train_from_melodies(
            [
                [(0, 1.0), (2, 1.0), (4, 1.0), (2, 1.0)],
                [(2, 0.5), (4, 0.5), (0, 1.0)],
            ],
            emotion_name="neutral",
        )
        emotion = next(e for e in EMOTIONS if getattr(e, "name", "").lower() == "neutral")
        chords = ["I"] * 32
        roots = [0] * 32
        out = g.generate_with_phrases(
            phrase_contours=["static"],
            start_degree=0,
            notes_per_phrase=[8],
            temperature=1.0,
            emotion=emotion,
            chords=chords,
            roots=roots,
            total_beats=32.0,
        )
        self.assertGreater(len(out), 0)


if __name__ == "__main__":
    unittest.main()
