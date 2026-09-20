import pickle
import random
import unittest


class MarkovEnsembleTests(unittest.TestCase):
    def test_markov_models_module_alias_for_pickle(self) -> None:
        import ai.markov.melody.ensemble  # noqa: F401 — registers stub

        from ai.markov.melody.ensemble import MarkovModelSet

        self.assertIs(
            MarkovModelSet,
            __import__("ai.markov.melody.markov_models", fromlist=["*"]).MarkovModelSet,
        )
        raw = pickle.dumps(MarkovModelSet(interval_order=2, rhythm_order=2, phrase_order=1))
        pickle.loads(raw)

    def test_train_intervals_and_rhythms(self) -> None:
        from ai.markov.melody.ensemble import MarkovModelSet

        m = MarkovModelSet(
            interval_order=2,
            rhythm_order=2,
            phrase_order=1,
            rng=random.Random(0),
        )
        m.train_intervals_and_rhythms(
            interval_sequences=[[1, 2, 1], [2, -1, 2]],
            rhythm_sequences=[[1.0, 0.5, 1.0], [0.5, 1.0, 0.5]],
        )
        ip = m.get_interval_probs([1], temperature=1.0)
        rp = m.get_rhythm_probs([1.0], temperature=1.0)
        self.assertGreater(len(ip), 0)
        self.assertGreater(len(rp), 0)


if __name__ == "__main__":
    unittest.main()
