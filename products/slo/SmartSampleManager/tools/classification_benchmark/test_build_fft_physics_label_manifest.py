import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("build_fft_physics_label_manifest.py")
SPEC = importlib.util.spec_from_file_location("build_fft_physics_label_manifest", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class BuildFftPhysicsLabelManifestTests(unittest.TestCase):
    def test_bucket_classification_is_evidence_only(self):
        row = {"form_evidence": "loop_temporal_evidence",
               "physics_candidate_lanes": ["transient_decay_evidence"]}
        self.assertEqual(MODULE._bucket(row), "evidence_disagreement")

    def test_input_queue_requires_review_only_safety(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queue.json"
            path.write_text(json.dumps({
                "record_type": "slo_physics_review_queue",
                "safety": {"read_only": False}, "rows": [],
            }), encoding="utf-8")
            with self.assertRaises(ValueError):
                MODULE._read_queue(path)

    def test_exclude_csv_paths_are_removed_before_sampling(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root / "a.wav"
            audio.write_bytes(b"a")
            queue = root / "queue.json"
            queue.write_text(json.dumps({
                "record_type": "slo_physics_review_queue",
                "safety": {"read_only": True, "semantic_labels_created": False,
                            "rename_actions": False, "auto_action_allowed": False},
                "rows": [{"fft_local_path": str(audio), "content_sha256": "a" * 64,
                          "form_evidence": "", "physics_candidate_lanes": []}],
            }), encoding="utf-8")
            excluded = root / "known.csv"
            excluded.write_text(f"path,label\n{audio},Kick\n", encoding="utf-8")
            out_json, out_csv = root / "out.json", root / "out.csv"
            payload = MODULE.build_manifest(queue, out_json, out_csv, 1, 42, [excluded])
            self.assertEqual(payload["n_selected"], 0)
            self.assertEqual(payload["known_label_path_excluded"], 1)


if __name__ == "__main__":
    unittest.main()
