import unittest


class MelodyEmotionProfileTuningTests(unittest.TestCase):
    def test_quiet_emotions_have_singable_density_floors(self) -> None:
        from data.melody_emotion_profiles import melody_emotion_profile_for_emotion
        from data.melody_note_profiles import melody_note_profile_for_emotion

        for name in ("sadness", "grief", "remorse", "relief", "disappointment"):
            with self.subTest(emotion=name):
                profile = melody_emotion_profile_for_emotion(name)
                notes = melody_note_profile_for_emotion(name)
                self.assertEqual(profile.name, name)
                self.assertGreaterEqual(float(profile.density_mult), 0.78)
                self.assertGreaterEqual(float(profile.min_notes_per_bar), 1.8)
                self.assertGreaterEqual(float(notes["min_notes_per_bar"]), 3.0)

    def test_calm_alias_style_profiles_do_not_fall_back_to_neutral(self) -> None:
        from data.melody_emotion_profiles import melody_emotion_profile_for_emotion

        for name in ("calm", "peaceful", "serenity"):
            with self.subTest(emotion=name):
                profile = melody_emotion_profile_for_emotion(name)
                self.assertEqual(profile.name, name)
                self.assertLess(float(profile.density_mult), 0.9)
                self.assertGreaterEqual(float(profile.min_notes_per_bar), 1.95)

    def test_low_energy_arrangement_rest_multipliers_are_not_melody_starving(self) -> None:
        from data.emotion_profiles import arrangement_overrides_for_emotion
        from data.music_data import EMOTION_BY_NAME

        for name in ("sadness", "grief", "remorse", "relief", "disappointment"):
            with self.subTest(emotion=name):
                curve = arrangement_overrides_for_emotion(EMOTION_BY_NAME[name])
                self.assertLessEqual(float(curve.get("markov_rest_prob_mult", 1.0)), 1.05)
                self.assertGreaterEqual(float(curve.get("melody_density_mult", 0.0)), 0.82)

    def test_sadness_has_stronger_lead_floor_after_listening_tune(self) -> None:
        from data.emotion_profiles import arrangement_overrides_for_emotion
        from data.melody_emotion_profiles import melody_emotion_profile_for_emotion
        from data.melody_note_profiles import melody_note_profile_for_emotion
        from data.music_data import EMOTION_BY_NAME

        profile = melody_emotion_profile_for_emotion("sadness")
        notes = melody_note_profile_for_emotion("sadness")
        curve = arrangement_overrides_for_emotion(EMOTION_BY_NAME["sadness"])

        self.assertGreaterEqual(float(profile.density_mult), 0.98)
        self.assertGreaterEqual(float(profile.min_notes_per_bar), 2.6)
        self.assertGreaterEqual(float(notes["min_notes_per_bar"]), 3.8)
        self.assertGreaterEqual(float(curve.get("melody_total_notes_mult", 0.0)), 1.0)


if __name__ == "__main__":
    unittest.main()
