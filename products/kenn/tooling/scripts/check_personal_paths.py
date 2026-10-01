#!/usr/bin/env python3
"""Gate: no owner's home path, no mounted volume and no remote hostname in a tracked file.

    check_personal_paths.py [--root DIR] [--quiet]

Modelled on products/slo/scripts/check_no_personal_paths.sh, which does the same job there, with three changes.

**It runs in CI.** SLO's gate is manual: two SLO docs claim it "fails the build" and nothing invokes it. This is
called from tooling/scripts/ci_verification.sh, which both kenn-core.yml and kenn-ci.yml already run, so a leak
stops the build rather than waiting for someone to remember.

**No debt list.** SLO ships a 124-file ratchet because its 34,722 occurrences sit in dated research reports it had
not got to. KENN's 140 occurrences were 43 files repeating one volume prefix and one username, so those were
rewritten to `~/` on 2026-09-30 and the list would only ever have been an apology. A gate with a debt list needs the
debt scrubbed eventually; this one has nothing to forgive.

**Placeholders are tolerated, with the reason recorded.** KENN's path tests use "/Volumes/X" and "/Users/example" as
the subject of the assertion, and several reports already use "<LOCAL_VOLUME>". Scrubbing those would break the
tests. PLACEHOLDERS below lists the tolerated first path segment; anything else fails.

What it does not do: rewrite history. The original paths are still in git history. That is an owner decision, not
something a gate can do, and it is recorded in the plan rather than pretended away.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

KENN_ROOT = Path(__file__).resolve().parents[2]

# Absolute paths into someone's home directory, or onto a mounted volume -- which is where Jack's Live SSD and his
# stem library live. The negative lookahead lets ".../Shenrendao/" through, because that is a redaction already
# written by hand, not a leak.
_PATTERNS = (
    re.compile(r"/Volumes/(?!\.\.\.(?:[/\s]|$))(?P<segment>[A-Za-z0-9._-]+)/"),
    re.compile(r"/Users/(?!\.\.\.(?:[/\s]|$))(?P<segment>[A-Za-z0-9._-]+)/"),
    re.compile(r"/home/(?!\.\.\.(?:[/\s]|$))(?P<segment>[A-Za-z0-9._-]+)/"),
    re.compile(r"[A-Za-z]:\\Users\\(?!\.\.\.\\)(?P<segment>[^\\\s]+)\\"),
)

# First path segment that names nobody. Every one of these is in use somewhere under products/kenn, and
# test_personal_path_gate.py fails if an entry is added that nothing uses: an unused allowance is a hole.
# "Shared" is macOS's own /Users/Shared, a real directory that carries no username. The rest are the tokens KENN's own
# path tests and diagrams use as stand-ins.
PLACEHOLDERS = frozenset({"...", "X", "example", "KENN", "Other", "person", "Shared"})

# A remote machine, in the two shapes one actually appears in: an scp/ssh destination ("user@host:/path"), and a
# hostname string bound to a variable. The quoted form is required on purpose -- without it `host = os.getenv(...)`
# and `host = parsed.netloc.lower()` in ordinary Python matched, and a variable named host is not a machine.
_USER_AT_HOST = re.compile(r"\b[\w.+-]+@(?P<host>[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9-]+)+)")
_HOST_ASSIGNMENT = re.compile(r"\b(?:host|remote_host|server_host|ssh_host)\s*[:=]\s*"
                               r"[\"'](?:[\w.+-]+@)?(?P<host>[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)[\"']", re.I)
_SSH_CONTEXT = re.compile(r"(?:ssh|scp|rsync|sshpass)\b|StrictHostKeyChecking")
_SCP_DESTINATION = re.compile(r"[\w.+-]+@[A-Za-z0-9.-]+(?:/|:)")
_ALLOWED_HOSTS = frozenset({
    "127.0.0.1", "0.0.0.0", "localhost",
    "ableton.com", "github.com", "githubusercontent.com", "raw.githubusercontent.com", "gitlab.com",
    "pypi.org", "files.pythonhosted.org", "python.org", "docs.python.org", "numpy.org", "scipy.org",
    "developer.mozilla.org", "mozilla.org", "gnu.org", "apache.org", "opensource.org", "w3.org",
    "json-schema.org", "schema.org", "creativecommons.org", "nist.gov", "ieee.org", "aes.audio",
    "ollama.com", "huggingface.co", "hf.co", "kenn.ai", "example.com", "example.org",
})

_TEXT_SUFFIXES = {".css", ".cfg", ".csv", ".html", ".ini", ".js", ".json", ".jsonl", ".md", ".mts", ".py",
                  ".sh", ".toml", ".ts", ".tsx", ".txt", ".xml", ".yaml", ".yml"}
MAX_BYTES = 5_000_000
# This file and its test carry the patterns as literals, so they would otherwise flag themselves.
SELF_EXEMPT = {Path(__file__).name, "test_personal_path_gate.py"}


def tracked_text_files(root: Path) -> list[Path]:
    """Every tracked text file under root, by suffix and size, so a stray binary is not read as text."""
    listed = subprocess.run(["git", "ls-files", "-z", "--", "."], capture_output=True, cwd=root, check=True)
    found = []
    for name in listed.stdout.decode("utf-8", "replace").split("\0"):
        if not name:
            continue
        path = root / name
        if path.name in SELF_EXEMPT or path.suffix.lower() not in _TEXT_SUFFIXES:
            continue
        try:
            if path.stat().st_size > MAX_BYTES:
                continue
        except OSError:
            continue
        found.append(path)
    return sorted(found)


def path_findings(text: str) -> list[str]:
    """Absolute home or volume paths in text, minus the placeholder segments listed above."""
    found = []
    for pattern in _PATTERNS:
        for match in pattern.finditer(text):
            if match.group("segment") not in PLACEHOLDERS:
                found.append(match.group(0).rstrip("/\\"))
    return found


def remote_host_findings(text: str) -> list[str]:
    """Remote hostnames: a host assigned to a variable, or a user@host used as an scp/ssh destination.

    "user@host:/some/path" is flagged on its own line, because a colon then a path is an scp target and an email
    address never is. Everything else needs an ssh/scp/rsync nearby, so an address in prose is left alone.
    """
    found = set()
    for line in text.splitlines():
        for match in _HOST_ASSIGNMENT.finditer(line):
            if match.group("host") not in _ALLOWED_HOSTS:
                found.add(match.group("host"))
        scp_target = bool(_SCP_DESTINATION.search(line))
        if not scp_target and not _SSH_CONTEXT.search(line):
            continue
        for match in _USER_AT_HOST.finditer(line):
            if match.group("host") not in _ALLOWED_HOSTS:
                found.add(match.group("host"))
    return sorted(found)


def scan(root: Path) -> list[tuple[str, str]]:
    """(path relative to root, what was found) for every tracked file carrying a leak."""
    findings = []
    for path in tracked_text_files(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        for found in path_findings(text):
            findings.append((str(path.relative_to(root)), f"personal path {found}"))
        for host in remote_host_findings(text):
            findings.append((str(path.relative_to(root)), f"remote host {host}"))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=KENN_ROOT)
    parser.add_argument("--quiet", action="store_true", help="only print on failure")
    args = parser.parse_args()

    findings = scan(args.root)
    tracked = len(tracked_text_files(args.root))
    if findings:
        print(f"personal-path-gate=FAIL tracked_files={tracked} findings={len(findings)}", file=sys.stderr)
        for name, what in findings:
            print(f"  {name}: {what}", file=sys.stderr)
        print("Rewrite the path as ~/, and take the hostname from KENN_SERVER_TARGET.", file=sys.stderr)
        print("If it belongs to a path test, use a segment listed in PLACEHOLDERS with its reason.", file=sys.stderr)
        return 1
    if not args.quiet:
        print(f"personal-path-gate=pass tracked_files={tracked} findings=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
