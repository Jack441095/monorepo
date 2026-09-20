import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("validate_l05_qualification_package.py")
SPEC = importlib.util.spec_from_file_location("validate_l05_qualification_package", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class L05QualificationPackageTests(unittest.TestCase):
    def test_missing_package_is_blocked_without_inference(self):
        with tempfile.TemporaryDirectory() as directory:
            result = MODULE.validate(Path(directory))

        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("missing file: dataset_manifest.json", result["errors"])
        self.assertIn(
            "independent blind-review receipt is required; owner_review_queue.csv is not sufficient",
            result["errors"],
        )
        self.assertIn("missing file: weak_class_decisions.json", result["errors"])

    def test_weak_class_decisions_are_explicit_and_evidence_linked(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "weak_class_decisions.json").write_text(json.dumps({
                "taxonomy_class_count": 17,
                "decisions": [
                    {
                        "class": "Atmosphere",
                        "status": "suppressed",
                        "rationale": "Ground-truth contamination remains unresolved",
                        "evidence_ref": "classification-review/atmosphere-v1",
                    },
                    {
                        "class": "Vocal Loop",
                        "status": "exploratory",
                        "rationale": "Cross-vendor recall is not yet release-grade",
                        "evidence_ref": "classification-review/vocal-loop-v1",
                    },
                ]
            }))
            errors = []
            MODULE._validate_weak_class_decisions(Path(directory), errors)

        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
