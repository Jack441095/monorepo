#!/usr/bin/env python3
"""
Clean-machine acceptance pre-check -- Phase 5.5, Section 61.

Checks the MECHANICAL preconditions of a distributed build (bundle exists,
dependency linkage, code-sign status, version) that don't require a human
driving a DAW. This is a real, non-destructive check -- it does not
attempt to fake or infer subjective DAW-workflow results
(scan/load/audio/drag-drop/save-reopen), which stay in
docs/DAW_VALIDATION_MATRIX.md as genuinely manual, human-recorded steps
(Section 62: "do not automate subjective DAW workflow checks falsely").

Usage:
    python3 scripts/clean_machine_acceptance.py <path-to-installed-app-or-plugin>
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Resolved relative to this script's own directory, not a repo root two
# levels up -- Phase 5.6: this script is meant to be copied to a clean
# machine standalone (see docs/CLEAN_MACHINE_TEST_PROCEDURE.md), where no
# wider repository checkout exists. Keep it and check_homebrew_dependencies.py
# in the same directory and this resolves correctly either way.
SCRIPT_DIR = Path(__file__).parent


def check(description: str, passed: bool, detail: str = "") -> bool:
    marker = "PASS" if passed else "FAIL"
    line = f"  [{marker}] {description}"
    if detail:
        line += f" -- {detail}"
    print(line)
    return passed


def get_version(bundle_path: Path) -> str | None:
    # `defaults read` requires an absolute path -- a relative one is
    # silently misinterpreted as a domain name rather than a file path.
    plist_path = (bundle_path / "Contents" / "Info.plist").resolve()
    result = subprocess.run(
        ["defaults", "read", str(plist_path), "CFBundleShortVersionString"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def get_codesign_status(bundle_path: Path) -> tuple[bool, str]:
    result = subprocess.run(["codesign", "-dv", str(bundle_path)], capture_output=True, text=True)
    if "code object is not signed" in result.stderr:
        return False, "not signed"
    if result.returncode == 0:
        return True, result.stderr.strip().splitlines()[0] if result.stderr else "signed"
    return False, result.stderr.strip()


def main() -> int:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <path-to-installed-app-or-plugin>", file=sys.stderr)
        return 2

    bundle_path = Path(sys.argv[1])
    print(f"CLEAN MACHINE ACCEPTANCE PRE-CHECK: {bundle_path}")
    print("=" * 60)

    all_ok = True
    all_ok &= check("Bundle exists at the given path", bundle_path.exists())
    if not bundle_path.exists():
        return 1

    version = get_version(bundle_path)
    all_ok &= check("Version readable from Info.plist", version is not None, version or "")

    signed, detail = get_codesign_status(bundle_path)
    check("Code-signed", signed, detail)
    print("    [INFO] Unsigned is EXPECTED until Apple Developer credentials exist -- ")
    print("           this is informational, not a pass/fail gate, at this stage.")

    homebrew_result = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "check_homebrew_dependencies.py"), str(bundle_path)],
        capture_output=True,
        text=True,
    )
    all_ok &= check("No Homebrew/dev-machine dependency paths", homebrew_result.returncode == 0)

    print("=" * 60)
    print("Mechanical pre-check:", "PASS" if all_ok else "FAIL")
    print("This does NOT replace docs/CLEAN_MACHINE_TEST_PROCEDURE.md's manual DAW-workflow steps.")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
