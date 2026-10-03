#!/usr/bin/env python3
"""Fetch cloud work and fast-forward a clean local monorepo checkout."""

import argparse
from datetime import datetime, timezone
import fcntl
import os
from pathlib import Path
import subprocess


def git(repo, *args):
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=90,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_SSH_COMMAND": "ssh -o BatchMode=yes -o ConnectTimeout=15"},
    )
    if result.returncode:
        raise RuntimeError(f"git {args[0]} failed (exit {result.returncode}); check network and repository access")
    return result.stdout.strip()


def synchronize(repo):
    repo = Path(repo)
    if not repo.is_dir():
        return "Paused: local drive is unavailable"
    branch = git(repo, "symbolic-ref", "--quiet", "--short", "HEAD")
    head = git(repo, "rev-parse", "HEAD")
    upstream = git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    if not upstream.startswith("origin/"):
        return "Paused: current branch does not track origin"
    remote_branch = upstream[len("origin/"):]
    git(repo, "fetch", "--quiet", "--no-tags", "origin", f"refs/heads/{remote_branch}:refs/remotes/origin/{remote_branch}")
    target = git(repo, "rev-parse", upstream)
    if git(repo, "status", "--porcelain", "--untracked-files=normal"):
        return f"Fetched {remote_branch}; pull paused because local files are changed or untracked"
    # A branch switch during the fetch must never update a different checkout.
    if git(repo, "symbolic-ref", "--quiet", "--short", "HEAD") != branch or git(repo, "rev-parse", "HEAD") != head:
        return "Fetched; pull paused because the checked-out branch changed"
    if head == target:
        return f"Up to date: {branch} at {head[:12]}"
    ancestor = subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", head, target], capture_output=True)
    if ancestor.returncode:
        return f"Fetched {remote_branch}; pull paused because local commits need review"
    git(repo, "merge", "--ff-only", target)
    return f"Updated {branch} to {target[:12]}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--lock", required=True)
    args = parser.parse_args()
    with open(args.lock, "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        try:
            result = synchronize(args.repo)
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            result = f"Paused: {exc}"
        print(f"{datetime.now(timezone.utc).isoformat()} {result}", flush=True)


if __name__ == "__main__":
    main()
