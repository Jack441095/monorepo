import importlib.util
import unittest
from pathlib import Path

import numpy as np


SPEC = importlib.util.spec_from_file_location(
    "full_taxonomy_loop_specialist_fusion",
    Path(__file__).with_name("full_taxonomy_loop_specialist_fusion.py"),
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class FullTaxonomyLoopSpecialistFusionTests(unittest.TestCase):
    def test_override_requires_a_compatible_loop_variant(self):
        pred = np.asarray(["Kick", "Other/none", "Drum Loop"], dtype=object)
        probability = np.asarray([0.9, 0.99, 0.99])
        fused, changed = MODULE._override(
            pred, probability,
            ["Kick", "Kick Loop", "Other/none", "Drum Loop"],
            0.8,
        )
        np.testing.assert_array_equal(fused, ["Kick Loop", "Other/none", "Drum Loop"])
        np.testing.assert_array_equal(changed, [True, False, False])

    def test_high_incumbent_confidence_blocks_override(self):
        pred = np.asarray(["Kick"], dtype=object)
        fused, changed = MODULE._override(
            pred, np.asarray([0.99]), ["Kick", "Kick Loop"], 0.8,
            incumbent_conf=np.asarray([0.95]), max_incumbent_conf=0.8,
        )
        np.testing.assert_array_equal(fused, pred)
        self.assertFalse(bool(changed[0]))


if __name__ == "__main__":
    unittest.main()
