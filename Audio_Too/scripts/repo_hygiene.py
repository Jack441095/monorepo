#!/usr/bin/env python3
"""Repo hygiene checks and local data usage reporting."""

from __future__ import annotations

import argparse
import fnmatch
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MAX_BYTES = 10 * 1024 * 1024

BLOCKED_TRACKED_PATTERNS = (
    "**/__pycache__/**",
    "**/*.pyc",
    "studio/kenn/kenn/data/index/**",
    "studio/kenn/kenn/artifacts/benchmarks/**",
    "studio/kenn/kenn/artifacts/audits/**",
    "studio/kenn/kenn/artifacts/training/*.json",
    "studio/kenn/kenn/artifacts/training/*.jsonl",
    "studio/kenn/kenn/Training_Data_PDF/*.pdf",
)

ALLOWLIST_PATTERNS = (
    "studio/kenn/kenn/data/index/README.md",
    "studio/kenn/kenn/Training_Data_PDF/audio-too-workflow-checklist.pdf",
    # Default instrument/drone samples the realtime player loads at startup —
    # not generated artifacts, exempt from the tracked-file size limit.
    "studio/audiogen/audiogen/samples/default/*.wav",
    # Trained audio-embedding model SmartSampleManager loads at runtime for
    # similarity search — a required application asset, not a generated
    # build artifact, same class of exception as the audiogen samples above.
    # See studio/vst3_plugins/SmartSampleManager/Models/README.md for what
    # it is, its license, and how it's verified.
    "studio/vst3_plugins/SmartSampleManager/Models/panns_cnn10_embedding.onnx.data",
)

LOCAL_DATA_TARGETS = (
    ("KENN PDFs", "studio/kenn/kenn/Training_Data_PDF", "Keep if you want offline index rebuilds; safe to delete downloaded manuals and rerun setup/download scripts."),
    ("KENN index", "studio/kenn/kenn/data/index", "Rebuildable with python main.py ableton build."),
    ("KENN artifacts", "studio/kenn/kenn/artifacts", "Benchmark, audit, and training outputs. Keep only runs you still need."),
    ("Mix Review data", "studio/agents/MixReview/data/mix_reviews", "Local uploads, reports, and references. Back up client work before deleting."),
    ("AudioGen exports", "studio/audiogen/audiogen/exports", "Rendered local audio output. Safe to archive outside git."),
    ("AudioGen songs", "studio/audiogen/audiogen/songs", "Generated song/session output. Safe to archive outside git."),
    ("AudioGen runs", "studio/audiogen/audiogen/artifacts/runs", "Generated run artifacts. Safe to delete after audits."),
    ("AudioGen datasets", "studio/audiogen/audiogen/artifacts/datasets", "Generated training datasets. Rebuildable if source data remains."),
)


@dataclass(frozen=True)
class HygieneIssue:
    path: str
    reason: str


@dataclass(frozen=True)
class TrackedFile:
    path: str
    size: int


@dataclass(frozen=True)
class LocalDataTarget:
    label: str
    path: str
    exists: bool
    size: int
    note: str


def git_ls_files(root: Path = ROOT) -> list[str]:
    proc = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return [item for item in proc.stdout.decode("utf-8").split("\0") if item]


