#!/usr/bin/env python3
"""
Build-safety guard: plugin auto-installation must stay opt-in.

JUCE's COPY_PLUGIN_AFTER_BUILD adds a POST_BUILD step that copies the built
AU/VST3 into the user's LIVE plugin folders:

    ~/Library/Audio/Plug-Ins/Components/SLO.component
    ~/Library/Audio/Plug-Ins/VST3/SLO.vst3

This writes OUTSIDE the build tree, so "I built in an isolated directory" is
not protection against it. While it was unconditionally TRUE, every build --
CI, scratch, automated, or a quick compile check -- silently overwrote
whatever the user had installed.

On 2026-08-21 that overwrote the owner's installed AU and VST3 with
incomplete intermediates: JUCE's copy runs BEFORE this project's later
POST_BUILD steps (model copy, scripts/bundle_apple_deps.py), so the copies
that landed had no Contents/Frameworks/, no ONNX model, and load commands
still pointing at absolute /opt/homebrew paths. The originals were
overwritten in place and could not be recovered.

This script fails the build if that regression is ever reintroduced. It is a
static check on CMakeLists.txt -- deliberately cheap, with no configure or
build required, so it can run as the very first step in CI.

Usage:
    python3 scripts/verify_no_auto_install.py [--cmakelists PATH]

Exit 0 = auto-installation is opt-in and defaults to OFF.
Exit 1 = it is unconditional, or the opt-in wiring is missing/altered.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

OPTION_NAME = "SSM_INSTALL_PLUGINS_AFTER_BUILD"

# option(SSM_INSTALL_PLUGINS_AFTER_BUILD "..." OFF) -- allow arbitrary
# whitespace/newlines and any docstring, but the default MUST be OFF.
OPTION_RE = re.compile(
    r"option\s*\(\s*" + OPTION_NAME + r"\s+\"[^\"]*\"\s+(?P<default>\w+)\s*\)",
    re.MULTILINE,
)

# The JUCE keyword must be driven BY the option, not by a literal.
WIRED_RE = re.compile(
    r"COPY_PLUGIN_AFTER_BUILD\s+\$\{" + OPTION_NAME + r"\}"
)

# Any literal truthy value is the regression this guard exists to catch.
# CMake treats these (case-insensitively) as true.
TRUTHY = {"true", "on", "1", "yes", "y"}
LITERAL_RE = re.compile(r"COPY_PLUGIN_AFTER_BUILD\s+(?P<value>[^\s${)]+)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cmakelists",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "CMakeLists.txt",
        help="Path to CMakeLists.txt (defaults to the project root's)",
    )
    args = parser.parse_args()

    if not args.cmakelists.is_file():
        print(f"FAIL: no CMakeLists.txt at {args.cmakelists}", file=sys.stderr)
        return 1

    text = args.cmakelists.read_text(encoding="utf-8")
    failures: list[str] = []

    # 1. Any literal COPY_PLUGIN_AFTER_BUILD value that is truthy.
    for match in LITERAL_RE.finditer(text):
        value = match.group("value")
        if value.lower() in TRUTHY:
            line = text[: match.start()].count("\n") + 1
            failures.append(
                f"line {line}: COPY_PLUGIN_AFTER_BUILD is hardcoded to '{value}'. "
                f"Every build would overwrite the user's installed plugins. "
                f"Use COPY_PLUGIN_AFTER_BUILD ${{{OPTION_NAME}}} instead."
            )

    # 2. The option must exist and default to OFF.
    option_match = OPTION_RE.search(text)
    if option_match is None:
        failures.append(
            f"the option({OPTION_NAME} \"...\" OFF) declaration is missing or "
            f"its form changed; auto-installation is no longer provably opt-in."
        )
    else:
        default = option_match.group("default")
        if default.lower() != "off":
            line = text[: option_match.start()].count("\n") + 1
            failures.append(
                f"line {line}: {OPTION_NAME} defaults to '{default}', not OFF. "
                f"Installing must never be the default."
            )

    # 3. The JUCE keyword must actually be wired to the option.
    if WIRED_RE.search(text) is None:
        failures.append(
            f"COPY_PLUGIN_AFTER_BUILD is not wired to ${{{OPTION_NAME}}}; "
            f"the option exists but does not control anything."
        )

    if failures:
        print("FAIL: plugin auto-installation safety check failed.\n", file=sys.stderr)
        for f in failures:
            print(f"  * {f}", file=sys.stderr)
        print(
            "\nSee the comment above option(" + OPTION_NAME + ") in CMakeLists.txt "
            "for why this must stay opt-in.",
            file=sys.stderr,
        )
        return 1

    print(
        f"OK: plugin auto-installation is opt-in via {OPTION_NAME} and defaults to OFF "
        f"({args.cmakelists})."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
