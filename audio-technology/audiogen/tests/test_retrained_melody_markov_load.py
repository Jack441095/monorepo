import pickle
import tempfile
import unittest
from pathlib import Path


class RetrainedMelodyMarkovLoadTests(unittest.TestCase):
    def test_loads_retrained_markov_pickle_when_enabled(self) -> None:
        from ai.markov.melody.ensemble import MarkovModelSet
        from composition.engine import CompositionGenerator
        from audiogen_core.config import CONFIG

        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "melody_markov_retrained.pkl"
            custom = MarkovModelSet(interval_order=2, rhythm_order=2, phrase_order=1, smoothing=0.02)
            with p.open("wb") as f:
                pickle.dump(custom, f, protocol=pickle.HIGHEST_PROTOCOL)

            prev_enabled = bool(getattr(CONFIG.composition, "melody_retrained_markov_enabled", False))
            prev_path = str(getattr(CONFIG.composition, "melody_retrained_markov_path", "") or "")
            try:
                CONFIG.composition.melody_retrained_markov_enabled = True
                CONFIG.composition.melody_retrained_markov_path = str(p)
                gen = CompositionGenerator(enable_perf_monitoring=False)
                self.assertEqual(int(gen.melody_gen.markov.interval.order), 2)
                self.assertEqual(int(gen.melody_gen.markov.rhythm.order), 2)
                self.assertEqual(int(gen.melody_gen.markov.phrase.order), 1)
            finally:
                CONFIG.composition.melody_retrained_markov_enabled = prev_enabled
                CONFIG.composition.melody_retrained_markov_path = prev_path

    def test_invalid_pickle_type_falls_back_to_default_markov(self) -> None:
        from composition.engine import CompositionGenerator
        from audiogen_core.config import CONFIG

        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad_retrained.pkl"
            with p.open("wb") as f:
                pickle.dump({"not": "a markov model"}, f, protocol=pickle.HIGHEST_PROTOCOL)

            prev_enabled = bool(getattr(CONFIG.composition, "melody_retrained_markov_enabled", False))
            prev_path = str(getattr(CONFIG.composition, "melody_retrained_markov_path", "") or "")
            try:
                CONFIG.composition.melody_retrained_markov_enabled = True
                CONFIG.composition.melody_retrained_markov_path = str(p)
                gen = CompositionGenerator(enable_perf_monitoring=False)
                # Default runtime melody interval order in CompositionGenerator is 6.
                self.assertEqual(int(gen.melody_gen.markov.interval.order), 6)
            finally:
                CONFIG.composition.melody_retrained_markov_enabled = prev_enabled
                CONFIG.composition.melody_retrained_markov_path = prev_path

    def test_hot_reload_updates_markov_when_pickle_mtime_changes(self) -> None:
        from ai.markov.melody.ensemble import MarkovModelSet
        from composition.engine import CompositionGenerator
        from audiogen_core.config import CONFIG

        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "melody_markov_retrained.pkl"
            first = MarkovModelSet(interval_order=2, rhythm_order=2, phrase_order=1, smoothing=0.02)
            second = MarkovModelSet(interval_order=4, rhythm_order=4, phrase_order=2, smoothing=0.02)
            with p.open("wb") as f:
                pickle.dump(first, f, protocol=pickle.HIGHEST_PROTOCOL)

            prev_enabled = bool(getattr(CONFIG.composition, "melody_retrained_markov_enabled", False))
            prev_path = str(getattr(CONFIG.composition, "melody_retrained_markov_path", "") or "")
            prev_hot = bool(getattr(CONFIG.composition, "melody_retrained_markov_hot_reload_enabled", False))
            prev_iv = float(
                getattr(CONFIG.composition, "melody_retrained_markov_hot_reload_interval_seconds", 2.0) or 2.0
            )
            try:
                CONFIG.composition.melody_retrained_markov_enabled = True
                CONFIG.composition.melody_retrained_markov_path = str(p)
                CONFIG.composition.melody_retrained_markov_hot_reload_enabled = True
                CONFIG.composition.melody_retrained_markov_hot_reload_interval_seconds = 0.05

                gen = CompositionGenerator(enable_perf_monitoring=False)
                self.assertEqual(int(gen.melody_gen.markov.interval.order), 2)

                with p.open("wb") as f:
                    pickle.dump(second, f, protocol=pickle.HIGHEST_PROTOCOL)
                # Bypass check interval for deterministic test timing.
                gen._retrained_melody_markov_next_check_monotonic = 0.0
                gen._try_load_retrained_melody_markov(hot_reload=True)

                self.assertEqual(int(gen.melody_gen.markov.interval.order), 4)
                self.assertEqual(int(gen.melody_gen.markov.rhythm.order), 4)
            finally:
                CONFIG.composition.melody_retrained_markov_enabled = prev_enabled
                CONFIG.composition.melody_retrained_markov_path = prev_path
                CONFIG.composition.melody_retrained_markov_hot_reload_enabled = prev_hot
                CONFIG.composition.melody_retrained_markov_hot_reload_interval_seconds = prev_iv

    def test_loads_retrained_markov_bundle_and_selects_by_emotion(self) -> None:
        from ai.markov.melody.ensemble import MarkovModelSet
        from composition.engine import CompositionGenerator
        from audiogen_core.config import CONFIG
        from data.music_data import EMOTION_BY_NAME

        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "melody_markov_bundle.pkl"
            global_model = MarkovModelSet(interval_order=2, rhythm_order=2, phrase_order=1, smoothing=0.02)
            joy_model = MarkovModelSet(interval_order=3, rhythm_order=3, phrase_order=1, smoothing=0.02)
            grief_family_model = MarkovModelSet(interval_order=5, rhythm_order=5, phrase_order=2, smoothing=0.02)
            bundle = {
                "kind": "melody_markov_bundle",
                "version": 1,
                "global": global_model,
                "emotion_models": {"joy": joy_model},
                "family_models": {"sad": grief_family_model},
                "metadata": {},
            }
            with p.open("wb") as f:
                pickle.dump(bundle, f, protocol=pickle.HIGHEST_PROTOCOL)

            prev_enabled = bool(getattr(CONFIG.composition, "melody_retrained_markov_enabled", False))
            prev_path = str(getattr(CONFIG.composition, "melody_retrained_markov_path", "") or "")
            try:
                CONFIG.composition.melody_retrained_markov_enabled = True
                CONFIG.composition.melody_retrained_markov_path = str(p)
                gen = CompositionGenerator(enable_perf_monitoring=False)
                self.assertEqual(int(gen.melody_gen.markov.interval.order), 2)
                gen._apply_retrained_melody_markov_for_emotion(EMOTION_BY_NAME["joy"])
                self.assertEqual(int(gen.melody_gen.markov.interval.order), 3)
                gen._apply_retrained_melody_markov_for_emotion(EMOTION_BY_NAME["grief"])
                self.assertEqual(int(gen.melody_gen.markov.interval.order), 5)
            finally:
                CONFIG.composition.melody_retrained_markov_enabled = prev_enabled
                CONFIG.composition.melody_retrained_markov_path = prev_path


if __name__ == "__main__":
    unittest.main()
