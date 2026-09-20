import importlib.util
import unittest
from pathlib import Path


SPEC = importlib.util.spec_from_file_location(
    "full_taxonomy_loop_family_specialist",
    Path(__file__).with_name("full_taxonomy_loop_family_specialist.py"),
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class FullTaxonomyLoopFamilySpecialistTests(unittest.TestCase):
    def test_supported_loop_targets_are_explicit(self):
        self.assertIn("Drum Loop", MODULE.LOOP_TARGETS)
        self.assertNotIn("Crash", MODULE.LOOP_TARGETS)


if __name__ == "__main__":
    unittest.main()
