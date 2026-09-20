import importlib.util
import unittest
from pathlib import Path


SPEC = importlib.util.spec_from_file_location(
    "full_taxonomy_loop_family_feature_fusion",
    Path(__file__).with_name("full_taxonomy_loop_family_feature_fusion.py"),
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class FullTaxonomyLoopFamilyFeatureFusionTests(unittest.TestCase):
    def test_feature_contract_is_explicit(self):
        self.assertEqual(len(MODULE.LOOP_NAMES), 10)
        self.assertIn("repetition_score", MODULE.PHYSICS_FEATURES)
        self.assertNotIn("early_tail_ratio", MODULE.PHYSICS_FEATURES)


if __name__ == "__main__":
    unittest.main()
