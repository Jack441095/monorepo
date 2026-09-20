import unittest


class PhraseFunctionScaffoldingTests(unittest.TestCase):
    def test_target_function_bias_prefers_dominant_in_prechorus_cadence(self):
        from composition.engine import CompositionGenerator

        gen = CompositionGenerator(enable_perf_monitoring=False)
        cp = gen.chord_planner

        simplified_vocab = ["maj", "min", "dom", "dim", "sus"]
        symbols, weights = cp.build_chord_candidate_weights(
            markov_probs={},
            simplified_vocab=simplified_vocab,
            history=["maj"],
            repeat_penalty=0.2,
            bar_in_phrase=3,
            phrase_length=4,
            emotion_name="neutral",
            section_role="pre_chorus",
            bar_index=3,
            total_bars=16,
            target_function="D",
            target_function_strength=1.0,
        )
        w = {s: float(v) for s, v in zip(symbols, weights)}
        self.assertGreater(w.get("dom", 0.0), w.get("maj", 0.0))


if __name__ == "__main__":
    unittest.main()

