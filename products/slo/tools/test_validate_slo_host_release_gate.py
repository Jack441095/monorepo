import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from validate_slo_host_release_gate import validate


ROOT = Path(__file__).parents[1]
MANIFEST = ROOT / "validation/audits/stage-2-slo-host-release-gate-v1/SLO_HOST_RELEASE_GATE_MANIFEST_V1.json"


class SLOHostReleaseGateTests(unittest.TestCase):
    def test_current_manifest_is_fail_closed(self):
        self.assertEqual(validate(ROOT, MANIFEST), [])

    def test_missing_gate_and_release_flag_are_rejected(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        manifest["planned_gates"].pop("vst3_validation")
        manifest["candidate"]["release_authorized"] = True
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "manifest.json"
            candidate.write_text(json.dumps(manifest), encoding="utf-8")
            errors = validate(ROOT, candidate)
        self.assertIn("planned_gates missing: vst3_validation", errors)
        self.assertIn("candidate.release_authorized must be false", errors)

    def test_live_candidate_branch_drift_is_rejected(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        manifest["candidate"]["branch"] = "wrong-branch"
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "manifest.json"
            candidate.write_text(json.dumps(manifest), encoding="utf-8")
            errors = validate(ROOT, candidate)
        self.assertIn("candidate branch does not match the live worktree", errors)


if __name__ == "__main__":
    unittest.main()
