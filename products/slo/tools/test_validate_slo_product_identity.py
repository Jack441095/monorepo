import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from validate_slo_product_identity import validate


ROOT = Path(__file__).parents[1]


class SLOProductIdentityTests(unittest.TestCase):
    def test_committed_identity_is_current(self):
        self.assertEqual(
            validate(ROOT / "SmartSampleManager/CMakeLists.txt",
                     ROOT / "SmartSampleManager/Source/PluginEditor.cpp"),
            [],
        )

    def test_legacy_cmake_name_is_rejected(self):
        cmake = 'juce_add_plugin(SmartSampleManager PRODUCT_NAME "Smart Sample Manager")'
        with tempfile.TemporaryDirectory() as directory:
            cmake_path = Path(directory) / "CMakeLists.txt"
            editor_path = Path(directory) / "PluginEditor.cpp"
            cmake_path.write_text(cmake, encoding="utf-8")
            editor_path.write_text('"About SLO"\n"SLO\\nversion 1.0.0 (dev build)\\n\\n"', encoding="utf-8")
            self.assertIn("CMake product name must be SLO", validate(cmake_path, editor_path))

    def test_legacy_about_name_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            cmake_path = Path(directory) / "CMakeLists.txt"
            editor_path = Path(directory) / "PluginEditor.cpp"
            cmake_path.write_text('PRODUCT_NAME "SLO"', encoding="utf-8")
            editor_path.write_text('"About Smart Sample Manager"', encoding="utf-8")
            self.assertIn("About dialog must identify the product as SLO",
                          validate(cmake_path, editor_path))


if __name__ == "__main__":
    unittest.main()
