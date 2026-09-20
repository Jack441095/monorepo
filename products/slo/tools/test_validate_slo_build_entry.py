import sys
import json
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from validate_slo_build_entry import validate


ROOT = Path(__file__).parents[1]


class SLOBuildEntryTests(unittest.TestCase):
    def test_committed_presets_are_safe(self):
        self.assertEqual(validate(ROOT / "SmartSampleManager/CMakePresets.json"), [])

    def load_document(self):
        return json.loads((ROOT / "SmartSampleManager/CMakePresets.json").read_text())

    def assert_invalid(self, document, expected):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "CMakePresets.json"
            path.write_text(json.dumps(document))
            errors = validate(path)
        self.assertIn(expected, errors)

    def test_absolute_binary_dir_is_rejected(self):
        document = self.load_document()
        document["configurePresets"][0]["binaryDir"] = "/tmp/slo-build"
        self.assert_invalid(document, "preset builds must use the canonical sibling _build root")

    def test_child_without_base_inheritance_is_rejected(self):
        document = self.load_document()
        next(item for item in document["configurePresets"] if item["name"] == "ssm-dev")["inherits"] = "other-base"
        self.assert_invalid(document, "ssm-dev must inherit ssm-base")

    def test_build_preset_target_drift_is_rejected(self):
        document = self.load_document()
        next(item for item in document["buildPresets"] if item["name"] == "ssm-qualification")["configurePreset"] = "ssm-dev"
        self.assert_invalid(document, "build preset ssm-qualification must target configure preset ssm-qualification")

    def test_child_auto_install_override_is_rejected(self):
        document = self.load_document()
        next(item for item in document["configurePresets"] if item["name"] == "ssm-release-candidate")["cacheVariables"]["SSM_INSTALL_PLUGINS_AFTER_BUILD"] = "ON"
        self.assert_invalid(document, "ssm-release-candidate must not enable plugin auto-install")

    def test_child_architecture_override_is_rejected(self):
        document = self.load_document()
        next(item for item in document["configurePresets"] if item["name"] == "ssm-dev")["cacheVariables"]["CMAKE_OSX_ARCHITECTURES"] = "x86_64"
        self.assert_invalid(document, "ssm-dev must inherit the common architecture without overriding it")

    def test_child_fetchcontent_root_override_is_rejected(self):
        document = self.load_document()
        next(item for item in document["configurePresets"] if item["name"] == "ssm-qualification")["cacheVariables"]["FETCHCONTENT_BASE_DIR"] = "/tmp/slo-cache"
        self.assert_invalid(document, "ssm-qualification must inherit the common FetchContent root without overriding it")

    def test_tier_build_type_drift_is_rejected(self):
        document = self.load_document()
        next(item for item in document["configurePresets"] if item["name"] == "ssm-dev")["cacheVariables"]["CMAKE_BUILD_TYPE"] = "Release"
        self.assert_invalid(document, "ssm-dev must use the declared Debug build type")

    def test_common_architecture_drift_is_rejected(self):
        document = self.load_document()
        document["configurePresets"][0]["cacheVariables"]["CMAKE_OSX_ARCHITECTURES"] = "x86_64"
        self.assert_invalid(document, "the common preset must pin the supported arm64 architecture")


if __name__ == "__main__":
    unittest.main()
