"""Tests for the reproducible AbletonOSC installer."""

from __future__ import annotations

import tempfile
import unittest
import sys
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.install_abletonosc import SOURCE_DIR, get_possible_remote_script_dirs, install_abletonosc, select_default_target


class TestAbletonOSCInstaller(unittest.TestCase):
    def test_detects_at_least_one_conventional_location(self):
        self.assertTrue(get_possible_remote_script_dirs())

    def test_prefers_the_user_library_on_kenn_repository_volume(self):
        paths = [
            Path("/Users/example/Music/Ableton/User Library/Remote Scripts"),
            Path("/Volumes/KENN/User Library/Remote Scripts"),
        ]
        with patch.object(Path, "is_dir", return_value=True):
            selected = select_default_target(paths, repository_root=Path("/Volumes/KENN/repo"))
        self.assertEqual(selected, paths[1])

    def test_returns_none_for_ambiguous_unrelated_existing_locations(self):
        paths = [Path("/Users/example/Library/Remote Scripts"), Path("/Volumes/Other/User Library/Remote Scripts")]
        with patch.object(Path, "is_dir", return_value=True):
            self.assertIsNone(select_default_target(paths, repository_root=Path("/Volumes/KENN/repo")))

    def test_dry_run_does_not_copy(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir)
            ok, message = install_abletonosc(target, source_dir=SOURCE_DIR, dry_run=True)
            self.assertTrue(ok)
            self.assertIn("DRY-RUN", message)
            self.assertFalse((target / "AbletonOSC").exists())

    def test_copies_only_live_runtime_and_preserves_existing_install(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir)
            ok, message = install_abletonosc(target, source_dir=SOURCE_DIR)
            self.assertTrue(ok, message)
            installed = target / "AbletonOSC"
            self.assertTrue((installed / "__init__.py").is_file())
            self.assertTrue((installed / "abletonosc" / "track.py").is_file())
            self.assertTrue((installed / "pythonosc" / "osc_message.py").is_file())
            self.assertFalse((installed / "tests").exists())

            rejected, rejected_message = install_abletonosc(target, source_dir=SOURCE_DIR)
            self.assertFalse(rejected)
            self.assertIn("--replace", rejected_message)

            replaced, replaced_message = install_abletonosc(target, source_dir=SOURCE_DIR, replace=True)
            self.assertTrue(replaced, replaced_message)
            self.assertTrue(installed.is_dir())
            self.assertTrue((target / "AbletonOSC.previous").is_dir())


if __name__ == "__main__":
    unittest.main()
