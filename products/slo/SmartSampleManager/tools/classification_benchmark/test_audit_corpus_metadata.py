import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("audit_corpus_metadata.py")
SPEC = importlib.util.spec_from_file_location("audit_corpus_metadata", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CorpusMetadataAuditTests(unittest.TestCase):
    def test_basename_collision_summary_is_explicit(self):
        summary = MODULE.summarize_basename_collisions([
            "/corpus/vendor_a/kick.wav",
            "/corpus/vendor_b/kick.wav",
            "/corpus/vendor_b/snare.wav",
        ])

        self.assertEqual(summary["duplicate_basename_count"], 1)
        self.assertEqual(summary["duplicate_basename_rows"], 2)
        self.assertEqual(summary["duplicate_basename_examples"][0]["basename"], "kick.wav")

    def test_same_real_path_is_not_a_collision(self):
        summary = MODULE.summarize_basename_collisions([
            "/corpus/vendor/kick.wav",
            "/corpus/vendor/../vendor/kick.wav",
        ])

        self.assertEqual(summary["duplicate_basename_count"], 0)


if __name__ == "__main__":
    unittest.main()
