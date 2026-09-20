import unittest
from types import SimpleNamespace


class EmotionDataTuningTests(unittest.TestCase):
    def test_every_emotion_has_a_dedicated_harmony_profile(self):
        from data.harmony_profiles import EMOTION_HARMONY_PROFILES
        from data.music_data import EMOTIONS

        missing = sorted(
            name.lower()
            for name in (getattr(e, "name", "") for e in EMOTIONS)
            if name and name.lower() not in EMOTION_HARMONY_PROFILES
        )
        self.assertEqual(missing, [])

    def test_harmony_profile_lookup_uses_alias_normalization(self):
        from data.harmony_profiles import harmony_profile_for_emotion

        self.assertEqual(
            harmony_profile_for_emotion("greif"),
            harmony_profile_for_emotion("grief"),
        )
        self.assertEqual(
            harmony_profile_for_emotion("angry"),
            harmony_profile_for_emotion("anger"),
        )

    def test_arrangement_override_lookup_uses_alias_normalization(self):
        from data.emotion_profiles import arrangement_overrides_for_emotion

        typo = SimpleNamespace(name="excitment", tempo_multiplier=1.0, velocity_multiplier=1.0, density=0.5)
        canon = SimpleNamespace(name="excitement", tempo_multiplier=1.0, velocity_multiplier=1.0, density=0.5)
        self.assertEqual(arrangement_overrides_for_emotion(typo), arrangement_overrides_for_emotion(canon))

    def test_warm_emotions_keep_a_subtle_arp_bed(self):
        from data.emotion_profiles import arrangement_overrides_for_emotion
        from data.music_data import EMOTION_BY_NAME

        for name in ("caring", "gratitude", "love"):
            with self.subTest(emotion=name):
                curve = arrangement_overrides_for_emotion(EMOTION_BY_NAME[name])
                self.assertGreaterEqual(float(curve.get("arp_enabled", 0.0)), 1.0)
                self.assertGreater(float(curve.get("arp_density_mult", 0.0)), 0.55)
                self.assertLessEqual(float(curve.get("arp_velocity_scale", 1.0)), 0.90)


if __name__ == "__main__":
    unittest.main()
