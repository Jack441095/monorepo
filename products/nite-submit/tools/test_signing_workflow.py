"""Exercise signing failure boundaries without Apple credentials or real artifacts."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class SigningWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="nite-submit-signing-test.")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.tools = self.root / "tools"
        self.tools.mkdir()
        self.bin = self.root / "stub-bin"
        self.bin.mkdir()
        product = Path(__file__).resolve().parent.parent
        self.version = (product / "VERSION").read_text().strip()
        (self.root / "VERSION").write_text(self.version + "\n")
        shutil.copy2(product / "tools/sign_and_notarize.sh", self.tools)
        self.manifest = self.root / f"artifacts/Submit-{self.version}-release-manifest.json"
        self.manifest.parent.mkdir()
        self.previous = b'{"previous_verified_beta":true}\n'
        self.manifest.write_bytes(self.previous)
        # Populate every signing layer so the actual inside-out loops run.
        app = self.manifest.parent / f"Submit-{self.version}-macOS.app"
        for relative in ("Resources/lib/libfixture.dylib", "Resources/bin/7za", "MacOS/NiteSubmit"):
            file = app / "Contents" / relative
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text("isolated signing fixture\n")
            file.chmod(0o755)
        self.environment = {
            **os.environ,
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "NITE_SIGNING_TEST_EVENTS": str(self.root / "events"),
            "NITE_SIGNING_TEST_MANIFEST": str(self.manifest),
        }
        self.identity = "Developer ID Application: Shipping Test (TEST)"
        self.stub(self.bin / "security", f"printf '%s\\n' '\"{self.identity}\"'\n")
        self.stub(self.bin / "codesign", 'printf "codesign %s\\n" "$*" >> "$NITE_SIGNING_TEST_EVENTS"\n')
        self.stub(self.bin / "xcrun", 'printf "xcrun %s\\n" "$*" >> "$NITE_SIGNING_TEST_EVENTS"\n')
        self.stub(self.bin / "spctl", 'printf "gatekeeper\\n" >> "$NITE_SIGNING_TEST_EVENTS"\n')
        measured = json.dumps({"verification": {
            "deterministic_checks": "534/534", "batch_summary": "47\t45\t2\t0", "release_check": "pass",
        }})
        self.stub(self.tools / "run_release_checks.sh",
                  f"printf '%s\\n' '{measured}' > \"$NITE_SIGNING_TEST_MANIFEST\"\n")
        for name in ("package_beta_zip.sh", "create_release_dmg.sh", "verify_release_artifacts.sh", "check_distribution_readiness.sh"):
            self.stub(self.tools / name, f'printf "{name}\\n" >> "$NITE_SIGNING_TEST_EVENTS"\n')
        # The final writer records its actual arguments, allowing us to check
        # that measured gate results survive signing rather than being invented.
        self.stub(self.tools / "write_release_manifest.sh",
                  'printf "%s\\n" "$@" > "$NITE_SIGNING_TEST_MANIFEST"\n')

    @staticmethod
    def stub(path, body):
        path.write_text("#!/bin/sh\nset -eu\n" + body)
        path.chmod(0o755)

    def run_workflow(self):
        return subprocess.run(
            [str(self.tools / "sign_and_notarize.sh"), "--identity", self.identity],
            cwd=self.root, env=self.environment, capture_output=True, text=True,
        )

    def test_unavailable_identity_preserves_verified_beta_before_building(self):
        self.stub(self.bin / "security", "exit 0\n")
        result = self.run_workflow()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.manifest.read_bytes(), self.previous)
        self.assertFalse((self.root / "events").exists())

    def test_signing_failure_removes_the_pre_signing_pass_manifest(self):
        # A signature changes artifact bytes: the earlier passing manifest
        # must disappear before the first signature can fail.
        self.stub(self.bin / "codesign", "exit 91\n")
        self.assertNotEqual(self.run_workflow().returncode, 0)
        self.assertFalse(self.manifest.exists())

    def test_notary_rejection_cannot_leave_a_passing_release_manifest(self):
        self.stub(self.bin / "xcrun",
                  'if [ "$2" = "submit" ]; then exit 92; fi\n')
        self.assertNotEqual(self.run_workflow().returncode, 0)
        self.assertFalse(self.manifest.exists())

    def test_success_staples_before_gatekeeper_and_preserves_measured_counts(self):
        result = self.run_workflow()
        self.assertEqual(result.returncode, 0, result.stderr)
        events = (self.root / "events").read_text().splitlines()
        gatekeeper = events.index("gatekeeper")
        stapled = [index for index, event in enumerate(events) if event.startswith("xcrun stapler staple")]
        self.assertEqual(len(stapled), 2)
        self.assertTrue(all(index < gatekeeper for index in stapled))
        self.assertEqual(self.manifest.read_text().splitlines(),
                         ["--checks", "534/534", "--batch-summary", "47\t45\t2\t0"])


if __name__ == "__main__":
    unittest.main()
