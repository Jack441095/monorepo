import importlib.util
import tempfile
import unittest
from pathlib import Path

import numpy as np


SCRIPT = Path(__file__).with_name("periodicity_fft_physics_benchmark.py")
SPEC = importlib.util.spec_from_file_location("periodicity_fft_physics_benchmark", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class PeriodicityFftPhysicsBenchmarkTests(unittest.TestCase):
    def test_named_cache_alignment_is_path_based(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "physics.npz"
            np.savez(
                cache,
                paths=np.asarray(["/tmp/b.wav", "/tmp/a.wav"], dtype=object),
                names=np.asarray(["x", "y"], dtype=object),
                F=np.asarray([[2.0, 3.0], [4.0, 5.0]], dtype=np.float32),
            )
            values = MODULE._load_named(cache, ["/tmp/a.wav", "/tmp/b.wav"], ("y",), "F")
            np.testing.assert_array_equal(values[:, 0], np.asarray([5.0, 3.0]))

    def test_metrics_use_loop_as_positive_class(self):
        y = np.asarray([0, 0, 1, 1])
        pred = np.asarray([0, 1, 1, 1])
        metrics = MODULE._metrics(y, pred)
        self.assertEqual(metrics["accuracy"], 75.0)
        self.assertEqual(metrics["loop_precision"], 66.667)
        self.assertEqual(metrics["loop_recall"], 100.0)


if __name__ == "__main__":
    unittest.main()
