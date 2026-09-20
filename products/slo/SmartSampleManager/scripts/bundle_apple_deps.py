#!/usr/bin/env python3
"""
Bundles Homebrew-resolved dynamic libraries (TagLib, ONNX Runtime,
libsodium) AND their transitive Homebrew dependencies into a plugin/app
bundle's Contents/Frameworks/, rewriting every load command to @rpath or
@loader_path instead of the original build-time absolute Homebrew path --
see docs/RUNTIME_DEPENDENCY_STRATEGY.md.

Phase 5.5 replacement for cmake/BundleAppleDeps.cmake (deleted -- this
supersedes it). That script only bundled the three top-level libraries and
rewrote the main executable's direct references to them; it never
inspected what THOSE libraries themselves link against. Found via
scripts/check_homebrew_dependencies.py (new this phase): libonnxruntime.dylib
transitively links ~90 Homebrew-installed abseil/protobuf/re2 dylibs that
were never bundled or rewritten -- a customer machine without Homebrew
would fail to load the plugin despite the top-level libs being "bundled."
This script walks the full transitive dependency graph, not just the top
level.

Invoked via a POST_BUILD custom command (see CMakeLists.txt).

Usage:
    python3 bundle_apple_deps.py --bundle-content-dir <dir> --exe-path <path> --libs <lib1,lib2,...>
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

# Paths that mean "resolved from a package manager on THIS machine" --
# everything under these must be bundled and rewritten, never left as a
# runtime dependency. System paths (/usr/lib, /System/Library/Frameworks)
# are always present on any real macOS install and are deliberately left
# alone.
HOMEBREW_PATH_PREFIXES = (
    "/usr/local/opt/",
    "/usr/local/lib/",
    "/usr/local/Cellar/",
    "/opt/homebrew/opt/",
    "/opt/homebrew/lib/",
    "/opt/homebrew/Cellar/",
)


def is_bundleable(path: str) -> bool:
    return path.startswith(HOMEBREW_PATH_PREFIXES)


def otool_own_install_name(path: Path) -> str:
    """The dylib's own LC_ID_DYLIB, i.e. what other binaries embed when
    they link against it -- not necessarily the same as `path` itself
    (see the find_library()-vs-LC_ID_DYLIB mismatch note below)."""
    output = subprocess.run(["otool", "-D", str(path)], capture_output=True, text=True, check=True).stdout
    lines = output.strip().splitlines()
    return lines[1].strip() if len(lines) > 1 else str(path)


def otool_dependencies(path: Path) -> list[str]:
    output = subprocess.run(["otool", "-L", str(path)], capture_output=True, text=True, check=True).stdout
    # First line is the file's own path/id, not a dependency.
    return [line.strip().split(" ", 1)[0] for line in output.strip().splitlines()[1:]]


def bundle(bundle_content_dir: Path, exe_path: Path, top_level_libs: list[str]) -> None:
    frameworks_dir = bundle_content_dir / "Frameworks"
    frameworks_dir.mkdir(parents=True, exist_ok=True)

    processed_names: set[str] = set()
    # original absolute source path -> bundled dest path, for the
    # top-level libs specifically (needed for the exe-rewrite step below).
    top_level_dest_by_source: dict[str, Path] = {}

    queue: list[str] = list(top_level_libs)
    is_top_level = {lib: True for lib in top_level_libs}

    while queue:
        source_path_str = queue.pop(0)
        source_path = Path(source_path_str)
        if not source_path.exists():
            print(f"WARNING: dependency not found at {source_path}, skipping")
            continue

        lib_name = source_path.name
        if lib_name in processed_names:
            continue
        processed_names.add(lib_name)

        dest = frameworks_dir / lib_name
        shutil.copy2(source_path, dest)
        dest.chmod(dest.stat().st_mode | 0o200)  # ensure writable -- Homebrew dylibs are often 444

        if is_top_level.get(source_path_str):
            top_level_dest_by_source[source_path_str] = dest

        subprocess.run(["install_name_tool", "-id", f"@rpath/{lib_name}", str(dest)], check=False)

        for dep in otool_dependencies(dest):
            if not is_bundleable(dep):
                continue
            # Resolve symlinks BEFORE computing the name used for the
            # rewrite -- Homebrew's /usr/local/opt/x/lib/libx.dylib is
            # typically a symlink into ../Cellar/x/<version>/lib/libx.Y.Z.dylib,
            # a DIFFERENT filename. Resolving only when queuing (as this
            # used to do) meant the rewritten reference used the symlink's
            # short name while the file actually copied into Frameworks/
            # used the resolved long name -- a real, launch-breaking bug
            # found this phase: the app failed to start with "Library not
            # loaded: @loader_path/libre2.11.dylib" because the bundled
            # file was actually named libre2.11.0.0.dylib. Resolving once,
            # up front, keeps the rewrite and the copy consistent.
            resolved_dep = Path(dep).resolve()
            dep_name = resolved_dep.name
            subprocess.run(
                ["install_name_tool", "-change", dep, f"@loader_path/{dep_name}", str(dest)],
                check=False,
            )
            if dep_name not in processed_names:
                queue.append(str(resolved_dep))

    # Rewrite the main executable's direct references to the top-level libs.
    # Uses each top-level lib's own LC_ID_DYLIB (queried from the ORIGINAL,
    # unmodified source file) as the -change target, since that's what the
    # executable actually embeds -- which can differ from the find_library()
    # path CMake resolved (see docs/RUNTIME_DEPENDENCY_STRATEGY.md).
    for source_path_str, dest in top_level_dest_by_source.items():
        install_name = otool_own_install_name(Path(source_path_str))
        subprocess.run(
            ["install_name_tool", "-change", install_name, f"@rpath/{dest.name}", str(exe_path)],
            check=False,
        )

    # Add the rpath once -- install_name_tool errors ("would duplicate
    # path") on re-adding an existing one, which a POST_BUILD step
    # re-running on every incremental build would otherwise hit constantly.
    otool_l_output = subprocess.run(["otool", "-l", str(exe_path)], capture_output=True, text=True, check=True).stdout
    if "@loader_path/../Frameworks" not in otool_l_output:
        subprocess.run(
            ["install_name_tool", "-add_rpath", "@loader_path/../Frameworks", str(exe_path)], check=False
        )


def resign_bundle(bundle_content_dir: Path) -> None:
    """RECOVERY PHASE R1 fix (see docs/SLO_LOST_WORK_RECOVERY_MANIFEST.md):
    every install_name_tool call above prints "changes being made to the
    file will invalidate the code signature" -- and it means it. Left
    unsigned, macOS's code-signing enforcement kills the host process with
    SIGKILL ("Code Signature Invalid" / CODESIGNING "Invalid Page") the
    moment it tries to execute a code page from one of the rewritten
    dylibs. This was never caught by any existing build-time check because
    every one of those checks only inspects load-command paths, not
    signature validity -- the plugin builds cleanly, `auval` (or an actual
    DAW) is what discovers it, as a SIGKILL with no earlier signal.
    Deep ad-hoc (`-s -`) re-signs the whole bundle -- including every dylib
    install_name_tool just touched -- as the final step, after all rewrites
    are done. Ad-hoc is correct for local dev/CI builds; a real
    Developer-ID signing pass for release artifacts happens elsewhere (see
    scripts/signing_preflight.py) and should re-sign again after this.
    """
    bundle_root = bundle_content_dir.parent  # Contents/ -> the .component/.vst3/.app itself
    subprocess.run(["codesign", "--force", "--deep", "-s", "-", str(bundle_root)], check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-content-dir", required=True)
    parser.add_argument("--exe-path", required=True)
    parser.add_argument("--libs", required=True, help="comma-separated absolute paths to top-level dylibs")
    args = parser.parse_args()

    bundle_content_dir = Path(args.bundle_content_dir)
    bundle(
        bundle_content_dir,
        Path(args.exe_path),
        [lib for lib in args.libs.split(",") if lib],
    )
    resign_bundle(bundle_content_dir)


if __name__ == "__main__":
    main()
