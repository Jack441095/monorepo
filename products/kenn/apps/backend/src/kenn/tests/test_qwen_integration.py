"""Unit tests for Qwen integration diagnostics and ONNX model fetcher."""

from __future__ import annotations

import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.fetch_embedding_model import download_file


class TestQwenAndEmbeddingIntegration(unittest.TestCase):

    @staticmethod
    def _response(payload: bytes):
        response = io.BytesIO(payload)
        response.headers = {"Content-Length": str(len(payload))}
        return response

    @mock.patch("scripts.fetch_embedding_model.urllib.request.urlopen")
    def test_download_file_uses_verified_default_tls_and_checks_digest(self, urlopen):
        payload = b"verified model bytes"
        urlopen.return_value = self._response(payload)
        with tempfile.TemporaryDirectory() as tmp_dir:
            dest = Path(tmp_dir) / "test.json"
            success = download_file(
                "https://example.invalid/model",
                dest,
                expected_sha256=hashlib.sha256(payload).hexdigest(),
            )

            self.assertTrue(success)
            self.assertEqual(dest.read_bytes(), payload)
            _, kwargs = urlopen.call_args
            self.assertNotIn("context", kwargs)
            self.assertEqual(kwargs["timeout"], 60)

    @mock.patch("scripts.fetch_embedding_model.urllib.request.urlopen")
    def test_download_file_rejects_digest_mismatch_without_replacing_destination(self, urlopen):
        urlopen.return_value = self._response(b"tampered")
        with tempfile.TemporaryDirectory() as tmp_dir:
            dest = Path(tmp_dir) / "model.onnx"
            dest.write_bytes(b"existing known-good artifact")

            success = download_file(
                "https://example.invalid/model",
                dest,
                expected_sha256="0" * 64,
            )

            self.assertFalse(success)
            self.assertEqual(dest.read_bytes(), b"existing known-good artifact")
            self.assertFalse((dest.parent / ".model.onnx.download").exists())


if __name__ == "__main__":
    unittest.main()
