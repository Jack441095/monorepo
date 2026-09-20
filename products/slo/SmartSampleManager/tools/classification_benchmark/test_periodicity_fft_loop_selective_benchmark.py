import importlib.util
import unittest
from pathlib import Path

import numpy as np


SCRIPT = Path(__file__).with_name("periodicity_fft_loop_selective_benchmark.py")
SPEC = importlib.util.spec_from_file_location("periodicity_fft_loop_selective_benchmark", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class PeriodicityFftLoopSelectiveTests(unittest.TestCase):
    def test_threshold_is_selected_without_using_test_predictions(self):
        confidence = np.linspace(0.99, 0.50, 100)
        correct = np.ones(100, dtype=bool)
        threshold = MODULE._select_threshold(confidence, correct, 0.90, 2)
        self.assertEqual(threshold, 0.5)

    def test_wilson_lower_bound_is_conservative(self):
        self.assertGreater(MODULE._wilson_lower(100, 100), 0.95)
        self.assertLess(MODULE._wilson_lower(9, 10), 0.95)

    def test_deferred_metrics_are_explicit(self):
        y = np.asarray([0, 0, 1, 1])
        pred = np.asarray([0, 1, 1, 1])
        confidence = np.asarray([0.95, 0.95, 0.80, 0.40])
        metrics = MODULE._selective_metrics(y, pred, confidence, 0.9, 0.9)
        self.assertEqual(metrics["accepted"], 2)
        self.assertEqual(metrics["deferred"], 2)
        self.assertEqual(metrics["coverage"], 50.0)
        self.assertEqual(metrics["accepted_precision"], 50.0)


if __name__ == "__main__":
    unittest.main()
