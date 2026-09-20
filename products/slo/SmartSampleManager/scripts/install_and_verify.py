#!/usr/bin/env python3
"""
Canonical dev/release install-and-verify pipeline -- Phase 4A.2.

Closes the install-hygiene gap identified in docs/AU_AUVAL_ROOT_CAUSE.md and
carried forward as an open item in docs/PHASE_4A_1_RUNTIME_HARDENING.md: a
long-lived ~/Library/Audio/Plug-Ins/{Components,VST3}/ folder across many
incremental dev builds silently held a stale/incorrectly-bundled AU while the
current build tree was clean. Nothing in the existing release-guard scripts
(verify_architecture.py, check_homebrew_dependencies.py,
verify_release_manifest.py, verify_identity_manifest.py, signing_preflight.py)
ever inspected the ACTUALLY INSTALLED artifact -- they all take an explicit
bundle path and were only ever pointed at the build tree. This script is the
missing link: it establishes a single canonical procedure --

    BUILD -> VERIFY BUILD ARTIFACT -> INSTALL (always fresh, never incremental)
    -> VERIFY INSTALLED ARTIFACT -> COMPARE BUILD vs INSTALLED
    -> [dev-only] REFRESH AUDIO COMPONENT REGISTRAR -> [optional] AUVAL

and makes it impossible to silently validate one artifact while a different,
stale one sits installed -- the exact class of problem that produced Phase
4A's false AU failure.

This script is DEV/CI VALIDATION TOOLING. The registrar-refresh step
(--refresh-registrar) kills and lets macOS relaunch a system-managed
background process (AudioComponentRegistrar) -- safe on a dev machine
verifying its own local install, but this flag is never invoked from
anything a customer runs, and this script is not part of any customer-facing
installer. See "REGISTRAR" section of docs/PHASE_4A_2_FINAL_RUNTIME_CLOSURE.md.

Usage:
    # Full pipeline: install fresh copy of the AU from build-arm64, verify,
    # refresh registrar, run auval.
    python3 scripts/install_and_verify.py --format au --refresh-registrar --auval

    # Validate a specific fresh CMake Release tree instead of the legacy
    # build-arm64 default.
    python3 scripts/install_and_verify.py --format au \
        --build-release-dir /tmp/slo-phase86p-release-final/SmartSampleManager_artefacts/Release

    # Check-only: compare what's currently installed against what the build
    # tree currently produces, WITHOUT installing anything. Use this as a
    # pre-auval gate in any validation script -- never run auval against an
    # unverified installed artifact.
    python3 scripts/install_and_verify.py --format au --check-only

Exit code 0 = every requested step passed. Non-zero and a clearly labeled
failure otherwise -- this script never silently continues past a mismatch.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
BUILD_ARM64 = REPO_ROOT / "build-arm64" / "SmartSampleManager_artefacts" / "Release"

# Current display/bundle name. The legacy project name and bundle identifier
# remain unchanged for build and host-compatibility purposes.
BUNDLE_NAME = "SLO"
INSTALL_DIRS = {
    "au": Path.home() / "Library" / "Audio" / "Plug-Ins" / "Components",
    "vst3": Path.home() / "Library" / "Audio" / "Plug-Ins" / "VST3",
}
BUNDLE_SUFFIX = {"au": ".component", "vst3": ".vst3"}
BUILD_SUBDIR = {"au": "AU", "vst3": "VST3"}


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def macho_arch_slices(path: Path) -> list[str]:
    out = run(["file", "-b", str(path)]).stdout
    return sorted(a for a in ("x86_64", "arm64", "arm64e") if a in out)


def bundle_identity(bundle: Path) -> dict:
    """Deterministic identity manifest for a bundle: main-executable hash +
    architecture slices, plus a hash of every bundled dylib by filename, plus
    a sorted file listing. This is what BUILT ARTIFACT == INSTALLED ARTIFACT
    is actually checked against -- not just filenames or mtimes, which can
    both lie (a copy preserves a filename; `ditto`/`cp -p` can preserve or
    fake a timestamp)."""
    contents = bundle / "Contents"
    exe = contents / "MacOS" / BUNDLE_NAME
    if not exe.exists():
        raise SystemExit(f"FAIL: no main executable at {exe}")

    frameworks = contents / "Frameworks"
    dylib_hashes = {}
    if frameworks.is_dir():
        for dylib in sorted(frameworks.glob("*.dylib")):
            if dylib.is_symlink():
                continue
            dylib_hashes[dylib.name] = sha256_file(dylib)

    all_files = sorted(str(p.relative_to(contents)) for p in contents.rglob("*") if p.is_file())
    resource_hashes = {
        str(p.relative_to(contents / "Resources")): sha256_file(p)
        for p in sorted((contents / "Resources").rglob("*"))
        if p.is_file()
    } if (contents / "Resources").is_dir() else {}

    return {
        "bundle": str(bundle),
        "main_executable_sha256": sha256_file(exe),
        "main_executable_arch": macho_arch_slices(exe),
        "dylib_count": len(dylib_hashes),
        "dylib_sha256": dylib_hashes,
        "file_count": len(all_files),
        "file_manifest_sha256": hashlib.sha256("\n".join(all_files).encode()).hexdigest(),
        "resource_sha256": resource_hashes,
    }


def compare_identity(build: dict, installed: dict) -> list[str]:
    diffs = []
    if build["main_executable_sha256"] != installed["main_executable_sha256"]:
        diffs.append(
            f"main executable hash differs: build={build['main_executable_sha256'][:12]}... "
            f"installed={installed['main_executable_sha256'][:12]}..."
        )
    if build["main_executable_arch"] != installed["main_executable_arch"]:
        diffs.append(
            f"architecture differs: build={build['main_executable_arch']} "
            f"installed={installed['main_executable_arch']}"
        )
    if build["file_manifest_sha256"] != installed["file_manifest_sha256"]:
        diffs.append("bundle file listing differs (files added/removed/renamed between build and installed copy)")
    if build["resource_sha256"] != installed["resource_sha256"]:
        diffs.append("bundled resource content differs between build and installed copy")
    build_dylibs = build["dylib_sha256"]
    installed_dylibs = installed["dylib_sha256"]
    missing_in_installed = sorted(set(build_dylibs) - set(installed_dylibs))
    extra_in_installed = sorted(set(installed_dylibs) - set(build_dylibs))
    changed = sorted(
        name for name in (set(build_dylibs) & set(installed_dylibs))
        if build_dylibs[name] != installed_dylibs[name]
    )
    if missing_in_installed:
        diffs.append(f"dylibs present in build but missing from installed: {missing_in_installed}")
    if extra_in_installed:
        diffs.append(f"dylibs present in installed but not in build (stale leftovers): {extra_in_installed}")
    if changed:
        diffs.append(f"dylibs with different content (hash mismatch): {changed}")
    return diffs


def install_fresh(build_bundle: Path, dest_dir: Path, suffix: str) -> Path:
    """Always a full rm -rf + fresh ditto copy -- NEVER an incremental copy.
    This is the direct fix for the root cause in AU_AUVAL_ROOT_CAUSE.md: an
    incremental/partial copy across many dev build cycles is what let a
    stale, incorrectly-bundled component survive silently."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_bundle = dest_dir / (BUNDLE_NAME + suffix)
    if dest_bundle.exists():
        shutil.rmtree(dest_bundle)
    result = run(["ditto", str(build_bundle), str(dest_bundle)])
    if result.returncode != 0:
        raise SystemExit(f"FAIL: ditto install failed: {result.stderr}")
    return dest_bundle


