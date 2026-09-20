"""Unit tests for Ableton Remote Script installer."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.install_remote_script import get_possible_remote_script_dirs, install_bridge


class TestRemoteScriptInstaller(unittest.TestCase):

    def test_get_possible_remote_script_dirs(self):
        dirs = get_possible_remote_script_dirs()
        self.assertIsInstance(dirs, list)
        self.assertGreater(len(dirs), 0)

    def test_install_bridge_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir)
            success, msg = install_bridge(target, dry_run=True)
            self.assertTrue(success)
            self.assertIn("[DRY-RUN]", msg)
            self.assertFalse((target / "KENN_Bridge").exists())

    def test_install_bridge_actual_copy(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir)
            success, msg = install_bridge(target, dry_run=False)
            self.assertTrue(success)
            self.assertIn("Successfully installed", msg)
            installed_bridge = target / "KENN_Bridge"
            self.assertTrue(installed_bridge.exists())
            self.assertTrue((installed_bridge / "KENN_Bridge.py").exists())
            self.assertTrue((installed_bridge / "__init__.py").exists())

    def test_bridge_disables_legacy_direct_mutation_addresses(self):
        bridge_source = (
            Path(__file__).resolve().parents[5]
            / "integrations"
            / "ableton-remote-script"
            / "KENN_Bridge"
            / "KENN_Bridge.py"
        ).read_text(encoding="utf-8")
        for address in (
            "/live/clip/load",
            "/live/clip/launch",
            "/live/scene/launch",
            "/live/scene/create",
            "/live/device/create",
            "/live/device/sidechain",
            "/live/song/transport/set_tempo",
        ):
            self.assertIn(address, bridge_source)
        self.assertIn("DISABLED_DIRECT_MUTATIONS", bridge_source)

    def test_bridge_uses_kenn_name_everywhere(self):
        bridge_source = (
            Path(__file__).resolve().parents[5]
            / "integrations"
            / "ableton-remote-script"
            / "KENN_Bridge"
            / "KENN_Bridge.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("AudioToo_Bridge", bridge_source)
        self.assertIn("class KENN_Bridge", bridge_source)
        self.assertIn("super(KENN_Bridge, self).disconnect()", bridge_source)



if __name__ == "__main__":
    unittest.main()
