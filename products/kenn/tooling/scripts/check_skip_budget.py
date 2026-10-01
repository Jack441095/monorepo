#!/usr/bin/env python3
"""Fail the build when a test skips for a reason nobody has accounted for.

    check_skip_budget.py [--allow-file PATH] [--target apps/backend/src/kenn/tests] [--pytest-args ...]

A "skips budget" is normally a number: fail if the skip count grows. A number is not enough here, because the
backend suite skips for two very different reasons and they need opposite treatment.

**Environmental skips** are real and expected — 48 tests in `test_server_smoke.py` cannot run without a built
knowledge index, and a fresh CI clone has none. They are listed by reason in `known_skip_reasons.json` and allowed.

**Everything else** is a test that quietly stopped running, which is the failure this exists to catch. A skipped
test reports green in every other output, and the suite's own count is the only place it shows up.

Measured 30 Sept on a fresh worktree with no index: 125 skips, of which 120 were index-dependent and 5 were not. On
the main checkout, which has the index, the same command reports 5. So a bare skip-count budget would have to allow
125 on CI and 5 locally, and would not notice the difference being the index rather than the code.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

KENN_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ALLOW = KENN_ROOT / "tooling" / "known_skip_reasons.json"
# file, then line, then the reason. Splitting on the first colon alone put "77: " at the front of every
# reason and made the whole allowlist wrong, which the checker itself caught on its first run.
# Two shapes: pytest prints "SKIPPED [48] file:77: reason" for a function-level skip and
# "SKIPPED [2] file: reason" for a module-level one. Requiring the line number silently dropped every
# module-level skip, which is most of them.
SKIPPED = re.compile(r"^SKIPPED \[(?P<count>\d+)\] (?P<file>[^:]+):(?:(?P<line>\d+):)? ?(?P<reason>.*)$")


def load_allowed(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return [str(reason) for reason in json.loads(path.read_text(encoding="utf-8")).get("environmental", [])]


def collect_skips(target: str, extra: list[str]) -> tuple[Counter, Counter, int]:
    """(skip reasons by count, file:line by count, passed) from one pytest run with -rs."""
    command = [sys.executable, "-m", "pytest", "-q", "-rs", "--no-header", target, *extra]
    result = subprocess.run(command, cwd=KENN_ROOT, capture_output=True, text=True)
    reasons: Counter = Counter()
    sites: Counter = Counter()
    for line in result.stdout.splitlines():
        match = SKIPPED.match(line.strip())
        if match:
            count = int(match.group("count"))
            site = f"{match.group('file')}:{match.group('line') or '-'}"
            reason = match.group("reason").strip()
            reasons[reason] += count
            sites[f"{site}: {reason}"] += count
    return reasons, sites, result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", default="apps/backend/src/kenn/tests")
    parser.add_argument("--allow-file", type=Path, default=DEFAULT_ALLOW)
    parser.add_argument("pytest_args", nargs="*", help="extra arguments passed through to pytest")
    args = parser.parse_args()

    allowed = load_allowed(args.allow_file)
    reasons, sites, code = collect_skips(args.target, list(args.pytest_args))
    if code not in (0, 1):
        print(f"skip-budget: pytest exited {code}, so the skip count is not trustworthy", file=sys.stderr)
        return code

    total = sum(reasons.values())
    unaccounted = {reason: count for reason, count in reasons.items() if reason not in allowed}
    accounted = total - sum(unaccounted.values())
    print(f"skip-budget: {total} skips, {accounted} environmental (allowed), {sum(unaccounted.values())} unaccounted")
    for site, count in sorted(sites.items()):
        print(f"  {count:4}  {site}")
    if unaccounted:
        print("skip-budget=FAIL: tests are skipping for reasons nobody accounted for", file=sys.stderr)
        for reason, count in sorted(unaccounted.items()):
            print(f"  {count:4}  {reason}", file=sys.stderr)
        print("Either fix the skip, or record it in "
              f"{args.allow_file.relative_to(KENN_ROOT)} under 'environmental' with the reason it is legitimate.",
              file=sys.stderr)
        return 1
    print("skip-budget=pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
