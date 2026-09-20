import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("build_l05_review_packet.py")
SPEC = importlib.util.spec_from_file_location("build_l05_review_packet", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class L05ReviewPacketTests(unittest.TestCase):
    def _inputs(self, directory: Path):
        manifest = directory / "manifest.json"
        manifest.write_text(json.dumps([
            {
                "sample_id": 1,
                "filename": "kick.wav",
                "local_relative_path": "fixtures/kick.wav",
                "source_path": "/private/Kick/kick.wav",
                "sha256": "a" * 64,
                "vendor_id": "vendor-a",
                "pack_id": "pack-a",
                "source_family": "family-a",
                "expected_subcategory": "Kick",
                "label_authority": "FOLDER_MAPPING",
                "label_confidence": "LOW",
                "ood": False,
            },
            {
                "sample_id": 2,
                "filename": "guitar.wav",
                "local_relative_path": "fixtures/guitar.wav",
                "source_path": "/private/Guitar/guitar.wav",
                "sha256": "b" * 64,
                "vendor_id": "vendor-b",
                "pack_id": "pack-b",
                "source_family": "family-b",
                "expected_subcategory": "OOD",
                "label_authority": "JUDGMENT_BASED_OOD",
                "label_confidence": "REVIEW_REQUIRED",
                "ood": True,
            },
        ]), encoding="utf-8")
        queue = directory / "queue.csv"
        with queue.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["relative_path", "proposed_class", "confidence"])
            writer.writeheader()
            writer.writerow({"relative_path": "fixtures/kick.wav", "proposed_class": "Snare", "confidence": "0.4"})
        errors = directory / "errors.csv"
        with errors.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["filename", "predicted_class", "confidence"])
            writer.writeheader()
            writer.writerow({"filename": "guitar.wav", "predicted_class": "Synth", "confidence": "0.99"})
        return manifest, queue, errors

    def test_builds_blind_packet_and_separate_key_without_audio_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest, queue, errors = self._inputs(root)
            output = root / "review"
            result = MODULE.build_packet(manifest, queue, errors, output)

            self.assertEqual(result["status"], "READY_FOR_HUMAN_REVIEW")
            self.assertEqual(result["candidate_count"], 2)
            with (output / "blind_review_packet.csv").open(encoding="utf-8") as handle:
                blind = list(csv.DictReader(handle))
            with (output / "review_packet_key.csv").open(encoding="utf-8") as handle:
                key = list(csv.DictReader(handle))
            self.assertEqual(len(blind), 2)
            self.assertEqual(len(key), 2)
            self.assertNotIn("expected_subcategory", blind[0])
            self.assertEqual(key[0]["expected_subcategory"], "Kick")
            self.assertEqual(key[1]["ood"], "true")
            self.assertFalse((root / "private").exists())

    def test_refuses_ambiguous_basename(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest, queue, errors = self._inputs(root)
            data = json.loads(manifest.read_text(encoding="utf-8"))
            data.append({**data[0], "source_path": "/other/kick.wav", "sha256": "c" * 64})
            manifest.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "ambiguous"):
                MODULE.build_packet(manifest, queue, errors, root / "review")

    def test_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest, queue, errors = self._inputs(root)
            output = root / "review"
            output.mkdir()
            (output / "blind_review_packet.csv").write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "overwrite"):
                MODULE.build_packet(manifest, queue, errors, output)


if __name__ == "__main__":
    unittest.main()
