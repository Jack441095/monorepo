import unittest


class MelodyDensityAndDurationBudgetTests(unittest.TestCase):
    def test_prepare_melody_parameters_respects_note_profile_floor(self) -> None:
        from composition.engine import CompositionGenerator
        from data.melody_note_profiles import melody_note_profile_for_emotion
        from data.music_data import EMOTION_BY_NAME

        gen = CompositionGenerator(enable_perf_monitoring=False, use_voice_leading=False)
        emotion = EMOTION_BY_NAME["admiration"]
        _contours, notes_per_phrase, _tm, _dm = gen.melody_runtime.prepare_melody_parameters(
            emotion,
            bars=4,
            temperature=1.0,
            target_notes_per_bar=6.0,
            section_role="intro",
        )
        floor = float(melody_note_profile_for_emotion("admiration")["min_notes_per_bar"]) * 0.88
        self.assertGreaterEqual(sum(notes_per_phrase), int(round(4 * floor)))

    def test_phrase_budget_caps_final_absorbing_duration(self) -> None:
        from ai.markov.melody.note_generator._core import NoteGenerator

        dur = NoteGenerator._fit_duration_to_phrase_budget(
            15.75,
            current_beat=0.25,
            phrase_end_beat=16.0,
            notes_done=1,
            num_notes=2,
            is_last_note=True,
        )
        self.assertLessEqual(dur, 2.0)

    def test_phrase_budget_raises_tiny_nonfinal_when_phrase_is_sparse(self) -> None:
        from ai.markov.melody.note_generator._core import NoteGenerator

        dur = NoteGenerator._fit_duration_to_phrase_budget(
            0.25,
            current_beat=0.0,
            phrase_end_beat=16.0,
            notes_done=0,
            num_notes=4,
            is_last_note=False,
        )
        self.assertGreaterEqual(dur, 1.0)


if __name__ == "__main__":
    unittest.main()
