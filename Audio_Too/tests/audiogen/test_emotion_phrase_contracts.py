import unittest
from types import SimpleNamespace


class EmotionPhraseContractTests(unittest.TestCase):
    def test_section_role_contour_template_changes_for_chorus(self) -> None:
        from data.melody_phrase_profiles import melody_phrase_contour_sequence_for_emotion

        verse = melody_phrase_contour_sequence_for_emotion("love", 4, section_role="a")
        chorus = melody_phrase_contour_sequence_for_emotion("love", 4, section_role="b")

        self.assertEqual(verse, ["arch", "desc", "arch", "desc"])
        self.assertEqual(chorus, ["arch", "desc", "arch", "asc"])

    def test_phrase_role_sequence_for_tender_emotion_uses_continuation_before_answer(self) -> None:
        from data.melody_phrase_profiles import melody_phrase_role_sequence_for_emotion

        roles = melody_phrase_role_sequence_for_emotion("sadness", 4)
        self.assertEqual(roles, ["opening", "answer", "continuation", "cadence"])

    def test_caring_and_embarrassment_profiles_bias_toward_stable_phrase_shapes(self) -> None:
        from data.melody_phrase_profiles import melody_phrase_contour_sequence_for_emotion

        caring = melody_phrase_contour_sequence_for_emotion("caring", 4, section_role="b")
        embarrassment = melody_phrase_contour_sequence_for_emotion("embarrassment", 4, section_role="a")

        self.assertEqual(caring, ["arch", "static", "arch", "static"])
        self.assertEqual(embarrassment, ["desc", "static", "desc", "static"])

    def test_phrase_planner_uses_profile_driven_final_cadence(self) -> None:
        from ai.markov.melody.phrase_planner import PhrasePlanner

        planner = PhrasePlanner()
        sadness = SimpleNamespace(name="sadness")
        joy = SimpleNamespace(name="joy")
        fear = SimpleNamespace(name="fear")

        sad_plans = planner.generate_plans(["desc", "arch", "desc", "static"], 4, sadness, section_role="a")
        joy_plans = planner.generate_plans(["asc", "asc", "arch", "asc"], 4, joy, section_role="b")
        fear_plans = planner.generate_plans(["arch", "desc", "asc", "desc"], 4, fear, section_role="pre_chorus")

        self.assertEqual(int(sad_plans[-1].cadence_degree), 2)
        self.assertEqual(int(joy_plans[-1].cadence_degree), 0)
        self.assertEqual(int(fear_plans[-1].cadence_degree), 6)

    def test_phrase_planner_uses_profile_role_register_arc(self) -> None:
        from ai.markov.melody.phrase_planner import PhrasePlanner

        planner = PhrasePlanner()
        emotion = SimpleNamespace(name="love")
        plans = planner.generate_plans(["arch", "desc", "arch", "static"], 4, emotion, section_role="a")

        centers = [int(plan.register_center_midi) for plan in plans]
        self.assertLess(centers[0], centers[2])
        self.assertLessEqual(centers[1], centers[3])

    def test_tender_verse_can_use_explicit_restatement_schedule(self) -> None:
        from ai.markov.melody.phrase_repetition import PhraseRepetitionMixin

        class _Rng:
            def random(self):
                return 0.0

            def randint(self, a, b):
                return 0

            def choice(self, seq):
                return seq[0]

        class _Dummy(PhraseRepetitionMixin):
            pass

        mix = _Dummy(phrase_repetition_prob=0.0, rng=_Rng())
        source = [(0, 1.0), (2, 1.0), (4, 2.0)]
        phrase = [(1, 1.0), (3, 1.0), (5, 2.0)]
        plan = SimpleNamespace(
            section_role="a",
            phrase_role="answer",
            cadence_degree=4,
            pre_cadence_degree=3,
            target_climax=4,
            entry_degree=2,
        )

        out = mix._apply_explicit_restatement_schedule(
            phrase,
            [source],
            phrase_idx=1,
            total_phrases=4,
            contour="arch",
            emotion_name="love",
            plan=plan,
        )

        self.assertNotEqual(out, phrase)


if __name__ == "__main__":
    unittest.main()
