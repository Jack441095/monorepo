#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from validate_slo_m06_canonical_source import validate


class SloM06CanonicalSourceTests(unittest.TestCase):
    def test_manifest_is_fail_closed(self):
        manifest = Path(__file__).parents[1] / "validation/audits/stage-6-migration-inventory-v1/slo_m06_canonical_source_readiness_v1.json"
        self.assertEqual(validate(manifest), [])


if __name__ == "__main__":
    unittest.main()
