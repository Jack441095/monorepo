#!/usr/bin/env python3
"""Validate SLO's user-visible product identity without building audio code."""

from __future__ import annotations

from pathlib import Path


EXPECTED_PRODUCT_NAME = 'PRODUCT_NAME "SLO"'
LEGACY_PRODUCT_NAME = 'PRODUCT_NAME "Smart Sample Manager"'
EXPECTED_ABOUT_TITLE = '"About SLO"'
EXPECTED_ABOUT_BODY = '"SLO\\nversion 1.0.0 (dev build)\\n\\n"'
LEGACY_ABOUT_TEXT = "Smart Sample Manager"


def validate(cmake_path: Path, editor_path: Path) -> list[str]:
    errors: list[str] = []
    try:
        cmake = cmake_path.read_text(encoding="utf-8")
        editor = editor_path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"cannot read identity source: {exc}"]

    if EXPECTED_PRODUCT_NAME not in cmake:
        errors.append("CMake product name must be SLO")
    if LEGACY_PRODUCT_NAME in cmake:
        errors.append("legacy Smart Sample Manager PRODUCT_NAME must be absent")
    if EXPECTED_ABOUT_TITLE not in editor:
        errors.append("About dialog must identify the product as SLO")
    if EXPECTED_ABOUT_BODY not in editor:
        errors.append("About dialog body must identify the product as SLO")
    if LEGACY_ABOUT_TEXT in editor:
        errors.append("legacy Smart Sample Manager About text must be absent")
    return errors


def main() -> int:
    root = Path(__file__).parents[1]
    errors = validate(root / "SmartSampleManager/CMakeLists.txt",
                      root / "SmartSampleManager/Source/PluginEditor.cpp")
    if errors:
        print("INVALID SLO product identity")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print("VALID SLO product identity: user-visible build and About surfaces use SLO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
