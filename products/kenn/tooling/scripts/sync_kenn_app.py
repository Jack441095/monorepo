#!/usr/bin/env python3
"""Mirror a committed KENN tree without rewriting the sharing repository's history."""

from __future__ import annotations

import argparse
import os
from pathlib import PurePosixPath
import posixpath
import re
import subprocess

from scripts import check_personal_paths


SOURCE_REPOSITORY = "Nite-DSP/monorepo"
SECRET = re.compile(
    rb"(?<![A-Za-z0-9_-])(?:AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9]{20,}"
    rb"|xox[bp]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)"
)
PRIVATE_SUFFIXES = {".wav", ".aiff", ".aif", ".mp3", ".flac", ".gguf", ".safetensors", ".pt", ".pth"}


def git(*args: str, input: str | None = None) -> str:
    result = subprocess.run(["git", *args], input=input, text=True, capture_output=True)
    if result.returncode:
        # Git errors can include an authenticated remote URL; keep those out of CI logs.
        raise RuntimeError(f"git {args[0]} failed (exit {result.returncode})")
    return result.stdout.strip()


def fetch_branch(remote: str, branch: str) -> str | None:
    ref = f"refs/heads/{branch}"
    advertised = git("ls-remote", "--heads", remote, ref)
    if not advertised:
        return None
    git("fetch", "--quiet", "--no-tags", remote, ref)
    return git("rev-parse", "FETCH_HEAD")


def check_export(tree: str) -> None:
    findings = set()
    for entry in git("ls-tree", "-r", "-z", tree).split("\0"):
        if not entry:
            continue
        metadata, name = entry.split("\t", 1)
        mode, kind, oid = metadata.split()
        path = PurePosixPath(name)
        if kind != "blob":
            findings.add(name)
            continue
        if path.parts[0] in {"runtime", ".runtime", "models"} or path.suffix.lower() in PRIVATE_SUFFIXES:
            findings.add(name)
            continue
        blob = subprocess.run(["git", "cat-file", "blob", oid], capture_output=True, check=True).stdout
        if mode == "120000":
            link = blob.decode("utf-8", "replace")
            resolved = posixpath.normpath(str(path.parent / link))
            if link.startswith("/") or resolved == ".." or resolved.startswith("../"):
                findings.add(name)
            else:
                git("cat-file", "-e", f"{tree}:{resolved}")
        if SECRET.search(blob):
            findings.add(name)
        if path.name in check_personal_paths.SELF_EXEMPT:
            continue
        if path.suffix.lower() in check_personal_paths._TEXT_SUFFIXES:
            text = blob.decode("utf-8", "replace")
            if check_personal_paths.path_findings(text) or check_personal_paths.remote_host_findings(text):
                findings.add(name)
    if findings:
        raise RuntimeError("Export blocked; review these paths: " + ", ".join(sorted(findings)))


def previous_source(destination: str, branch: str) -> str:
    marker = git("log", "-1", "--format=%H", "--grep=^Sync KENN from Nite-DSP/monorepo branch ", destination)
    if not marker:
        raise RuntimeError("Destination needs a reviewed reconciliation PR before automatic sync")
    match = re.fullmatch(
        r"Sync KENN from Nite-DSP/monorepo branch (\S+) source ([0-9a-f]{40})",
        git("show", "-s", "--format=%B", marker),
    )
    if not match or match[1] != branch:
        raise RuntimeError("Destination source metadata does not match this branch")
    if git("rev-parse", f"{destination}^{{tree}}") != git("rev-parse", f"{marker}^{{tree}}"):
        raise RuntimeError("Destination has independent edits; import and review them before syncing")
    return match[2]


def synchronize(args: argparse.Namespace) -> str:
    for branch in [args.branch, args.destination_branch or args.branch, args.base_branch]:
        git("check-ref-format", f"refs/heads/{branch}")
    source = git("rev-parse", "--verify", f"{args.source_ref}^{{commit}}")
    tree = git("rev-parse", f"{source}:products/kenn")
    if git("cat-file", "-t", tree) != "tree":
        raise RuntimeError("Source must contain the committed products/kenn directory")
    check_export(tree)
    target = args.destination_branch or args.branch
    if target != args.branch and not args.reconcile:
        raise RuntimeError("A different destination branch is only allowed for a reconciliation PR")
    destination = fetch_branch(args.remote, target)
    if args.reconcile and (destination or target == args.branch):
        raise RuntimeError("Reconciliation must use a new review branch, never replace an existing branch")
    if destination:
        previous = previous_source(destination, args.branch)
        result = subprocess.run(["git", "merge-base", "--is-ancestor", previous, source], capture_output=True)
        if result.returncode:
            raise RuntimeError("Source was rewritten or changed branches; review before syncing")
        if git("rev-parse", f"{destination}^{{tree}}") == tree:
            print(f"{target} already matches committed KENN")
            return destination
        parent = destination
    else:
        if not (args.bootstrap or args.reconcile):
            raise RuntimeError("New destination branch requires --bootstrap or --reconcile")
        if target == "main":
            raise RuntimeError("Establish main through a reviewed reconciliation PR")
        parent = fetch_branch(args.remote, args.base_branch)
        if not parent:
            raise RuntimeError("Sharing repository base branch does not exist")
    message = f"Sync KENN from {SOURCE_REPOSITORY} branch {args.branch} source {source}\n"
    commit = git("commit-tree", tree, "-p", parent, input=message)
    if args.push:
        # The ordinary fast-forward push rejects a colleague's concurrent update.
        git("push", args.remote, f"{commit}:refs/heads/{target}")
        published = fetch_branch(args.remote, target)
        if published != commit or git("rev-parse", f"{published}^{{tree}}") != tree:
            raise RuntimeError("Destination changed during verification; check the sharing branch")
        print(f"Synced {target}: source {source[:12]}, destination {commit[:12]}, exact tree match")
    else:
        print(f"Prepared {target}: {commit}; use --push after review")
    return commit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-ref", default="HEAD")
    parser.add_argument("--branch", required=True)
    parser.add_argument("--remote", default="kenn-app")
    parser.add_argument("--base-branch", default="main")
    parser.add_argument("--destination-branch")
    parser.add_argument("--bootstrap", action="store_true")
    parser.add_argument("--reconcile", action="store_true")
    parser.add_argument("--push", action="store_true")
    args = parser.parse_args()
    os.chdir(git("rev-parse", "--show-toplevel"))
    try:
        synchronize(args)
    except RuntimeError as exc:
        parser.exit(1, f"{exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
