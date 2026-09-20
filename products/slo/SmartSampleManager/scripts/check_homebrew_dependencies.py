#!/usr/bin/env python3
"""
Homebrew dependency guard -- Phase 5.5, Section 64. Extended Phase 7 to
also verify every @loader_path/@rpath reference actually resolves to a
file present in the bundle.

Scans a built macOS bundle's executable(s) and dylibs for load-command
references to developer-machine-only paths (Homebrew, MacPorts, a
non-bundled absolute dev path). If any of the bundled dependencies
(TagLib/ONNX Runtime/libsodium) still reference an external Homebrew path
instead of the bundle's own @rpath-relative Frameworks/ copy
(scripts/bundle_apple_deps.py's job), a customer machine without Homebrew
installed would fail to launch the plugin -- this check exists to catch
that before a release ships, not after a support ticket.

Phase 7 addition, found the hard way: this check previously verified only
that no FORBIDDEN path was referenced -- it never verified that every
@loader_path/@rpath reference actually resolves to a real file in the
bundle. A real bug slipped through every previous "PASS" as a result:
bundle_apple_deps.py had a symlink-resolution mismatch that rewrote a
reference to "libre2.11.dylib" while the file it actually copied into
Frameworks/ was named "libre2.11.0.0.dylib" -- a launch-time crash
("Library not loaded") that no static forbidden-path scan could ever
catch, since the rewritten reference was never a Homebrew path to begin
with. Caught only by actually launching the built app. `check_missing_deps`
below closes this gap going forward: it resolves every @loader_path/@rpath
reference against the bundle and fails if the target file doesn't exist.

This is a real, automated check -- it invokes `otool -L` on every
Mach-O binary inside the bundle and inspects the actual linked paths, not
a description of what should be true.

RECOVERY PHASE R1 addition (see docs/SLO_LOST_WORK_RECOVERY_MANIFEST.md,
section 33 of the recovery brief): this script previously checked ONLY
forbidden load-command paths, never actual architecture. A real,
previously-diagnosed failure mode this missed entirely: a clean arm64
configure resolving a dependency against the x86_64 Homebrew prefix
(/usr/local) instead of the arm64 one (/opt/homebrew) is now caught much
earlier by CMakeLists.txt's ssm_verify_dylib_arch() preflight (at configure
time, before any of the ~14-minute build even starts) -- but this script is
the last line of defense against the SAME class of problem surviving into a
built/bundled artifact by some other path (a stale CMake cache, a hand-run
bundling step, a dependency that changed after configure). check_bundle_arch()
below verifies every Mach-O file actually inside the bundle contains an
arm64 slice, independent of and in addition to the load-command-path check.

Usage:
    python3 scripts/check_homebrew_dependencies.py <bundle_path>
Exits 0 if no forbidden paths are referenced, every @loader_path/@rpath
reference resolves to a real file, AND every Mach-O file in the bundle is
arm64, 1 otherwise.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

FORBIDDEN_PATH_PREFIXES = (
    "/opt/homebrew",
    "/usr/local/Cellar",
    "/usr/local/opt",
    "/usr/local/lib",  # Homebrew's traditional Intel-Mac prefix
)


def find_macho_files(bundle_path: Path) -> list[Path]:
    macho_files = []
    for path in bundle_path.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            result = subprocess.run(["file", "-b", str(path)], capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError:
            continue
        if "Mach-O" in result.stdout:
            macho_files.append(path)
    return macho_files


def check_binary(path: Path, bundle_path: Path) -> list[str]:
    result = subprocess.run(["otool", "-L", str(path)], capture_output=True, text=True, check=True)
    violations = []
    for line in result.stdout.splitlines()[1:]:  # first line is the binary's own path
        linked_path = line.strip().split(" ", 1)[0]
        if linked_path.startswith(FORBIDDEN_PATH_PREFIXES):
            violations.append(f"{path.relative_to(bundle_path)}: links {linked_path}")
    return violations


def check_missing_deps(path: Path, bundle_path: Path, contents_dir: Path) -> list[str]:
    """Resolves every @loader_path/@rpath reference and confirms the
    target file actually exists -- a reference can be perfectly
    Homebrew-free and still be broken if it points at a filename that was
    never actually copied into the bundle (the exact bug this check was
    added to catch)."""
    frameworks_dir = contents_dir / "Frameworks"
    result = subprocess.run(["otool", "-L", str(path)], capture_output=True, text=True, check=True)
    missing = []
    for line in result.stdout.splitlines()[1:]:
        linked_path = line.strip().split(" ", 1)[0]
        if linked_path.startswith("@loader_path/"):
            target = path.parent / linked_path.removeprefix("@loader_path/")
        elif linked_path.startswith("@rpath/"):
            target = frameworks_dir / linked_path.removeprefix("@rpath/")
        else:
            continue
        if not target.exists():
            missing.append(f"{path.relative_to(bundle_path)}: references {linked_path} -> {target} (MISSING)")
    return missing


def check_bundle_arch(path: Path, bundle_path: Path, expected_arch: str = "arm64") -> list[str]:
    """RECOVERY PHASE R1: fails if this Mach-O file does not contain the
    expected architecture's slice. Uses `file` (not otool) since it reports
    architecture directly and works for both thin and fat/universal
    binaries without extra parsing."""
    result = subprocess.run(["file", "-b", str(path)], capture_output=True, text=True, check=True)
    if expected_arch not in result.stdout:
        return [f"{path.relative_to(bundle_path)}: not {expected_arch} (file reports: {result.stdout.strip()})"]
    return []


def main() -> int:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <bundle_path>", file=sys.stderr)
        return 2

    bundle_path = Path(sys.argv[1])
    if not bundle_path.exists():
        print(f"ERROR: {bundle_path} does not exist", file=sys.stderr)
        return 2

    macho_files = find_macho_files(bundle_path)
    if not macho_files:
        print(f"ERROR: no Mach-O binaries found inside {bundle_path} -- check the path", file=sys.stderr)
        return 2

    contents_dir = bundle_path / "Contents"
    all_violations = []
    all_missing = []
    all_wrong_arch = []
    for macho_file in macho_files:
        all_violations.extend(check_binary(macho_file, bundle_path))
        all_missing.extend(check_missing_deps(macho_file, bundle_path, contents_dir))
        all_wrong_arch.extend(check_bundle_arch(macho_file, bundle_path))

    if all_violations:
        print(f"HOMEBREW DEPENDENCY GUARD FAILED for {bundle_path}:")
        for v in all_violations:
            print(f"  - {v}")
        print()
        print(
            "A customer machine without these paths installed will fail to load this "
            "plugin. Check scripts/bundle_apple_deps.py ran and rewrote these load commands."
        )

    if all_missing:
        print(f"MISSING DEPENDENCY FILES in {bundle_path}:")
        for m in all_missing:
            print(f"  - {m}")
        print()
        print(
            "A reference with no Homebrew path can still be broken if the referenced file "
            "was never actually copied into the bundle -- this will crash on launch with "
            "dyld's 'Library not loaded' error, not a Gatekeeper/Homebrew-path problem."
        )

    if all_wrong_arch:
        print(f"WRONG ARCHITECTURE in {bundle_path}:")
        for w in all_wrong_arch:
            print(f"  - {w}")
        print()
        print(
            "A non-arm64 Mach-O file inside an arm64-only bundle will fail to load "
            "(or silently run under Rosetta, masking the real problem) -- almost "
            "always caused by a dependency resolving against the x86_64 Homebrew "
            "prefix (/usr/local) instead of the arm64 one (/opt/homebrew). See "
            "CMakeLists.txt's ssm_verify_dylib_arch() preflight, which should have "
            "caught this earlier at configure time."
        )

    if all_violations or all_missing or all_wrong_arch:
        print("RELEASE FAILS")
        return 1

    print(
        f"OK: {bundle_path} -- {len(macho_files)} Mach-O binary(ies) checked, "
        "no forbidden dependency paths, no missing dependency files, "
        "all arm64."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
