import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_DIR))

import prepare_subset  # noqa: E402


class PrepareSubsetTests(unittest.TestCase):
    def test_default_source_root_is_the_declared_corpus(self):
        self.assertEqual(
            prepare_subset.SOURCE_ROOT,
            "/Volumes/Jack_Gandy_1TB_SSD/testing-for-NITE-DSP/sample_pack_testing",
        )

    def test_failed_plan_does_not_touch_existing_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            corpus = root / "missing-corpus"
            output = root / "fixtures" / "scan_subset"
            output.mkdir(parents=True)
            sentinel = output / "previous.txt"
            sentinel.write_text("preserve me", encoding="utf-8")
            manifest = root / "dataset_manifest.json"
            manifest.write_text("previous manifest\n", encoding="utf-8")

            with self.assertRaises(RuntimeError):
                prepare_subset.build_subset(
                    str(corpus),
                    str(output),
                    str(manifest),
                    dry_run=True,
                )

            self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve me")
            self.assertEqual(manifest.read_text(encoding="utf-8"), "previous manifest\n")

    def test_publish_preserves_previous_subset_and_manifest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.wav"
            source.write_bytes(b"fixture audio bytes")
            output = root / "scan_subset"
            output.mkdir()
            (output / "old.wav").write_bytes(b"old")
            manifest = root / "dataset_manifest.json"
            manifest.write_text("old manifest\n", encoding="utf-8")

            backup_dir = prepare_subset.publish_subset(
                [{"sample_id": 1, "filename": "new.wav"}],
                [(str(source), str(output / "new.wav"))],
                str(output),
                str(manifest),
            )

            self.assertTrue((output / "new.wav").exists())
            self.assertFalse((output / "old.wav").exists())
            self.assertIsNotNone(backup_dir)
            self.assertTrue((Path(backup_dir) / "old.wav").exists())
            self.assertEqual(
                json.loads(manifest.read_text(encoding="utf-8"))[0]["filename"],
                "new.wav",
            )


if __name__ == "__main__":
    unittest.main()
