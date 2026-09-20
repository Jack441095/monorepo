#!/usr/bin/env python3
"""
Architecture release guard -- Phase 4A (docs/APPLE_SILICON_ARCHITECTURE_AUDIT.md).

Inspects every Mach-O file inside a built .app/.component/.vst3 bundle
(the main executable AND every bundled dylib in Contents/Frameworks/) and
asserts each one contains the architecture slice(s) the release is supposed
to ship. A native-arm64 (or Universal 2) main executable whose bundled
ONNX Runtime/abseil/protobuf/re2 dylibs are still x86_64-only is not an
arm64-capable product -- it will fail to load at runtime on first launch,
not at build time, which is exactly the kind of defect this guard exists
to catch before it reaches a customer machine.

This does NOT lipo mismatched slices together, does NOT strip slices to
silence failures, and does NOT weaken/replace the existing dependency
guards (check_homebrew_dependencies.py, verify_release_manifest.py) --
it is purely additive.

Usage:
    python3 verify_architecture.py --bundle <path-to-.app-or-.component-or-.vst3> \
        --require arm64[,x86_64]

Exit code 0 = every Mach-O in the bundle contains all required slices.
Exit code 1 = at least one file is missing a required slice (details printed).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def macho_slices(path: Path) -> set[str]:
    """Return the set of architecture slices a Mach-O file (thin or fat)
    actually contains, via `file` -- works for both single-arch and
    universal binaries without requiring the file to be executable."""
    try:
        output = subprocess.run(["file", "-b", str(path)], capture_output=True, text=True, check=True).stdout
    except subprocess.CalledProcessError:
        return set()

    slices: set[str] = set()
    for token in ("x86_64", "arm64", "arm64e"):
        if token in output:
            slices.add(token)
    return slices


def is_macho_candidate(path: Path) -> bool:
    if not path.is_file():
        return False
    if path.suffix in (".dylib",):
        return True
    # Executables inside Contents/MacOS/ have no extension.
    return "MacOS" in path.parts


def find_bundle_binaries(bundle: Path) -> list[Path]:
    found: list[Path] = []
    for p in bundle.rglob("*"):
        if is_macho_candidate(p):
            found.append(p)
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", required=True, help="Path to .app / .component / .vst3 bundle")
    parser.add_argument("--require", required=True, help="Comma-separated required slices, e.g. arm64 or arm64,x86_64")
    args = parser.parse_args()

    bundle = Path(args.bundle)
    if not bundle.exists():
        print(f"FAIL: bundle not found: {bundle}")
        return 1

    required = {s.strip() for s in args.require.split(",") if s.strip()}
    if not required:
        print("FAIL: --require must list at least one architecture")
        return 1

    binaries = find_bundle_binaries(bundle)
    if not binaries:
        print(f"FAIL: no Mach-O candidates found under {bundle}")
        return 1

    failures: list[tuple[Path, set[str]]] = []
    checked = 0
    for path in binaries:
        slices = macho_slices(path)
        if not slices:
            # Not a Mach-O (e.g. a plist, a resource) -- skip silently.
            continue
        checked += 1
        missing = required - slices
        if missing:
            failures.append((path, missing))

    print(f"Checked {checked} Mach-O file(s) under {bundle}")
    print(f"Required slice(s): {sorted(required)}")

    if failures:
        print(f"\nFAIL: {len(failures)} file(s) missing required architecture slice(s):")
        for path, missing in failures:
            print(f"  {path.relative_to(bundle)}: missing {sorted(missing)}")
        return 1

    print("PASS: every bundled Mach-O contains all required slices.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
