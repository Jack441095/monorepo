import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_DIR))

import build_real_corpus_v2  # noqa: E402


class RealCorpusBuilderTests(unittest.TestCase):
    def test_audio_discovery_matches_admitted_formats(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for name in ("kick.wav", "snare.aif", "hat.aiff", "perc.flac", "notes.txt"):
                (root / name).write_bytes(b"fixture")

            discovered = build_real_corpus_v2.find_audio_files(str(root))

            self.assertEqual(
                {Path(path).name for path in discovered},
                {"kick.wav", "snare.aif", "hat.aiff", "perc.flac"},
            )

    def test_manifest_only_collection_records_path_and_family_provenance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_folder = root / "Vendor" / "Pack" / "Kicks"
            source_folder.mkdir(parents=True)
            source_file = source_folder / "Family_Kick_01.wav"
            source_file.write_bytes(b"fixture")

            with patch.object(
                build_real_corpus_v2,
                "MAPPING",
                {"Vendor": {"Pack/Kicks": "Kick"}},
            ), patch.object(build_real_corpus_v2, "FILENAME_KEYWORD_SPLIT_FOLDERS", {}):
                manifest, missing, unmatched = build_real_corpus_v2.collect_manifest(str(root))

            self.assertEqual(missing, [])
            self.assertEqual(unmatched, [])
            self.assertEqual(len(manifest), 1)
            self.assertEqual(manifest[0]["source_path"], str(source_file.resolve()))
            self.assertEqual(manifest[0]["vendor_id"], "Vendor")
            self.assertEqual(manifest[0]["expected_subcategory"], "Kick")
            self.assertTrue(manifest[0]["source_family"].startswith("Vendor/Pack/Kicks/"))

    def test_manifest_publication_preserves_previous_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest_path = Path(temp_dir) / "manifest.json"
            manifest_path.write_text("old\n", encoding="utf-8")

            backup = build_real_corpus_v2.publish_manifest(
                [{"sample_id": 1, "expected_subcategory": "Kick"}],
                str(manifest_path),
            )

            self.assertIsNotNone(backup)
            self.assertEqual(
                json.loads(manifest_path.read_text(encoding="utf-8"))[0]["sample_id"],
                1,
            )
            self.assertEqual(Path(backup).read_text(encoding="utf-8"), "old\n")


if __name__ == "__main__":
    unittest.main()
