import unittest


class PhraseIntentTimelineTests(unittest.TestCase):
    def test_timeline_exports_phrase_intent_payload(self) -> None:
        from composition.section_planner import _make_timeline_targets

        curve = {
            "melody_density_mult": 1.0,
            "chord_rhythm_mult": 1.0,
            "motif_prob_mult": 1.0,
        }
        targets = _make_timeline_targets("a", 8, dict(curve))

        intents = list(targets.get("phrase_intent_by_bar", []) or [])
        funcs = list(targets.get("harmony_function_target_by_bar", []) or [])

        self.assertEqual(len(intents), 8)
        self.assertEqual(len(funcs), 8)
        self.assertEqual(set(str(x) for x in funcs) <= {"T", "PD", "D"}, True)
        self.assertEqual(str(funcs[0]), "T")
        self.assertIn("harmony_function_target", intents[0])
        self.assertIn("cadence_strength", intents[0])
        self.assertIn("melody_activity_target", intents[0])
        self.assertIn("chord_rhythm_target", intents[0])

    def test_role_aware_end_targets(self) -> None:
        from composition.section_planner import _make_timeline_targets

        curve = {
            "melody_density_mult": 1.0,
            "chord_rhythm_mult": 1.0,
            "motif_prob_mult": 1.0,
        }
        pre = _make_timeline_targets("pre_chorus", 8, dict(curve))
        chorus = _make_timeline_targets("b", 8, dict(curve))

        pre_funcs = list(pre.get("harmony_function_target_by_bar", []) or [])
        chor_funcs = list(chorus.get("harmony_function_target_by_bar", []) or [])

        self.assertEqual(str(pre_funcs[-1]), "D")
        self.assertEqual(str(chor_funcs[-1]), "T")


if __name__ == "__main__":
    unittest.main()

