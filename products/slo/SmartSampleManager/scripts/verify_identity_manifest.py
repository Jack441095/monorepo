#!/usr/bin/env python3
"""
Identity regression guard -- Phase 5, Sections 7-8.

Compares CMakeLists.txt's plugin-identity fields (COMPANY_NAME, BUNDLE_ID,
PLUGIN_MANUFACTURER_CODE, PLUGIN_CODE, PRODUCT_NAME) against
docs/APPROVED_IDENTITY_MANIFEST.json. Any drift fails the release --
BUNDLE_ID and PLUGIN_MANUFACTURER_CODE become permanently load-bearing the
moment a real DAW session references them, so an accidental or unreviewed
change here is exactly the kind of mistake this check exists to catch
before it reaches a release build, not after.

A deliberate identity change (e.g. an approved NITE DSP rebrand) is not
blocked -- it just requires updating docs/APPROVED_IDENTITY_MANIFEST.json
in the same change, which is the explicit, reviewable trail this guard is
designed to force.

Usage:
    python3 scripts/verify_identity_manifest.py
Exits 0 if CMakeLists.txt matches the approved manifest, 1 otherwise.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
CMAKE_FILE = ROOT / "CMakeLists.txt"
MANIFEST_FILE = ROOT / "docs" / "APPROVED_IDENTITY_MANIFEST.json"

FIELD_PATTERNS = {
    "company_name": r'COMPANY_NAME\s+"([^"]*)"',
    "bundle_id": r'BUNDLE_ID\s+"([^"]*)"',
    "plugin_manufacturer_code": r"PLUGIN_MANUFACTURER_CODE\s+(\S+)",
    "plugin_code": r"PLUGIN_CODE\s+(\S+)",
    "product_name": r'PRODUCT_NAME\s+"([^"]*)"',
}


def extract_current_identity(cmake_text: str) -> dict[str, str]:
    # Scope the search to the juce_add_plugin(...) call itself, not the whole
    # file -- comments elsewhere (e.g. explaining *why* a field is unchanged)
    # can legitimately contain these field names too, and matching against
    # the full file risked picking up a comment line instead of the real
    # argument.
    # Match up to a ")" at the start of a line, not just any ")" -- a field
    # value (e.g. COMPANY_COPYRIGHT's "Copyright (c) ...") can legitimately
    # contain its own parentheses, which a naive "stop at first )" regex
    # would truncate on.
    call_match = re.search(r"juce_add_plugin\(.*?\n\)", cmake_text, re.DOTALL)
    if call_match is None:
        raise SystemExit("Could not find juce_add_plugin(...) call in CMakeLists.txt")
    call_text = call_match.group(0)

    current = {}
    for field, pattern in FIELD_PATTERNS.items():
        match = re.search(pattern, call_text)
        if match is None:
            raise SystemExit(f"Could not find {field} in the juce_add_plugin(...) call -- update FIELD_PATTERNS")
        current[field] = match.group(1)
    return current


def main() -> int:
    cmake_text = CMAKE_FILE.read_text()
    current = extract_current_identity(cmake_text)
    approved = json.loads(MANIFEST_FILE.read_text())

    mismatches = []
    for field in FIELD_PATTERNS:
        if current[field] != approved.get(field):
            mismatches.append((field, approved.get(field), current[field]))

    if mismatches:
        print("IDENTITY REGRESSION GUARD FAILED -- unreviewed identity drift detected:")
        for field, expected, actual in mismatches:
            print(f"  {field}: manifest says {expected!r}, CMakeLists.txt has {actual!r}")
        print()
        print(
            "If this change is deliberate and approved, update "
            "docs/APPROVED_IDENTITY_MANIFEST.json in the same change."
        )
        print("RELEASE FAILS")
        return 1

    print(f"OK: plugin identity matches docs/APPROVED_IDENTITY_MANIFEST.json ({len(FIELD_PATTERNS)} fields checked).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
