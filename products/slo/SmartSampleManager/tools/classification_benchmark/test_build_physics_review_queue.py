import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("build_physics_review_queue.py")
SPEC = importlib.util.spec_from_file_location("build_physics_review_queue", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class BuildPhysicsReviewQueueTests(unittest.TestCase):
    def test_mutating_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "queue.json"
            source.write_text(json.dumps({
                "record_type": "slo_fft_evidence_review_queue",
                "safety": {"read_only": False}, "rows": [{"path": "/tmp/a.wav"}],
            }), encoding="utf-8")
            with self.assertRaises(ValueError):
                MODULE._read_queue(source)

    def test_physics_lanes_are_evidence_only(self):
        evidence = {
            "repetition_score": 0.2, "third_onset_cv": 0.4,
            "full_decay_s": 0.6, "full_transient": 1.0,
            "full_hf_density": 0.5,
        }
        self.assertEqual(MODULE._physics_lanes(evidence), [
            "repeating_temporal_evidence", "high_frequency_evidence",
        ])


if __name__ == "__main__":
    unittest.main()