def matches_any(path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def tracked_file_issues(paths: list[str], *, root: Path = ROOT, max_bytes: int = DEFAULT_MAX_BYTES) -> list[HygieneIssue]:
    issues: list[HygieneIssue] = []
    for path in paths:
        if matches_any(path, ALLOWLIST_PATTERNS):
            continue
        if matches_any(path, BLOCKED_TRACKED_PATTERNS):
            issues.append(HygieneIssue(path, "generated/local artifact pattern is tracked"))
            continue
        full_path = root / path
        try:
            size = full_path.stat().st_size
        except OSError:
            continue
        if size > max_bytes:
            issues.append(HygieneIssue(path, f"tracked file is larger than {max_bytes // (1024 * 1024)} MB"))
    return issues


def tracked_files(paths: list[str], *, root: Path = ROOT) -> list[TrackedFile]:
    files: list[TrackedFile] = []
    for path in paths:
        full_path = root / path
        try:
            size = full_path.stat().st_size
        except OSError:
            continue
        files.append(TrackedFile(path=path, size=size))
    return sorted(files, key=lambda item: item.size, reverse=True)


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def directory_size(path: Path) -> int:
    total = 0
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = [name for name in dirnames if name not in {".git", ".venv"}]
        for filename in filenames:
            try:
                total += (Path(dirpath) / filename).stat().st_size
            except OSError:
                continue
    return total


def local_data_targets(*, root: Path = ROOT) -> list[LocalDataTarget]:
    targets: list[LocalDataTarget] = []
    for label, relative_path, note in LOCAL_DATA_TARGETS:
        path = root / relative_path
        exists = path.exists()
        targets.append(
            LocalDataTarget(
                label=label,
                path=relative_path,
                exists=exists,
                size=directory_size(path) if exists else 0,
                note=note,
            )
        )
    return sorted(targets, key=lambda item: item.size, reverse=True)


def print_size_report(paths: list[str], *, root: Path = ROOT, limit: int = 20) -> None:
    print(f"largest tracked files (top {limit}):")
    for item in tracked_files(paths, root=root)[:limit]:
        print(f"- {human_size(item.size):>9}  {item.path}")


def print_local_data_doctor(*, root: Path = ROOT) -> None:
    print("local data doctor:")
    for target in local_data_targets(root=root):
        state = human_size(target.size) if target.exists else "missing"
        print(f"- {target.label}: {state}  {target.path}")
        print(f"  {target.note}")


def run_check(*, max_mb: int) -> int:
    max_bytes = max_mb * 1024 * 1024
    issues = tracked_file_issues(git_ls_files(ROOT), root=ROOT, max_bytes=max_bytes)
    if not issues:
        print("repo hygiene ok")
        return 0
    print("repo hygiene failed:")
    for issue in issues:
        print(f"- {issue.path}: {issue.reason}")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    # Bare invocation (no subcommand) is documented to default to "check",
    # but argparse only populates a subparser's own defaults (--max-mb) when
    # that subparser is actually selected on the command line -- with none
    # given, `args.max_mb` didn't exist at all and `run_check(max_mb=args.max_mb)`
    # below crashed with AttributeError. Inserting "check" into argv when no
    # command was typed makes argparse apply that subparser's real defaults.
    # `argv is None` mirrors parse_args' own None-means-sys.argv convention.
    resolved_argv = list(sys.argv[1:]) if argv is None else list(argv)
    if not resolved_argv or resolved_argv[0] not in {"check", "sizes", "doctor", "all", "-h", "--help"}:
        resolved_argv = ["check", *resolved_argv]
    sub = parser.add_subparsers(dest="command")

    check = sub.add_parser("check", help="Fail if generated or oversized files are tracked.")
    check.add_argument("--max-mb", type=int, default=10, help="Maximum allowed tracked file size in MB.")

    sizes = sub.add_parser("sizes", help="Print the largest tracked files.")
    sizes.add_argument("--limit", type=int, default=20)

    sub.add_parser("doctor", help="Show local-only data folders and cleanup guidance.")

    all_cmd = sub.add_parser("all", help="Run check, size report, and local data doctor.")
    all_cmd.add_argument("--max-mb", type=int, default=10, help="Maximum allowed tracked file size in MB.")
    all_cmd.add_argument("--limit", type=int, default=20)

    args = parser.parse_args(resolved_argv)

    command = args.command or "check"
    if command == "check":
        return run_check(max_mb=args.max_mb)
    if command == "sizes":
        print_size_report(git_ls_files(ROOT), root=ROOT, limit=args.limit)
        return 0
    if command == "doctor":
        print_local_data_doctor(root=ROOT)
        return 0
    if command == "all":
        status = run_check(max_mb=args.max_mb)
        print()
        print_size_report(git_ls_files(ROOT), root=ROOT, limit=args.limit)
        print()
        print_local_data_doctor(root=ROOT)
        return status
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
