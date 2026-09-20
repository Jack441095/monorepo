import unittest


class EmotionSectionRoleProfileTests(unittest.TestCase):
    def test_joy_chorus_lifts_more_than_verse(self):
        from composition.policies import ArrangementPolicy
        from data.music_data import EMOTION_BY_NAME

        policy = ArrangementPolicy()
        joy = EMOTION_BY_NAME["joy"]
        verse = policy.arrangement_curve(1, joy)
        chorus = policy.arrangement_curve(3, joy)

        self.assertGreater(float(chorus.get("melody_density_mult", 1.0)), float(verse.get("melody_density_mult", 1.0)))
        self.assertGreater(float(chorus.get("section_dynamic", 1.0)), float(verse.get("section_dynamic", 1.0)))

    def test_grief_chorus_stays_restrained(self):
        from composition.policies import ArrangementPolicy
        from data.music_data import EMOTION_BY_NAME

        policy = ArrangementPolicy()
        grief = EMOTION_BY_NAME["grief"]
        verse = policy.arrangement_curve(1, grief)
        chorus = policy.arrangement_curve(3, grief)

        self.assertLessEqual(float(chorus.get("section_dynamic", 1.0)), float(verse.get("section_dynamic", 1.0)) * 1.12)
        self.assertLess(float(chorus.get("arp_density_mult", 1.0)), 1.0)

    def test_sadness_intro_and_verse_are_not_underwritten(self):
        from composition.policies import ArrangementPolicy
        from data.music_data import EMOTION_BY_NAME

        policy = ArrangementPolicy()
        sadness = EMOTION_BY_NAME["sadness"]
        intro = policy.arrangement_curve(0, sadness)
        verse = policy.arrangement_curve(1, sadness)

        self.assertGreaterEqual(float(intro.get("melody_density_mult", 0.0)), 0.95)
        self.assertGreaterEqual(float(verse.get("melody_density_mult", 0.0)), 0.95)
        self.assertLessEqual(float(intro.get("markov_rest_prob_mult", 1.0)), 1.0)
        self.assertLessEqual(float(verse.get("markov_rest_prob_mult", 1.0)), 1.0)
        # Default arranged form: intro has no arp bed; verse picks it up.
        self.assertLess(float(intro.get("arp_enabled", 1.0)), 0.5)
        self.assertGreaterEqual(float(verse.get("arp_enabled", 0.0)), 1.0)
        self.assertGreaterEqual(float(intro.get("arp_target_notes_per_bar", 0.0)), 5.0)
        self.assertGreaterEqual(float(verse.get("arp_target_notes_per_bar", 0.0)), 5.0)

    def test_quiet_emotion_verses_have_subtle_arp_bed(self):
        from types import SimpleNamespace

        from composition.policies import ArrangementPolicy
        from data.music_data import EMOTION_BY_NAME

        policy = ArrangementPolicy()
        for name in ("grief", "remorse", "relief", "calm", "peaceful", "serenity", "caring"):
            with self.subTest(emotion=name):
                emotion = EMOTION_BY_NAME.get(
                    name,
                    SimpleNamespace(name=name, tempo_multiplier=0.82, velocity_multiplier=0.85, density=0.42),
                )
                curve = policy.arrangement_curve(1, emotion)
                self.assertGreaterEqual(float(curve.get("arp_enabled", 0.0)), 1.0)
                self.assertGreater(float(curve.get("arp_density_mult", 0.0)), 0.20)
                self.assertLessEqual(float(curve.get("arp_velocity_scale", 1.0)), 0.92)

    def test_fear_prechorus_has_more_tension_than_verse(self):
        from composition.policies import ArrangementPolicy
        from data.music_data import EMOTION_BY_NAME

        policy = ArrangementPolicy()
        fear = EMOTION_BY_NAME["fear"]
        verse = policy.arrangement_curve(1, fear)
        pre = policy.arrangement_curve(2, fear)

        self.assertGreater(float(pre.get("tension_mult", 1.0)), float(verse.get("tension_mult", 1.0)))


if __name__ == "__main__":
    unittest.main()
