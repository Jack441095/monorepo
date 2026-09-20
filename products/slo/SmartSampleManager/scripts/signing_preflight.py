#!/usr/bin/env python3
"""
Signing preflight -- Phase 5.5, Section 59.

Checks every precondition that must hold before a real `codesign`/
`notarytool` invocation would be attempted, and reports exactly what's
missing. Never attempts to sign or notarize anything itself, and never
fakes a result -- Section 58 is explicit: "Do not fake execution."

This exists so that the moment Apple Developer credentials are available,
running this script tells you immediately whether you're actually ready to
sign, instead of discovering a missing manifest/identity/build problem
partway through a real (rate-limited, non-free) notarization submission.

Usage:
    python3 scripts/signing_preflight.py [--format vst3|au|standalone|all]
Exits 0 if every checkable precondition passes, 1 if any fail. Credential
checks (signing identity, notarization credentials) are reported but never
cause a "crash" -- their absence is the expected, current state.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
BUILD_RELEASE = REPO_ROOT / "build-release" / "SmartSampleManager_artefacts" / "Release"

FORMAT_PATHS = {
    "vst3": (BUILD_RELEASE / "VST3" / "SLO.vst3", "vst3"),
    "au": (BUILD_RELEASE / "AU" / "SLO.component", "au"),
    "standalone": (BUILD_RELEASE / "Standalone" / "SLO.app", "standalone"),
}


def check(description: str, passed: bool, detail: str = "") -> bool:
    marker = "PASS" if passed else "FAIL"
    line = f"  [{marker}] {description}"
    if detail:
        line += f" -- {detail}"
    print(line)
    return passed


def find_signing_identity() -> str | None:
    result = subprocess.run(
        ["security", "find-identity", "-v", "-p", "codesigning"], capture_output=True, text=True
    )
    for line in result.stdout.splitlines():
        if "Developer ID Application" in line:
            return line.strip()
    return None


def find_notarization_profile() -> bool:
    # notarytool credentials are typically stored via `xcrun notarytool
    # store-credentials` under a named keychain profile -- there's no
    # direct "list profiles" command, so the only real check is whether
    # notarytool itself is available; actual credential validity can only
    # be confirmed by a real submission.
    result = subprocess.run(["xcrun", "--find", "notarytool"], capture_output=True, text=True)
    return result.returncode == 0


def check_format(format_name: str) -> bool:
    bundle_path, manifest_format = FORMAT_PATHS[format_name]
    print(f"\n{format_name.upper()}:")
    all_ok = True

    all_ok &= check(f"Release build exists ({bundle_path.name})", bundle_path.exists())
    if not bundle_path.exists():
        return all_ok

    manifest_result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "verify_release_manifest.py"), str(bundle_path), "--format", manifest_format],
        capture_output=True,
        text=True,
    )
    all_ok &= check("Release manifest passes", manifest_result.returncode == 0, manifest_result.stdout.strip().splitlines()[-1] if manifest_result.stdout else "")

    homebrew_result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "check_homebrew_dependencies.py"), str(bundle_path)],
        capture_output=True,
        text=True,
    )
    all_ok &= check("No Homebrew/dev-machine dependency paths", homebrew_result.returncode == 0)

    return all_ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--format", choices=["vst3", "au", "standalone", "all"], default="all")
    args = parser.parse_args()

    print("SIGNING PREFLIGHT")
    print("=" * 60)

    formats = list(FORMAT_PATHS) if args.format == "all" else [args.format]
    build_ok = all(check_format(fmt) for fmt in formats)

    print("\nIDENTITY MANIFEST:")
    identity_result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "verify_identity_manifest.py")], capture_output=True, text=True
    )
    identity_ok = check("Plugin identity matches docs/APPROVED_IDENTITY_MANIFEST.json", identity_result.returncode == 0)

    print("\nAPPLE CREDENTIALS (external -- see docs/HUMAN_COMMERCIAL_REQUIREMENTS.md):")
    signing_identity = find_signing_identity()
    check("Developer ID Application certificate in keychain", signing_identity is not None, signing_identity or "none found")
    check("notarytool available", find_notarization_profile())
    print("  [INFO] notarytool credential validity can only be confirmed by a real submission --")
    print("         this preflight cannot verify a stored profile is genuinely valid.")

    print("\n" + "=" * 60)
    if build_ok and identity_ok:
        print("Build/manifest/identity preflight: READY.")
    else:
        print("Build/manifest/identity preflight: NOT READY -- fix FAIL items above.")

    if signing_identity is None:
        print("Signing credentials: MISSING -- no Developer ID Application certificate found.")
        print("Cannot proceed to actual codesign/notarization until this exists.")

    return 0 if (build_ok and identity_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
