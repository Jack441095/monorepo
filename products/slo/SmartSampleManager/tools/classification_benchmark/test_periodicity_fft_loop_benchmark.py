import importlib.util
import tempfile
import unittest
from pathlib import Path

import numpy as np


SCRIPT = Path(__file__).with_name("periodicity_fft_loop_benchmark.py")
SPEC = importlib.util.spec_from_file_location("periodicity_fft_loop_benchmark", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class PeriodicityFftLoopBenchmarkTests(unittest.TestCase):
    def test_periodicity_loader_selects_named_columns(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "periodicity.npz"
            paths = np.asarray(["/tmp/a.wav", "/tmp/b.wav"], dtype=object)
            names = np.asarray([
                "dur", "sustain", "ac_peak", "ac_lag_s", "ac_ratio",
                "recur", "splice", "onsets", "tempo_conf",
            ], dtype=object)
            X = np.arange(18, dtype=np.float32).reshape(2, 9)
            np.savez(cache, X=X, paths=paths, names=names)
            selected = MODULE._load_periodicity(cache, paths.tolist())
            self.assertEqual(selected.shape, (2, 7))
            np.testing.assert_array_equal(selected[0], X[0, [0, 1, 2, 4, 5, 7, 8]])

    def test_metrics_are_percentages(self):
        y = np.asarray([0, 0, 1, 1])
        pred = np.asarray([0, 1, 1, 1])
        metrics = MODULE._metrics(y, pred)
        self.assertEqual(metrics["accuracy"], 75.0)
        self.assertEqual(metrics["loop_precision"], 66.667)
        self.assertEqual(metrics["loop_recall"], 100.0)

    def test_rows_deduplicate_and_reject_conflicts(self):
        with tempfile.TemporaryDirectory() as directory:
            labels = Path(directory) / "labels.csv"
            audio = Path(directory) / "a.wav"
            audio.write_bytes(b"placeholder")
            labels.write_text("path,label\n%s,Kick\n%s,Kick\n" % (audio, audio), encoding="utf-8")
            self.assertEqual(MODULE._rows(labels), [(str(audio), 0)])
            labels.write_text("path,label\n%s,Kick\n%s,Loop\n" % (audio, audio), encoding="utf-8")
            with self.assertRaises(ValueError):
                MODULE._rows(labels)


if __name__ == "__main__":
    unittest.main()