def refresh_audio_component_registrar() -> None:
    """DEV-ONLY. Forces macOS's AudioComponentRegistrar to drop its cached
    architecture-hosting state and rescan installed components. Safe: it is
    a system-managed background process macOS relaunches on demand -- see
    docs/AU_AUVAL_ROOT_CAUSE.md. Never call this from anything a customer
    runs; a customer's registrar has no stale multi-build-cycle history to
    begin with on a first-time install."""
    run(["killall", "-9", "AudioComponentRegistrar"])


def run_dependency_and_arch_checks(bundle: Path, require_arch: str) -> bool:
    ok = True
    homebrew = run([sys.executable, str(REPO_ROOT / "scripts" / "check_homebrew_dependencies.py"), str(bundle)])
    print(homebrew.stdout.strip())
    if homebrew.returncode != 0:
        ok = False

    arch = run([sys.executable, str(REPO_ROOT / "scripts" / "verify_architecture.py"),
                "--bundle", str(bundle), "--require", require_arch])
    print(arch.stdout.strip())
    if arch.returncode != 0:
        ok = False

    return ok


def codesign_status(bundle: Path) -> str:
    result = run(["codesign", "--verify", "--deep", "--strict", str(bundle)])
    if result.returncode == 0:
        return "valid (satisfies its Designated Requirement)"
    return f"NOT VALID -- {result.stderr.strip().splitlines()[-1] if result.stderr else 'unknown'}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--format", required=True, choices=["au", "vst3"])
    parser.add_argument("--require-arch", default="arm64")
    parser.add_argument("--build-release-dir", type=Path, default=BUILD_ARM64,
                        help="Release artifact directory containing AU/ and VST3/ "
                             "(defaults to the legacy build-arm64 Release directory).")
    parser.add_argument("--check-only", action="store_true",
                         help="Do not install anything -- only compare the current build tree "
                              "artifact against whatever is currently installed, and report drift.")
    parser.add_argument("--refresh-registrar", action="store_true",
                         help="DEV-ONLY: killall -9 AudioComponentRegistrar after install (AU only). "
                              "Never wire this into a customer-facing installer.")
    parser.add_argument("--auval", action="store_true", help="Run auval after install/verify (AU only).")
    args = parser.parse_args()

    build_bundle = args.build_release_dir / BUILD_SUBDIR[args.format] / (BUNDLE_NAME + BUNDLE_SUFFIX[args.format])
    install_dir = INSTALL_DIRS[args.format]
    installed_bundle = install_dir / (BUNDLE_NAME + BUNDLE_SUFFIX[args.format])

    print("=" * 70)
    print(f"INSTALL-AND-VERIFY PIPELINE -- format={args.format}")
    print("=" * 70)

    if not build_bundle.exists():
        print(f"FAIL: build artifact not found at {build_bundle} -- build it first.")
        return 1

    print(f"\n[1/6] BUILD ARTIFACT: {build_bundle}")
    if not run_dependency_and_arch_checks(build_bundle, args.require_arch):
        print("FAIL: build artifact failed dependency/architecture checks -- refusing to install a bad artifact.")
        return 1
    build_identity = bundle_identity(build_bundle)
    print(f"  main executable sha256: {build_identity['main_executable_sha256'][:16]}...")
    print(f"  architecture: {build_identity['main_executable_arch']}")
    print(f"  {build_identity['dylib_count']} bundled dylib(s)")

    if args.check_only:
        print(f"\n[2/6] CHECK-ONLY MODE -- comparing against currently installed: {installed_bundle}")
        if not installed_bundle.exists():
            print("FAIL: nothing is currently installed at that path -- cannot compare. "
                  "Run without --check-only to install.")
            return 1
        installed_identity = bundle_identity(installed_bundle)
        diffs = compare_identity(build_identity, installed_identity)
        if diffs:
            print("\nSTALE INSTALL DETECTED -- installed artifact differs from current build artifact:")
            for d in diffs:
                print(f"  - {d}")
            print("\nRefusing to treat the installed artifact as current. Re-run without "
                  "--check-only to install the current build fresh before validating further "
                  "(e.g. before auval).")
            return 1
        print("OK: installed artifact is IDENTICAL to the current build artifact (hash-for-hash).")
        return 0

    print(f"\n[2/6] INSTALL: fresh rm+ditto copy into {install_dir} (never incremental)")
    installed_bundle = install_fresh(build_bundle, install_dir, BUNDLE_SUFFIX[args.format])
    print(f"  installed: {installed_bundle}")

    print(f"\n[3/6] VERIFY INSTALLED ARTIFACT: {installed_bundle}")
    if not run_dependency_and_arch_checks(installed_bundle, args.require_arch):
        print("FAIL: freshly installed artifact failed dependency/architecture checks against the "
              "INSTALLED path (not just the build tree) -- this would have been missed by any guard "
              "that only ever checks the build tree.")
        return 1
    installed_identity = bundle_identity(installed_bundle)

    print(f"\n[4/6] COMPARE BUILD vs INSTALLED (deterministic hash manifest, not filenames/mtimes)")
    diffs = compare_identity(build_identity, installed_identity)
    if diffs:
        print("FAIL: installed artifact does not match the build artifact immediately after install "
              "-- the install step itself is broken:")
        for d in diffs:
            print(f"  - {d}")
        return 1
    print("OK: BUILT ARTIFACT == INSTALLED ARTIFACT (main executable hash, architecture, "
          f"{installed_identity['dylib_count']} dylib hashes, full file manifest all match).")

    codesign_result = codesign_status(installed_bundle)
    print(f"  codesign --verify --deep --strict: {codesign_result}")

    if args.refresh_registrar:
        if args.format != "au":
            print("\n[5/6] --refresh-registrar ignored (only meaningful for AU)")
        else:
            print("\n[5/6] REFRESH AUDIO COMPONENT STATE (dev-only): killall -9 AudioComponentRegistrar")
            refresh_audio_component_registrar()
    else:
        print("\n[5/6] registrar refresh skipped (pass --refresh-registrar to force one, AU only, dev-only)")

    if args.auval:
        if args.format != "au":
            print("\n[6/6] --auval ignored (only meaningful for AU)")
        else:
            print("\n[6/6] AUVAL against the just-verified installed component")
            auval_result = run(["auval", "-v", "aufx", "AtSm", "NDSP"])
            print(auval_result.stdout)
            if auval_result.returncode != 0 or "PASS" not in auval_result.stdout or "FAIL" in auval_result.stdout:
                print("FAIL: auval did not report a clean PASS.")
                return 1
            print("auval: PASS")
    else:
        print("\n[6/6] auval skipped (pass --auval to run it)")

    print("\n" + "=" * 70)
    report = {
        "format": args.format,
        "build_bundle": str(build_bundle),
        "installed_bundle": str(installed_bundle),
        "architecture": installed_identity["main_executable_arch"],
        "main_executable_sha256": installed_identity["main_executable_sha256"],
        "dylib_count": installed_identity["dylib_count"],
        "codesign": codesign_result,
        "built_equals_installed": True,
    }
    print("ARTIFACT IDENTITY REPORT:")
    print(json.dumps(report, indent=2))
    print("\nPIPELINE PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
