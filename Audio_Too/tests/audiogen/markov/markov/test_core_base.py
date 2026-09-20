import pickle
import random
import unittest


class MarkovCoreBaseTests(unittest.TestCase):
    def test_chains_shim_matches_core(self) -> None:
        from ai.markov.chains.base import BaseMarkov as BaseShim
        from ai.markov.core.base import BaseMarkov as BaseCore

        self.assertIs(BaseShim, BaseCore)

    def test_train_and_get_probabilities(self) -> None:
        from ai.markov.core.base import BaseMarkov

        m = BaseMarkov(order=2, rng=random.Random(0))
        m.train([[1, 2, 3, 1], [2, 3, 1, 2]])
        p = m.get_probabilities([1, 2], temperature=1.0)
        self.assertGreater(len(p), 0)
        self.assertAlmostEqual(sum(p.values()), 1.0, places=5)

    def test_get_next_is_deterministic_with_seeded_rng(self) -> None:
        from ai.markov.core.base import BaseMarkov

        m = BaseMarkov(order=2, rng=random.Random(42))
        m.train([[10, 20, 30, 10]])
        a = m.get_next([10, 20], temperature=1.0)
        m2 = BaseMarkov(order=2, rng=random.Random(42))
        m2.train([[10, 20, 30, 10]])
        b = m2.get_next([10, 20], temperature=1.0)
        self.assertEqual(a, b)

    def test_pickle_roundtrip(self) -> None:
        from ai.markov.core.base import BaseMarkov

        m = BaseMarkov(order=2, rng=random.Random(0))
        m.train([[1, 2, 3], [2, 3, 4]])
        raw = pickle.dumps(m)
        m2 = pickle.loads(raw)
        self.assertEqual(m2.order, m.order)
        self.assertEqual(m2.smoothing, m.smoothing)
        p = m2.get_probabilities([1, 2], temperature=1.0)
        self.assertGreater(len(p), 0)

    def test_interval_and_rhythm_markov_smoke(self) -> None:
        from ai.markov.core.models import IntervalMarkov, RhythmMarkov

        im = IntervalMarkov(order=2, rng=random.Random(0))
        im.train([[1, 2], [2, -1]])
        self.assertGreater(len(im.get_probabilities([1], temperature=1.0)), 0)

        rm = RhythmMarkov(order=2, rng=random.Random(0))
        rm.train([[1.0, 0.5], [0.5, 1.0]])
        self.assertGreater(len(rm.get_probabilities([1.0], temperature=1.0)), 0)


if __name__ == "__main__":
    unittest.main()
