import unittest
from types import SimpleNamespace


class EmotionMelodyPriorTests(unittest.TestCase):
    def test_every_music_data_emotion_has_a_sampler_prior(self) -> None:
        from data.emotion_melody_priors import EMOTION_MELODY_PRIORS
        from data.music_data import EMOTIONS

        missing = sorted(
            name.lower()
            for name in (getattr(e, "name", "") for e in EMOTIONS)
            if name and name.lower() not in EMOTION_MELODY_PRIORS
        )
        self.assertEqual(missing, [])

    def test_sad_emotions_are_more_descending_and_long_breathed_than_joy(self) -> None:
        from data.emotion_melody_priors import emotion_melody_prior_for

        sadness = emotion_melody_prior_for("sadness")
        grief = emotion_melody_prior_for("grief")
        joy = emotion_melody_prior_for("joy")

        self.assertGreater(sadness.descending_mult, joy.descending_mult)
        self.assertGreater(grief.long_rhythm_mult, joy.long_rhythm_mult)
        self.assertGreater(grief.interval_step_mult, joy.interval_step_mult)
        self.assertLess(grief.interval_large_leap_mult, joy.interval_large_leap_mult)

    def test_nervousness_prefers_shorter_rhythm_than_grief(self) -> None:
        from data.emotion_melody_priors import emotion_melody_prior_for

        nervous = emotion_melody_prior_for("nervousness")
        grief = emotion_melody_prior_for("grief")

        self.assertGreater(nervous.short_rhythm_mult, grief.short_rhythm_mult)
        self.assertLess(nervous.long_rhythm_mult, grief.long_rhythm_mult)

    def test_alias_lookup_uses_canonical_emotion_name(self) -> None:
        from data.emotion_melody_priors import emotion_melody_prior_for

        self.assertEqual(emotion_melody_prior_for("greif"), emotion_melody_prior_for("grief"))
        self.assertEqual(emotion_melody_prior_for("sad"), emotion_melody_prior_for("sadness"))

    def test_rhythm_bias_uses_emotion_priors(self) -> None:
        from ai.markov.melody.note_generator._core import NoteGenerator

        base = {0.25: 1.0, 0.5: 1.0, 1.0: 1.0, 2.0: 1.0, 4.0: 1.0}
        grief = NoteGenerator._bias_rhythm(object(), dict(base), SimpleNamespace(name="grief"), on_downbeat=False)
        joy = NoteGenerator._bias_rhythm(object(), dict(base), SimpleNamespace(name="joy"), on_downbeat=False)
        nervous = NoteGenerator._bias_rhythm(object(), dict(base), SimpleNamespace(name="nervousness"), on_downbeat=False)

        self.assertGreater(grief[4.0], joy[4.0])
        self.assertGreater(nervous[0.5], grief[0.5])
        self.assertGreater(joy[0.25], grief[0.25])


if __name__ == "__main__":
    unittest.main()
