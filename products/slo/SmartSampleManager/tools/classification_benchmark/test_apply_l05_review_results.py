import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("apply_l05_review_results.py")
SPEC = importlib.util.spec_from_file_location("apply_l05_review_results", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ApplyL05ReviewResultsTests(unittest.TestCase):
    def _inputs(self, directory: Path):
        manifest = directory / "manifest.json"
        manifest.write_text(json.dumps([{
            "filename": "kick.wav",
            "local_relative_path": "fixtures/kick.wav",
            "source_path": "/private/kick.wav",
            "sha256": "a" * 64,
            "expected_subcategory": "Kick",
        }]), encoding="utf-8")
        results = directory / "results.csv"
        fields = [
            "review_id", "source_path", "source_sha256",
            "reviewer_1_id", "reviewer_1_label", "reviewer_1_status",
            "reviewer_1_ambiguity_reason", "reviewer_2_id", "reviewer_2_label",
            "reviewer_2_status", "reviewer_2_ambiguity_reason",
            "adjudicated_label", "adjudication_status", "adjudication_notes",
        ]
        with results.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerow({
                "review_id": "slo-l05-0001",
                "source_path": "fixtures/kick.wav",
                "source_sha256": "a" * 64,
                "reviewer_1_id": "r1",
                "reviewer_1_label": "Kick",
                "reviewer_1_status": "REVIEWED",
                "reviewer_2_id": "r2",
                "reviewer_2_label": "Kick",
                "reviewer_2_status": "REVIEWED",
                "adjudicated_label": "Kick",
                "adjudication_status": "AGREED",
            })
        return manifest, results

    def test_emits_annotations_without_rewriting_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest, results = self._inputs(root)
            original = manifest.read_text(encoding="utf-8")
            annotations = root / "annotations.json"
            receipt = root / "receipt.json"
            result = MODULE.apply_review_results(manifest, results, annotations, receipt)
            self.assertEqual(result["review_count"], 1)
            self.assertEqual(manifest.read_text(encoding="utf-8"), original)
            self.assertEqual(json.loads(annotations.read_text())[0]["reviewed_subcategory"], "Kick")
            self.assertEqual(json.loads(receipt.read_text())["qualification_status"], "NOT_QUALIFIED")

    def test_disagreement_requires_adjudication(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest, results = self._inputs(root)
            with results.open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            rows[0]["reviewer_2_label"] = "Snare"
            rows[0]["adjudicated_label"] = ""
            rows[0]["adjudication_status"] = ""
            with results.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaisesRegex(RuntimeError, "disagreeing"):
                MODULE.apply_review_results(manifest, results, root / "a.json", root / "r.json")

    def test_source_hash_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest, results = self._inputs(root)
            with results.open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            rows[0]["source_sha256"] = "b" * 64
            with results.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaisesRegex(RuntimeError, "source_sha256"):
                MODULE.apply_review_results(manifest, results, root / "a.json", root / "r.json")
            self.assertFalse((root / "a.json").exists())


if __name__ == "__main__":
    unittest.main()
