"""Async retrained-melody-Markov load (docs/AUDIOGEN_COMPOSITION_PLAN.md startup-latency).

When `melody_retrained_markov_async_load` is on, the ~196MB bundle loads on a background
thread so CompositionGenerator construction doesn't block ~6s. The first sections use the
default melody path and upgrade once the load lands. Skips if the model file isn't present.
"""
import time
import unittest


class TestAsyncMarkovLoad(unittest.TestCase):
    def setUp(self):
        from audiogen_core.config import CONFIG

        self._enabled = CONFIG.composition.melody_retrained_markov_enabled
        self._async = getattr(CONFIG.composition, "melody_retrained_markov_async_load", False)
        CONFIG.composition.melody_retrained_markov_enabled = True
        CONFIG.composition.melody_retrained_markov_async_load = True

    def tearDown(self):
        from audiogen_core.config import CONFIG

        CONFIG.composition.melody_retrained_markov_enabled = self._enabled
        CONFIG.composition.melody_retrained_markov_async_load = self._async

    def test_construction_does_not_block_and_first_section_is_varied(self):
        """Environment-independent core contract: async construction is fast and generating
        immediately (before/without the model) still yields a varied melody, never a crash
        or degenerate output."""
        from composition.engine import CompositionGenerator
        from data.music_data import EMOTION_BY_NAME

        t0 = time.perf_counter()
        gen = CompositionGenerator(enable_perf_monitoring=False)
        ctor_s = time.perf_counter() - t0
        # construction must not block on the ~6s load regardless of whether the file exists
        self.assertLess(ctor_s, 2.0, f"async construction should be fast, took {ctor_s:.2f}s")

        ev = gen.generate_section(EMOTION_BY_NAME["joy"], root_note=60, bars=4,
                                  temperature=0.6, target_notes_per_bar=4.0, melody_style="auto")
        mel_pitches = {e[1] for e in ev if e[0] == 2 and e[1] > 0}
        self.assertGreaterEqual(len(mel_pitches), 4, "first section should still be a varied melody")

    def test_model_upgrades_after_async_load(self):
        """When the model file is actually loadable in this environment, the retrained model
        binds on a later section after the background load completes. Skips otherwise (the
        path resolves relative to CWD, which varies by how the suite is invoked)."""
        from composition.engine import CompositionGenerator
        from data.music_data import EMOTION_BY_NAME

        gen = CompositionGenerator(enable_perf_monitoring=False)
        th = getattr(gen, "_melody_markov_async_load_thread", None)
        if th is not None:
            th.join(timeout=30)
        if not getattr(gen, "_retrained_melody_markov_emotion_models", None):
            self.skipTest("retrained melody model not loadable in this environment (CWD-relative path)")
        gen.generate_section(EMOTION_BY_NAME["joy"], root_note=60, bars=4,
                             temperature=0.6, target_notes_per_bar=4.0, melody_style="auto", section_index=1)
        self.assertIsNotNone(getattr(gen, "_retrained_melody_markov_current_model", None),
                             "retrained model should bind after async load completes")


if __name__ == "__main__":
    unittest.main()
