"""Recovery must reject changed sources and leave private/local files intact."""

import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from restore_public_corpus import restore, source_path


class PublicCorpusRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.corpus = Path(self.workspace.name) / "corpus"
        self.pdf = b"%PDF-1.4\ncontrolled recovery fixture\n"
        self.row = {
            "local_filename": "university_templates/example.pdf",
            "sha256": hashlib.sha256(self.pdf).hexdigest(),
            "licence_status": "TEMPLATE_FOR_PUBLIC_USE",
            # The URL is never opened in these tests; the response is injected.
            "source_url": "https:///example.pdf",
        }

    def test_hash_matching_source_is_installed_and_verified_without_redownload(self):
        opener = Mock(return_value=io.BytesIO(self.pdf))
        self.assertEqual(restore(self.row, self.corpus, opener=opener), "restored")
        target = source_path(self.row, self.corpus)
        self.assertEqual(target.read_bytes(), self.pdf)
        self.assertEqual(restore(self.row, self.corpus, check=True, opener=opener), "verified")
        self.assertEqual(opener.call_count, 1)

    def test_changed_public_pdf_is_rejected_without_partial_file(self):
        opener = Mock(return_value=io.BytesIO(b"%PDF-1.4\ndifferent document"))
        with self.assertRaisesRegex(ValueError, "differs from recorded"):
            restore(self.row, self.corpus, opener=opener)
        self.assertEqual(list(self.corpus.rglob("*.*")), [])

    def test_existing_local_file_is_preserved_on_hash_mismatch(self):
        target = source_path(self.row, self.corpus)
        target.parent.mkdir(parents=True)
        target.write_bytes(b"local document")
        opener = Mock()
        with self.assertRaisesRegex(ValueError, "Existing file differs"):
            restore(self.row, self.corpus, opener=opener)
        self.assertEqual(target.read_bytes(), b"local document")
        opener.assert_not_called()

    def test_private_intake_and_parent_traversal_cannot_be_destinations(self):
        for name in ["../private.pdf", "beta_intake/private.pdf", "test_results/output.pdf", ""]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                source_path({"local_filename": name, "file": name}, self.corpus)

    def test_symlink_cannot_redirect_download_outside_corpus(self):
        self.corpus.mkdir()
        (self.corpus / "university_templates").symlink_to(Path(self.workspace.name))
        with self.assertRaisesRegex(ValueError, "outside the corpus"):
            source_path(self.row, self.corpus)

    def test_unknown_reuse_status_never_downloads(self):
        self.row["licence_status"] = "UNKNOWN"
        opener = Mock()
        with self.assertRaisesRegex(ValueError, "not approved"):
            restore(self.row, self.corpus, opener=opener)
        opener.assert_not_called()

    def test_network_failure_leaves_no_partial_file(self):
        opener = Mock(side_effect=TimeoutError("source timed out"))
        with self.assertRaises(TimeoutError):
            restore(self.row, self.corpus, opener=opener)
        self.assertEqual(list(self.corpus.rglob("*.*")), [])

    def test_html_and_oversized_responses_cannot_be_installed(self):
        for content, limit in [(b"<html>error</html>", 1024), (self.pdf, 5)]:
            with self.subTest(limit=limit), patch("restore_public_corpus.MAX_BYTES", limit):
                with self.assertRaises(ValueError):
                    restore(self.row, self.corpus, opener=Mock(return_value=io.BytesIO(content)))
                self.assertFalse(source_path(self.row, self.corpus).exists())

    def test_offline_missing_source_does_not_download(self):
        opener = Mock()
        with self.assertRaisesRegex(ValueError, "missing"):
            restore(self.row, self.corpus, check=True, opener=opener)
        opener.assert_not_called()


if __name__ == "__main__":
    unittest.main()
