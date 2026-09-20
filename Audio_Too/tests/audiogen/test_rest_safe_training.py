import random
import unittest


class RestSafeTrainingTests(unittest.TestCase):
    def test_melody_interval_steps_rest_safe_skips_rests(self):
        from ai.markov.melody.generator import MelodyGenerator

        mel = [(0, 1.0), (-1, 0.5), (3, 1.0)]
        self.assertEqual(MelodyGenerator._melody_interval_steps(mel, True), [3])
        self.assertEqual(len(MelodyGenerator._melody_interval_steps(mel, False)), 2)

    def test_signed_rhythm_tokens_in_training_vocab(self):
        from audiogen_core.config import CONFIG
        from ai.markov.melody.generator import MelodyGenerator

        prev = bool(getattr(CONFIG.composition, "melody_rest_rhythm_tokens_train_enabled", False))
        try:
            CONFIG.composition.melody_rest_rhythm_tokens_train_enabled = True
            g = MelodyGenerator(rng=__import__("random").Random(0))
            g.train_from_melodies(
                [[(0, 0.5), (-1, 0.25), (2, 1.0)]],
                emotion_name="neutral",
            )
            vocab = list(getattr(g.markov.rhythm, "_vocab_list", []) or [])
            self.assertTrue(any(float(x) < 0 for x in vocab))
        finally:
            CONFIG.composition.melody_rest_rhythm_tokens_train_enabled = prev

    def test_prev_duration_bucket_interval_sequences(self):
        from ai.markov.melody.generator import MelodyGenerator
        from ai.markov.melody.ensemble.bucketing import prev_note_duration_bucket

        mel = [(0, 0.25), (2, 1.0), (4, 0.5)]
        per = MelodyGenerator._interval_sequences_by_prev_duration_bucket(mel, True)
        self.assertEqual(prev_note_duration_bucket(0.25), 0)
        self.assertIn(2, per[0])
        self.assertIn(2, per[prev_note_duration_bucket(1.0)])

    def test_phrase_gesture_interval_sequences(self):
        from ai.markov.melody.generator import MelodyGenerator

        # Seven voiced notes → six intervals; pos=j/5 → two per gesture bucket.
        mel = [(i % 7, 0.5) for i in range(7)]
        per = MelodyGenerator._interval_sequences_by_phrase_gesture(mel, True)
        self.assertEqual(len(per["opening"]), 2)
        self.assertEqual(len(per["middle"]), 2)
        self.assertEqual(len(per["cadence"]), 2)

    def test_train_gesture_interval_models_populates_vocab(self):
        from audiogen_core.config import CONFIG
        from ai.markov.melody.generator import MelodyGenerator

        prev = bool(getattr(CONFIG.composition, "melody_train_gesture_interval_models", False))
        try:
            CONFIG.composition.melody_train_gesture_interval_models = True
            g = MelodyGenerator(rng=random.Random(0))
            g.train_from_melodies(
                [
                    [(0, 0.5), (1, 0.5), (2, 0.5), (3, 0.5), (4, 0.5)],
                    [(3, 0.5), (2, 0.5), (1, 0.5), (0, 0.5)],
                ],
                emotion_name="neutral",
            )
            nonempty = 0
            for key in ("opening", "middle", "cadence"):
                if len(getattr(g.markov.gesture_interval_models[key], "_vocab_list", []) or []) > 0:
                    nonempty += 1
            self.assertGreater(nonempty, 0)
        finally:
            CONFIG.composition.melody_train_gesture_interval_models = prev

    def test_melody_interval_steps_empty_when_single_voiced(self):
        from ai.markov.melody.generator import MelodyGenerator

        mel = [(-1, 1.0), (0, 1.0), (-1, 1.0)]
        self.assertEqual(MelodyGenerator._melody_interval_steps(mel, True), [])

    def test_apply_staged_bundle_sets_flags(self):
        from audiogen_core.composition_config import CompositionConfiguration, apply_melody_staged_experimental_bundle

        c = CompositionConfiguration()
        c.melody_joint_rhythm_pitch_rerank_k = 0
        c.melody_staged_experimental_bundle_enabled = True
        apply_melody_staged_experimental_bundle(c)
        self.assertTrue(c.melody_rhythm_pitch_coupling_enabled)
        self.assertTrue(c.melody_interval_duration_coupling_enabled)
        self.assertTrue(c.melody_joint_rhythm_pitch_rerank_enabled)
        self.assertEqual(c.melody_joint_rhythm_pitch_rerank_k, 8)
        self.assertTrue(c.melody_breath_rest_bias_enabled)
        self.assertTrue(c.melody_breath_rhythm_bias_enabled)

    def test_train_from_melodies_with_rest_does_not_crash(self):
        from ai.markov.melody.generator import MelodyGenerator

        g = MelodyGenerator(rng=random.Random(42))
        g.train_from_melodies(
            [
                [(0, 0.5), (-1, 0.5), (2, 0.5), (3, 0.5)],
                [(1, 1.0), (2, 1.0)],
            ],
            emotion_name="neutral",
        )
        self.assertTrue(len(g.markov.interval._vocab_list) > 0)

    def test_chord_conditioned_training_with_rests_uses_voiced_pairs(self):
        from ai.markov.melody.generator import MelodyGenerator

        g = MelodyGenerator(rng=random.Random(1), use_chord_conditioned_markov=True)
        mel = [(0, 0.5), (-1, 0.5), (4, 0.5), (5, 0.5)]
        chords = ["I", "I", "I", "I"]
        g.train_from_melodies([mel], emotion_name="neutral", chord_sequences=[chords])
        self.assertTrue(len(g.markov.interval._vocab_list) > 0)

    def test_generate_phrase_smoke_with_staged_bundle(self):
        from audiogen_core.composition_config import apply_melody_staged_experimental_bundle
        from audiogen_core.config import CONFIG
        from ai.markov.melody.generator import MelodyGenerator
        from data.music_data import EMOTIONS

        snap = {
            "melody_staged_experimental_bundle_enabled": getattr(
                CONFIG.composition, "melody_staged_experimental_bundle_enabled", False
            ),
            "melody_rhythm_pitch_coupling_enabled": getattr(
                CONFIG.composition, "melody_rhythm_pitch_coupling_enabled", False
            ),
            "melody_interval_duration_coupling_enabled": getattr(
                CONFIG.composition, "melody_interval_duration_coupling_enabled", False
            ),
            "melody_joint_rhythm_pitch_rerank_enabled": getattr(
                CONFIG.composition, "melody_joint_rhythm_pitch_rerank_enabled", False
            ),
            "melody_joint_rhythm_pitch_rerank_k": getattr(
                CONFIG.composition, "melody_joint_rhythm_pitch_rerank_k", 0
            ),
            "melody_breath_rest_bias_enabled": getattr(
                CONFIG.composition, "melody_breath_rest_bias_enabled", False
            ),
            "melody_breath_rhythm_bias_enabled": getattr(
                CONFIG.composition, "melody_breath_rhythm_bias_enabled", False
            ),
        }
        try:
            CONFIG.composition.melody_staged_experimental_bundle_enabled = True
            apply_melody_staged_experimental_bundle(CONFIG.composition)

            rng = random.Random(0)
            g = MelodyGenerator(rng=rng)
            g.train_from_melodies(
                [[(0, 0.5), (1, 0.5), (2, 0.5), (1, 0.5), (0, 0.5)]],
                emotion_name="neutral",
            )
            emotion = next(e for e in EMOTIONS if getattr(e, "name", "").lower() == "neutral")

            from ai.markov.melody.phrase_planner import PhrasePlan

            plan = PhrasePlan(contour="asc", phrase_role="opening", section_role="a")

            m, _, _ = g.note_gen.generate_phrase(
                start_degree=0,
                num_notes=6,
                plan=plan,
                temperature=1.0,
                emotion=emotion,
                start_beat=0.0,
                chords=["I"] * 32,
                roots=[60] * 32,
                beats_per_bar=4.0,
                chord_weights_per_bar=[{0: 1.0, 2: 1.0, 4: 1.0}] * 32,
                beat_positions_out=[],
                grid=0.25,
                initial_interval_context=None,
                initial_rhythm_context=None,
                bass_notes=None,
                total_beats=64,
                target_melody_notes=None,
                breath_window_by_bar=[0.0] * 32,
            )
            self.assertEqual(len(m), 6)
        finally:
            for k, v in snap.items():
                setattr(CONFIG.composition, k, v)


if __name__ == "__main__":
    unittest.main()
