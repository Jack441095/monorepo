"""Missing inputs or extraction mistakes must fail the rebuilt corpus check."""

import copy
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
import subprocess

from build_reviewed_corpus import FIELDS
from check_rebuilt_corpus import check_coverage, check_report, check_qualification, qualification_record, run_validation


class RebuiltCorpusChecks(unittest.TestCase):
    def setUp(self):
        self.cases = [{"truth": {"student_id": "12345678"}},
                      {"truth": {"student_id": "ABSENT"}}, {"truth": {}}]
        self.report = {"processed": 3, "failed_missing_files": 0,
                       "encrypted_or_unreadable": 0, "wrong_high_confidence_total": 0,
                       "fields": {field: {"true_positives": "0", "false_positives": "0",
                                          "false_negatives": "0", "absent_correctly_ignored": "0"}
                                  for field in FIELDS}}
        self.report["fields"]["student_id"].update(true_positives="1", absent_correctly_ignored="1")

    def test_reviewed_values_and_absence_pass_with_layout_inputs_unscored(self):
        check_coverage(self.cases, 3, {"student_id": 2})
        check_report(self.report, self.cases)

    def test_missing_cases_and_lost_truth_cannot_reduce_coverage(self):
        for cases in [self.cases[:-1], [{"truth": {}}] * 3]:
            with self.assertRaisesRegex(ValueError, "coverage changed"):
                check_coverage(cases, 3, {"student_id": 2})

    def test_incomplete_processing_and_unreadable_inputs_fail(self):
        for key, value in [("processed", 2), ("failed_missing_files", 1),
                           ("encrypted_or_unreadable", 1), ("wrong_high_confidence_total", 1)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                check_report(dict(self.report, **{key: value}), self.cases)

    def test_any_confidence_of_wrong_or_missing_value_fails(self):
        for key, value in [("true_positives", "0"), ("false_positives", "1"),
                           ("false_negatives", "1"), ("absent_correctly_ignored", "0")]:
            report = copy.deepcopy(self.report)
            report["fields"]["student_id"][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "student_id"):
                check_report(report, self.cases)

    def test_missing_report_field_cannot_be_treated_as_zero(self):
        del self.report["fields"]["module_code"]
        with self.assertRaises(KeyError):
            check_report(self.report, self.cases)

    def test_changed_source_truth_or_case_cannot_reuse_qualification(self):
        # Matching coverage once allowed replacements to inherit a reviewed identity.
        row = {"document_id": "reviewed", "local_filename": "project_reports/public.pdf",
               "sha256": "a" * 64, "truth": {"project_title": "Independent title"}}
        expected = {"corpus_id": "rebuilt", "documents": [qualification_record(row)]}
        check_qualification({"corpus_id": "rebuilt", "documents": [row]}, expected)
        for changed in [dict(row, sha256="b" * 64), dict(row, truth={}),
                        dict(row, document_id="replacement")]:
            with self.assertRaises(ValueError):
                check_qualification({"corpus_id": "rebuilt", "documents": [changed]}, expected)

    def test_failed_subprocess_removes_stale_report_and_cannot_pass(self):
        # A previous green JSON must never certify a crashed validation process.
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / "report.json"
            report.write_text('{"processed": 47}')
            with patch("check_rebuilt_corpus.subprocess.run", side_effect=subprocess.CalledProcessError(1, "cli")):
                with self.assertRaises(subprocess.CalledProcessError):
                    run_validation(Path("cli"), Path("manifest"), report)
            self.assertFalse(report.exists())

    def test_successful_subprocess_without_new_report_cannot_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / "report.json"
            report.write_text('{}')
            with patch("check_rebuilt_corpus.subprocess.run"):
                with self.assertRaises(FileNotFoundError):
                    run_validation(Path("cli"), Path("manifest"), report)


if __name__ == "__main__":
    unittest.main()
