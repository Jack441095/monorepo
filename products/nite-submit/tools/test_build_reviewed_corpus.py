"""A rebuilt corpus must not hide missing truth, source drift or duplicate cases."""

import hashlib
from pathlib import Path
import tempfile
import unittest

from build_reviewed_corpus import build_cases


class ReviewedCorpusTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.corpus = Path(self.workspace.name)
        pdf = self.corpus / "example.pdf"
        pdf.write_bytes(b"%PDF-1.4\ncontrolled local source\n")
        self.row = {"document_id": "reviewed_case", "local_filename": pdf.name,
                    "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
                    "licence_status": "TEMPLATE_FOR_PUBLIC_USE", "category": "thesis",
                    "review_method": "independent_cover_review",
                    "truth": {"project_title": "Controlled Review Example"}}

    def test_reviewed_bytes_and_truth_are_preserved_without_running_detector(self):
        cases = build_cases([self.row], self.corpus)
        self.assertEqual(cases[0]["truth"], self.row["truth"])
        self.assertEqual(cases[0]["pdf"], str(self.corpus / "example.pdf"))
        self.assertEqual(cases[0]["evaluation_mode"], "accuracy")

    def test_layout_examples_are_excluded_from_accuracy_truth(self):
        self.row.update(evaluation_mode="layout_only", truth={})
        self.assertEqual(build_cases([self.row], self.corpus)[0]["truth"], {})
        self.row["truth"] = {"student_name": "Example Author"}
        with self.assertRaisesRegex(ValueError, "must not carry"):
            build_cases([self.row], self.corpus)

    def test_source_drift_cannot_reuse_previous_review(self):
        (self.corpus / "example.pdf").write_bytes(b"%PDF-1.4\nchanged source\n")
        with self.assertRaisesRegex(ValueError, "recorded hash"):
            build_cases([self.row], self.corpus)

    def test_missing_file_cannot_produce_a_partial_validation_manifest(self):
        (self.corpus / "example.pdf").unlink()
        with self.assertRaises(FileNotFoundError):
            build_cases([self.row], self.corpus)

    def test_duplicate_ids_or_paths_cannot_inflate_coverage(self):
        for duplicate in [dict(self.row), dict(self.row, document_id="second_id")]:
            with self.subTest(duplicate=duplicate["document_id"]), self.assertRaisesRegex(ValueError, "Duplicate"):
                build_cases([self.row, duplicate], self.corpus)

    def test_unknown_truth_and_detector_output_are_not_independent_reviews(self):
        for change in [{"truth": {}}, {"truth": {"student_id": "UNREVIEWED"}},
                       {"truth": {"unsupported_field": "value"}},
                       {"review_method": "detector_output"}, {"evaluation_mode": "skip"}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                build_cases([dict(self.row, **change)], self.corpus)

    def test_controlled_fixture_truth_cannot_qualify_public_document_accuracy(self):
        self.row["review_method"] = "controlled_fixture_truth"
        with self.assertRaisesRegex(ValueError, "cannot qualify"):
            build_cases([self.row], self.corpus)
        self.row["licence_status"] = "CONTROLLED_GENERATED_TEST_DATA"
        self.assertEqual(len(build_cases([self.row], self.corpus)), 1)

    def test_empty_or_unqualified_corpus_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "no cases"):
            build_cases([], self.corpus)
        for change in [{"qualification_eligible": False}, {"licence_status": "UNKNOWN"}]:
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "Unqualified"):
                build_cases([dict(self.row, **change)], self.corpus)


if __name__ == "__main__":
    unittest.main()
