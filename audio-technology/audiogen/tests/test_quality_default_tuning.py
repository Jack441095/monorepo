import unittest


class QualityDefaultTuningTests(unittest.TestCase):
    def test_new_quality_defaults_are_present(self) -> None:
        from audiogen_core.config import CONFIG

        c = CONFIG.composition
        self.assertTrue(hasattr(c, "melody_listener_memory_scorer_enabled"))
        self.assertTrue(hasattr(c, "melody_listener_memory_scorer_strength"))
        self.assertTrue(hasattr(c, "timeline_role_contrast_enabled"))
        self.assertTrue(hasattr(c, "pop_arrangement_strength"))
        self.assertTrue(hasattr(c, "pop_hook_scoring_strength"))
        self.assertTrue(hasattr(c, "timeline_phrase_targets_enabled"))
        self.assertTrue(hasattr(c, "hook_development"))
        self.assertTrue(hasattr(c, "whole_song_director_enabled"))
        self.assertTrue(hasattr(c, "whole_song_chorus_hook_memory_enabled"))
        self.assertTrue(hasattr(c, "transition_arrangement_gestures_enabled"))
        self.assertTrue(hasattr(c, "transition_arrangement_gestures_strength"))
        self.assertTrue(hasattr(c, "phrase_vocal_grammar_enabled"))
        self.assertTrue(hasattr(c, "post_generation_qa_enabled"))
        self.assertTrue(hasattr(c, "hook_strength_qa_enabled"))
        self.assertTrue(hasattr(c, "arrangement_collision_manager_enabled"))
        self.assertTrue(hasattr(c, "section_contrast_qa_enabled"))
        self.assertTrue(hasattr(c, "emotion_bass_personality_enabled"))

    def test_quality_defaults_stay_in_safe_ranges(self) -> None:
        from audiogen_core.config import CONFIG

        c = CONFIG.composition
        self.assertGreaterEqual(float(c.texture_drop_strength), 0.0)
        self.assertLessEqual(float(c.texture_drop_strength), 1.0)
        self.assertGreaterEqual(float(c.texture_register_lift_strength), 0.0)
        self.assertLessEqual(float(c.texture_register_lift_strength), 1.0)
        self.assertGreaterEqual(float(c.texture_fx_gesture_strength), 0.0)
        self.assertLessEqual(float(c.texture_fx_gesture_strength), 1.0)
        self.assertGreaterEqual(int(c.transition_bridge_hold_bars), 1)
        self.assertLessEqual(float(c.melody_listener_memory_scorer_strength), 1.0)
        self.assertGreaterEqual(float(c.whole_song_director_strength), 0.0)
        self.assertLessEqual(float(c.whole_song_director_strength), 1.0)
        self.assertGreaterEqual(float(c.whole_song_chorus_hook_memory_strength), 0.0)
        self.assertLessEqual(float(c.whole_song_chorus_hook_memory_strength), 1.0)
        self.assertGreaterEqual(float(c.transition_arrangement_gestures_strength), 0.0)
        self.assertLessEqual(float(c.transition_arrangement_gestures_strength), 1.0)
        self.assertGreaterEqual(float(c.phrase_vocal_grammar_strength), 0.0)
        self.assertLessEqual(float(c.phrase_vocal_grammar_strength), 1.0)
        self.assertGreaterEqual(float(c.post_generation_qa_strength), 0.0)
        self.assertLessEqual(float(c.post_generation_qa_strength), 1.0)
        self.assertGreaterEqual(float(c.hook_strength_qa_strength), 0.0)
        self.assertLessEqual(float(c.hook_strength_qa_strength), 1.0)
        self.assertGreaterEqual(float(c.arrangement_collision_manager_strength), 0.0)
        self.assertLessEqual(float(c.arrangement_collision_manager_strength), 1.0)
        self.assertGreaterEqual(float(c.section_contrast_qa_strength), 0.0)
        self.assertLessEqual(float(c.section_contrast_qa_strength), 1.0)
        self.assertGreaterEqual(float(c.emotion_bass_personality_strength), 0.0)
        self.assertLessEqual(float(c.emotion_bass_personality_strength), 1.0)
        self.assertGreaterEqual(float(c.pop_arrangement_strength), 0.0)
        self.assertLessEqual(float(c.pop_arrangement_strength), 1.0)
        self.assertGreaterEqual(float(c.pop_hook_scoring_strength), 0.0)
        self.assertLessEqual(float(c.pop_hook_scoring_strength), 1.0)

    def test_conversation_default_is_layered_ost_baseline(self) -> None:
        """Fresh ConfigurationManager loads ``default_ambient_01`` (default pack + layered preset)."""
        from audiogen_core.config import ConfigurationManager

        cm = ConfigurationManager()
        self.assertEqual(cm.active_conversation_preset, "default_ambient_01")
        self.assertEqual(cm.active_sample_pack, "default")
        self.assertEqual(float(cm.composition.default_tempo), 70.0)
        self.assertEqual(str(cm.composition.melody_harmony_agreement_preset), "tight")
        self.assertTrue(bool(cm.composition.arp_chord_harmonic_rhythm_shared_enabled))


if __name__ == "__main__":
    unittest.main()
