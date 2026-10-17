import unittest


class TempoClampTuningTests(unittest.TestCase):
    def test_effective_tempo_clamps_extreme_emotion_multipliers(self) -> None:
        from audiogen_core.config import effective_tempo_bpm_from_config, CONFIG
        from data.music_data import EMOTION_BY_NAME

        base = float(CONFIG.composition.default_tempo) * float(CONFIG.composition.global_tempo_scale)
        grief = effective_tempo_bpm_from_config(CONFIG, EMOTION_BY_NAME["grief"])
        excitement = effective_tempo_bpm_from_config(CONFIG, EMOTION_BY_NAME["excitement"])

        self.assertGreaterEqual(grief, base * 0.55)
        self.assertLessEqual(excitement, base * 1.55)

    def test_song_form_duration_uses_clamped_tempo_multiplier(self) -> None:
        from composition.song_generator import SongGenerator
        from data.audit import normalize_emotion_scalars
        from data.music_data import EMOTION_BY_NAME

        sadness_tempo, _, _ = normalize_emotion_scalars(EMOTION_BY_NAME["sadness"])
        specs = SongGenerator.pop_ext_form(
            "sadness",
            base_tempo_bpm=70.0,
            target_seconds=240.0,
            max_bars=96,
        )
        total_bars = sum(int(s.bars) for s in specs)
        expected = round(240.0 / (4.0 * 60.0 / (70.0 * sadness_tempo)))

        self.assertLess(abs(total_bars - expected), 16)


if __name__ == "__main__":
    unittest.main()
