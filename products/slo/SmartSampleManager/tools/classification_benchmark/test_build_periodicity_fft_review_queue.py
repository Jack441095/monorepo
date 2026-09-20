import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("build_periodicity_fft_review_queue.py")
SPEC = importlib.util.spec_from_file_location("build_periodicity_fft_review_queue", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class BuildPeriodicityFftReviewQueueTests(unittest.TestCase):
    def test_periodicity_work_is_bounded(self):
        self.assertEqual(MODULE.MAX_PERIODICITY_SECONDS, 30.0)

    def test_candidate_queue_rejects_mutating_receipts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queue.json"
            path.write_text('{"record_type":"slo_fft_evidence_review_queue",'
                            '"safety":{"read_only":false},"rows":[]}', encoding="utf-8")
            with self.assertRaises(ValueError):
                MODULE._candidate_rows(path)

    def test_fft_matrix_skips_unresolved_and_nonfinite_rows(self):
        rows = [
            {"fft_status": "computed", "fft_evidence": {"a": 1.0, "b": 2.0}},
            {"fft_status": "unresolved_local_audio", "fft_evidence": {}},
            {"fft_status": "computed", "fft_evidence": {"a": float("nan"), "b": 2.0}},
        ]
        matrix, kept = MODULE._fft_matrix(rows, ["a", "b"])
        self.assertEqual(matrix.shape, (1, 2))
        self.assertEqual(len(kept), 1)
        self.assertEqual(float(matrix[0, 1]), 2.0)


if __name__ == "__main__":
    unittest.main()
