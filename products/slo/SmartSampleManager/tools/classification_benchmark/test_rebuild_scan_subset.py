import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_DIR))

import rebuild_scan_subset  # noqa: E402


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class RebuildScanSubsetTests(unittest.TestCase):
    def test_strip_manifest_prefix_recovers_source_basename(self):
        self.assertEqual(
            rebuild_scan_subset.strip_manifest_prefix(
                "0760_KSHMR_Vocal_Energy_Booster_01_Ahh_128_D.wav"),
            "KSHMR_Vocal_Energy_Booster_01_Ahh_128_D.wav",
        )

    def test_dry_run_resolves_without_copying(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            corpus = root / "packs"
            corpus.mkdir()
            payload = b"real audio bytes"
            (corpus / "Kick_01_A.wav").write_bytes(payload)
            manifest = root / "dataset_manifest.json"
            manifest.write_text(json.dumps([
                {"filename": "0001_Kick_01_A.wav", "sha256": sha256_bytes(payload),
                 "expected_subcategory": "Kick"},
            ]), encoding="utf-8")
            output = root / "fixtures" / "scan_subset"

            receipt = rebuild_scan_subset.rebuild(
                manifest, corpus, output, dry_run=True)

            self.assertEqual(receipt["resolved"], 1)
            self.assertEqual(receipt["missing"], 0)
            self.assertEqual(receipt["verified"], 0)
            self.assertFalse(output.exists())
            self.assertFalse(receipt["policy"]["source_packs_modified"])

    def test_hash_mismatch_blocks_publish(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            corpus = root / "packs"
            corpus.mkdir()
            (corpus / "Snare_01.wav").write_bytes(b"tampered audio")
            manifest = root / "dataset_manifest.json"
            manifest.write_text(json.dumps([
                {"filename": "0002_Snare_01.wav", "sha256": "0" * 64,
                 "expected_subcategory": "Snare"},
            ]), encoding="utf-8")
            output = root / "fixtures" / "scan_subset"

            with self.assertRaises(RuntimeError):
                rebuild_scan_subset.rebuild(manifest, corpus, output)

            self.assertFalse(output.exists())
            leftovers = list((root / "fixtures").glob(".scan_subset.stage-*"))
            self.assertEqual(leftovers, [])

    def test_missing_source_entry_blocks_rebuild(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            corpus = root / "packs"
            corpus.mkdir()
            manifest = root / "dataset_manifest.json"
            manifest.write_text(json.dumps([
                {"filename": "0003_Absent.wav", "sha256": "a" * 64},
            ]), encoding="utf-8")

            with self.assertRaises(RuntimeError) as ctx:
                rebuild_scan_subset.rebuild(
                    manifest, corpus, root / "fixtures" / "scan_subset")
            self.assertIn("unresolved", str(ctx.exception))

    def test_publish_is_verified_and_refuses_overwrite_without_force(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            corpus = root / "packs"
            corpus.mkdir()
            payload = b"verified audio bytes"
            (corpus / "Loop_01_128_Cm.wav").write_bytes(payload)
            manifest = root / "dataset_manifest.json"
            manifest.write_text(json.dumps([
                {"filename": "0004_Loop_01_128_Cm.wav",
                 "sha256": sha256_bytes(payload),
                 "expected_subcategory": "Vocal Loop"},
            ]), encoding="utf-8")
            output = root / "fixtures" / "scan_subset"

            receipt = rebuild_scan_subset.rebuild(manifest, corpus, output)
            self.assertEqual(receipt["verified"], 1)
            self.assertEqual(
                hashlib.sha256(
                    (output / "0004_Loop_01_128_Cm.wav").read_bytes()
                ).hexdigest(),
                sha256_bytes(payload),
            )
            # Existing subset is protected unless --force is explicit.
            with self.assertRaises(RuntimeError):
                rebuild_scan_subset.rebuild(manifest, corpus, output)

    def test_ambiguous_basename_resolved_by_content_hash(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            corpus = root / "packs"
            for sub in ("pack_a", "pack_b"):
                (corpus / sub).mkdir(parents=True)
                (corpus / sub / "EAST.wav").write_bytes((sub + " bytes").encode())
            wanted = b"pack_b bytes"
            manifest = root / "dataset_manifest.json"
            manifest.write_text(json.dumps([
                {"filename": "0007_EAST.wav", "sha256": sha256_bytes(wanted),
                 "expected_subcategory": "Drum Loop"},
            ]), encoding="utf-8")

            receipt = rebuild_scan_subset.rebuild(
                manifest, corpus, root / "fixtures" / "scan_subset")
            self.assertEqual(receipt["disambiguated_by_hash"], 1)
            self.assertEqual(receipt["missing"], 0)
            self.assertEqual(
                (root / "fixtures" / "scan_subset" / "0007_EAST.wav").read_bytes(),
                wanted,
            )

    def test_unresolvable_ambiguity_is_reported_not_guessed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            corpus = root / "packs"
            for sub in ("pack_a", "pack_b"):
                (corpus / sub).mkdir(parents=True)
                (corpus / sub / "EAST.wav").write_bytes((sub + " bytes").encode())
            manifest = root / "dataset_manifest.json"
            manifest.write_text(json.dumps([
                {"filename": "0008_EAST.wav", "sha256": sha256_bytes(b"neither"),
                 "expected_subcategory": "Drum Loop"},
            ]), encoding="utf-8")

            with self.assertRaises(RuntimeError) as ctx:
                rebuild_scan_subset.rebuild(
                    manifest, corpus, root / "fixtures" / "scan_subset")
            self.assertIn("unresolved", str(ctx.exception))
            self.assertFalse((root / "fixtures" / "scan_subset").exists())


if __name__ == "__main__":
    unittest.main()