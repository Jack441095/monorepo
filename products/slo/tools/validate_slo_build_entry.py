#!/usr/bin/env python3
"""Validate the committed SLO CMake preset safety contract."""

from __future__ import annotations

import json
from pathlib import Path


REQUIRED = {"ssm-dev", "ssm-qualification", "ssm-release-candidate"}
CANONICAL_BINARY_DIR = "${sourceDir}/../_build/${presetName}"
CANONICAL_FETCHCONTENT_DIR = "${sourceDir}/../_cache/fetchcontent"
EXPECTED_BUILD_TYPES = {
    "ssm-dev": "Debug",
    "ssm-qualification": "Release",
    "ssm-release-candidate": "Release",
}


def validate(path: Path) -> list[str]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"cannot parse presets: {exc}"]
    errors: list[str] = []
    configure = {item["name"]: item for item in document.get("configurePresets", []) if isinstance(item, dict) and "name" in item}
    if not REQUIRED.issubset(configure):
        errors.append("dev, qualification, and release-candidate configure presets are required")
    base = configure.get("ssm-base", {})
    if base.get("binaryDir") != CANONICAL_BINARY_DIR:
        errors.append("preset builds must use the canonical sibling _build root")
    if base.get("inherits"):
        errors.append("the hidden base preset must not inherit another preset")
    if base.get("cacheVariables", {}).get("FETCHCONTENT_BASE_DIR") != CANONICAL_FETCHCONTENT_DIR:
        errors.append("FetchContent must use the canonical sibling _cache root")
    if base.get("cacheVariables", {}).get("SSM_INSTALL_PLUGINS_AFTER_BUILD") != "OFF":
        errors.append("auto-install must be OFF in the common preset")
    if base.get("cacheVariables", {}).get("CMAKE_OSX_ARCHITECTURES") != "arm64":
        errors.append("the common preset must pin the supported arm64 architecture")
    for name in REQUIRED:
        preset = configure.get(name, {})
        if preset.get("inherits") != "ssm-base":
            errors.append(f"{name} must inherit ssm-base")
        binary_dir = preset.get("binaryDir")
        if isinstance(binary_dir, str) and (binary_dir.startswith(("/", "~")) or "SmartSampleManager" in binary_dir):
            errors.append(f"{name} must not define an absolute or in-source binaryDir")
        if preset.get("cacheVariables", {}).get("SSM_INSTALL_PLUGINS_AFTER_BUILD") == "ON":
            errors.append(f"{name} must not enable plugin auto-install")
        cache = preset.get("cacheVariables", {})
        if "CMAKE_OSX_ARCHITECTURES" in cache:
            errors.append(f"{name} must inherit the common architecture without overriding it")
        if "FETCHCONTENT_BASE_DIR" in cache:
            errors.append(f"{name} must inherit the common FetchContent root without overriding it")
        if cache.get("CMAKE_BUILD_TYPE") != EXPECTED_BUILD_TYPES[name]:
            errors.append(f"{name} must use the declared {EXPECTED_BUILD_TYPES[name]} build type")
    build_names = {item.get("name") for item in document.get("buildPresets", []) if isinstance(item, dict)}
    if not REQUIRED.issubset(build_names):
        errors.append("each supported configure preset needs a matching build preset")
    build_presets = {item.get("name"): item for item in document.get("buildPresets", []) if isinstance(item, dict) and item.get("name")}
    for name in REQUIRED:
        if build_presets.get(name, {}).get("configurePreset") != name:
            errors.append(f"build preset {name} must target configure preset {name}")
    return errors


def main() -> int:
    path = Path(__file__).parents[1] / "SmartSampleManager/CMakePresets.json"
    errors = validate(path)
    if errors:
        print("INVALID SLO build-entry policy")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print("VALID SLO build-entry policy: three tiers; out-of-tree; auto-install off")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
