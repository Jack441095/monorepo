#!/usr/bin/env python3
"""Release manifest enforcement for SLO plugin bundles.

Phase 2, Section 79 of the master prompt: "Convert the existing documentary
release manifest into something the build/release system can verify
automatically. The pipeline should know exactly which files may ship.
Unexpected artifact: RELEASE FAILS." Also directly implements Section 44's
"Release Artifact Assertion" -- this is the concrete check that would catch
a sibling-plugin artifact (AudioToo_Reverb, KENNMixAssistant, MidiGenerator)
accidentally ending up in a SmartSampleManager release build.

This is a real, automated check -- not just docs/RELEASE_MANIFEST.md's prose
description of what should ship. Every file inside a built bundle is walked
and compared against an explicit per-format allowlist; anything not on the
list fails the check with a nonzero exit code and a clear message.

Usage:
    python3 verify_release_manifest.py <bundle_path> --format {vst3,au,standalone}

Exits 0 if the bundle's contents exactly match what's expected (allowing for
optional files, e.g. codesign artifacts that may or may not be present on an
unsigned dev build), nonzero with a description of every unexpected file if
not.
"""

from __future__ import annotations

import argparse
import fnmatch
import sys
from pathlib import Path

# Files common to every format. Paths are relative to Contents/.
COMMON_REQUIRED = [
    "Info.plist",
    "PkgInfo",
    "MacOS/SLO",
    "Resources/Icon.icns",
    "Resources/panns_cnn10_embedding.onnx",
    "Resources/panns_cnn10_embedding.onnx.data",
    "Resources/THIRD_PARTY_NOTICES.txt",
]

# Bundled runtime dependencies -- see docs/RUNTIME_DEPENDENCY_STRATEGY.md.
# Required once codesigning is in place; on an unsigned/ad-hoc dev build
# these are still expected to be present since the POST_BUILD bundling step
# always runs, so kept in REQUIRED rather than OPTIONAL.
COMMON_REQUIRED += [
    "Frameworks/libtag.dylib",
    "Frameworks/libonnxruntime.dylib",
    "Frameworks/libsodium.dylib",
]

# Optional files: may or may not be present depending on build
# configuration (signed vs. unsigned, format-specific JUCE resources) without
# that being a release-manifest violation.
COMMON_OPTIONAL = [
    "_CodeSignature/CodeResources",
]

FORMAT_SPECIFIC_REQUIRED = {
    "vst3": ["Resources/moduleinfo.json"],
    "au": [],
    "standalone": [],
}

FORMAT_SPECIFIC_OPTIONAL = {
    "vst3": [],
    "au": [],
    # JUCE's Standalone wrapper adds this for its native "recent files" menu;
    # present or absent depending on JUCE version/config, not a release concern.
    "standalone": ["Resources/RecentFilesMenuTemplate.nib"],
}

# Glob pattern for files allowed without an exact-name entry above.
# Phase 5.5: scripts/bundle_apple_deps.py now bundles the FULL transitive
# Homebrew dependency graph of the three top-level libs (ONNX Runtime alone
# pulls in ~90 abseil/protobuf/re2 dylibs), not just the top level --
# see docs/PHASE_5_5_FINAL_SYNTHESIS.md. Listing every one of those by exact
# versioned filename would be fragile (a Homebrew upgrade changes the
# embedded version string in the filename) and isn't the actual thing this
# manifest protects against -- the FORBIDDEN_PATTERNS check below still
# catches a sibling-plugin artifact or dev tooling landing in Frameworks/,
# which is the real risk this manifest exists to prevent.
ALLOWED_PATTERNS = [
    "frameworks/*.dylib",
]

# Glob patterns for files that must NEVER appear, regardless of format --
# the actual sibling-plugin-exclusion assertion from Section 44. Matched
# case-insensitively against the full relative path.
FORBIDDEN_PATTERNS = [
    "*audiotoo_reverb*",
    "*audiotoo_limiter*",
    "*kennmixassistant*",
    "*midigenerator*",
    "*kenn*",
    "*automix*",
    "*audiogen*",
    "*.py",              # no Python tooling belongs in a shipped bundle
    "*licensing_server*",
    "*.db", "*.db-wal", "*.db-shm", "*.sqlite3*",  # no dev cache/DB files
    "*dummy_clap*",       # superseded placeholder model, must never ship
]


def collect_files(bundle_path: Path) -> list[str]:
    contents = bundle_path / "Contents"
    if not contents.is_dir():
        print(f"ERROR: {bundle_path} has no Contents/ directory -- not a valid bundle", file=sys.stderr)
        sys.exit(2)
    return sorted(
        str(p.relative_to(contents))
        for p in contents.rglob("*")
        if p.is_file()
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle_path", type=Path)
    parser.add_argument("--format", required=True, choices=["vst3", "au", "standalone"])
    args = parser.parse_args()

    required = set(COMMON_REQUIRED) | set(FORMAT_SPECIFIC_REQUIRED[args.format])
    optional = set(COMMON_OPTIONAL) | set(FORMAT_SPECIFIC_OPTIONAL[args.format])
    allowed = required | optional

    actual_files = collect_files(args.bundle_path)

    missing_required = sorted(required - set(actual_files))
    unexpected = sorted(
        f
        for f in actual_files
        if f not in allowed and not any(fnmatch.fnmatch(f.lower(), pat) for pat in ALLOWED_PATTERNS)
    )
    forbidden_hits = sorted(
        f for f in actual_files
        if any(fnmatch.fnmatch(f.lower(), pat) for pat in FORBIDDEN_PATTERNS)
    )

    ok = True

    if missing_required:
        ok = False
        print(f"RELEASE MANIFEST VIOLATION: {args.bundle_path} is missing required file(s):", file=sys.stderr)
        for f in missing_required:
            print(f"  - {f}", file=sys.stderr)

    if unexpected:
        ok = False
        print(f"RELEASE MANIFEST VIOLATION: {args.bundle_path} contains unexpected file(s) not on the allowlist:", file=sys.stderr)
        for f in unexpected:
            print(f"  - {f}", file=sys.stderr)
        print("If this file is genuinely supposed to ship, add it to COMMON_REQUIRED/OPTIONAL "
              "or the format-specific list in this script -- do not silently ignore this check.", file=sys.stderr)

    if forbidden_hits:
        ok = False
        print(f"RELEASE MANIFEST VIOLATION: {args.bundle_path} contains explicitly forbidden file(s) "
              "(sibling-plugin artifact, dev tooling, or a superseded placeholder):", file=sys.stderr)
        for f in forbidden_hits:
            print(f"  - {f}", file=sys.stderr)

    if not ok:
        print(f"\nRELEASE FAILS for {args.bundle_path}", file=sys.stderr)
        return 1

    print(f"OK: {args.bundle_path} ({args.format}) matches the release manifest -- "
          f"{len(actual_files)} file(s), all accounted for.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
