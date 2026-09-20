#!/usr/bin/env python3
"""
Automated macOS Codesigning, Packaging, and Notarization Script.
Phase 6 release pipeline orchestration.

Steps:
1. Run signing_preflight.py to assert build/manifest/identity validation.
2. Sign all built targets (Standalone, VST3, AU) with Developer ID Application.
3. Build component packages using pkgbuild.
4. Assemble unified installer using productbuild with distribution.xml.
5. Sign the installer package with Developer ID Installer.
6. Submit for notarization using xcrun notarytool.
7. Staple the notarization ticket to the installer.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
BUILD_DIR = REPO_ROOT / "_build" / "ssm-qualification" / "SmartSampleManager_artefacts" / "Release"
OUTPUT_DIR = REPO_ROOT / "_build" / "ssm-qualification" / "Release_Installers"

FORMAT_PATHS = {
    "standalone": BUILD_DIR / "Standalone" / "Smart Sample Manager.app",
    "vst3": BUILD_DIR / "VST3" / "Smart Sample Manager.vst3",
    "au": BUILD_DIR / "AU" / "Smart Sample Manager.component",
}


def log(msg: str) -> None:
    print(f"--> [RELEASE BUILD ENGINE] {msg}")


def run_cmd(cmd: list[str], dry_run: bool = False) -> bool:
    log(f"Running: {' '.join(cmd)}")
    if dry_run:
        log("  [DRY-RUN] Command skipped.")
        return True
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log(f"FAIL: Command failed with code {result.returncode}")
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        return False
    return True


def run_preflight() -> bool:
    log("Running pre-signing checks via signing_preflight.py...")
    preflight_script = REPO_ROOT / "scripts" / "signing_preflight.py"
    result = subprocess.run([sys.executable, str(preflight_script)], capture_output=True, text=True)
    print(result.stdout)
    return result.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Codesign and package macOS installer.")
    parser.add_argument("--identity", help="Apple Developer ID Application Certificate Common Name (e.g. 'Developer ID Application: Company')")
    parser.add_argument("--installer-identity", help="Apple Developer ID Installer Certificate Common Name")
    parser.add_argument("--keychain-profile", help="Keychain profile name stored via notarytool store-credentials")
    parser.add_argument("--dry-run", action="store_true", help="Perform checks and mock signing/notarization steps")
    args = parser.parse_args()

    # 1. Run Preflight
    if not run_preflight():
        log("Pre-signing checks FAILED. Correct issues before continuing.")
        if not args.dry_run:
            return 1

    if not args.dry_run and not args.identity:
        log("Error: --identity is required for real release signing. Use --dry-run to test configuration.")
        return 1

    # 2. Codesign Bundles
    log("Codesigning executable bundles...")
    for fmt, path in FORMAT_PATHS.items():
        if not path.exists():
            log(f"Bundle missing: {path}")
            return 1
        sign_cmd = [
            "codesign",
            "-s",
            args.identity or "Developer ID Application: Dummy",
            "--timestamp",
            "--options",
            "runtime",
            "--force",
            "--deep",
            str(path),
        ]
        if not run_cmd(sign_cmd, dry_run=args.dry_run):
            return 1

    # 3. Create Component PKGs
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    log("Building component packages using pkgbuild...")

    pkg_mappings = [
        ("Standalone", FORMAT_PATHS["standalone"], "/Applications", OUTPUT_DIR / "SmartSampleManager_Standalone.pkg"),
        ("VST3", FORMAT_PATHS["vst3"], "/Library/Audio/Plug-Ins/VST3", OUTPUT_DIR / "SmartSampleManager_VST3.pkg"),
        ("AU", FORMAT_PATHS["au"], "/Library/Audio/Plug-Ins/Components", OUTPUT_DIR / "SmartSampleManager_AU.pkg"),
    ]

    for name, path, install_loc, pkg_out in pkg_mappings:
        pkg_cmd = [
            "pkgbuild",
            "--component",
            str(path),
            "--install-location",
            install_loc,
            str(pkg_out),
        ]
        if not run_cmd(pkg_cmd, dry_run=args.dry_run):
            return 1

    # 4. Unified productbuild Installer Package
    log("Creating unified productbuild installer package...")
    dist_xml = REPO_ROOT / "scripts" / "distribution.xml"
    final_pkg = OUTPUT_DIR / "SmartSampleManager-Installer.pkg"
    
    prod_cmd = [
        "productbuild",
        "--distribution",
        str(dist_xml),
        "--package-path",
        str(OUTPUT_DIR),
        str(final_pkg),
    ]
    if not run_cmd(prod_cmd, dry_run=args.dry_run):
        return 1

    # 5. Sign the Unified Installer
    log("Signing installer package...")
    signed_pkg = OUTPUT_DIR / "SmartSampleManager-Installer-Signed.pkg"
    sign_installer_cmd = [
        "productsign",
        "--sign",
        args.installer_identity or "Developer ID Installer: Dummy",
        str(final_pkg),
        str(signed_pkg),
    ]
    if not run_cmd(sign_installer_cmd, dry_run=args.dry_run):
        return 1

    # 6. Notarize
    if args.keychain_profile:
        log("Submitting signed package for Apple Notarization...")
        notary_cmd = [
            "xcrun",
            "notarytool",
            "submit",
            str(signed_pkg),
            "--keychain-profile",
            args.keychain_profile,
            "--wait",
        ]
        if not run_cmd(notary_cmd, dry_run=args.dry_run):
            return 1

        # 7. Staple Notarization Ticket
        log("Stapling notarization ticket to package...")
        staple_cmd = ["xcrun", "stapler", "staple", str(signed_pkg)]
        if not run_cmd(staple_cmd, dry_run=args.dry_run):
            return 1
    else:
        log("Skipping notarization submit (--keychain-profile omitted).")

    log("macOS codesigning and installer generation COMPLETE.")
    log(f"Output files located at: {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
