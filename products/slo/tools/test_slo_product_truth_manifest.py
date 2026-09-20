import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SLOProductTruthManifestTests(unittest.TestCase):
    def test_manifest_is_current_and_fail_closed(self):
        result = subprocess.run(
            [sys.executable, "-B", str(ROOT / "tools/validate_slo_product_truth_manifest.py")],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("slo_product_truth_manifest=valid", result.stdout)
        self.assertIn("release_ready=false", result.stdout)
        self.assertIn("owner_approved=false", result.stdout)


if __name__ == "__main__":
    unittest.main()
