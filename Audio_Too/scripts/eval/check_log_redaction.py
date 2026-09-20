#!/usr/bin/env python3
"""Static guard for the log-redaction gap found in
docs/audits/2026-07-18-log-redaction-audit.md: a log/print call that
directly interpolates a raw, sensitive-looking variable (a customer prompt,
a filesystem path, a secret/token) rather than a safe derived value
(len(x), x.name, a redacted summary).

This is a heuristic regex scan, not a real AST-based analyzer -- it exists
to catch the exact class of mistake found by hand on 2026-07-18 (four sites
across thursday/brain.py and automix_worker.py), not to be a general-purpose
secret scanner. False positives are expected on legitimate uses (e.g.
logging a project_id, which is an identifier, not sensitive content); add
them to ALLOWLIST below with a one-line reason, same pattern as
audio_too/release_package.py's _PRIVATE_PREFIXES.

Usage: check_log_redaction.py (exits 1 and prints findings if any; part of
tests/test_log_redaction_guard.py, not meant to be run standalone in CI
directly -- import find_violations() from there).
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

SCAN_DIRS = (
    "server/app",
    "thursday",
    "studio/kenn/kenn",
    "studio/audio_analysis/audio_analysis",
)

# Variable names that are safe to log raw (identifiers, not content) even
# though they might superficially match a sensitive-looking pattern below.
SAFE_BARE_NAMES = {
    "project_id", "job_id", "review_id", "request_id", "session_id",
    "correlation_id", "task_id", "worker_id", "version", "genre",
    "target_lufs", "status", "event", "error_id",
}

# Variable-name fragments considered sensitive when interpolated *raw*
# (i.e. not via .name, len(...), or similar derived-safe access).
SENSITIVE_NAME_PATTERN = re.compile(
    r"\b(prompt|feedback_text|user_text|content|raw_content|response_content|"
    r"api_key|apikey|access_token|auth_token|bearer_token|secret_key|"
    r"session_secret|signing_key|dashboard_password|smtp_password|"
    r"ref_path|audio_path|upload_path|stem_path|file_path|project_upload_dir)\b",
    re.IGNORECASE,
)

# (file relative to ROOT, line substring) pairs already reviewed and judged
# safe -- e.g. logging a redacted/derived value using a sensitive-looking
# variable name. Each entry needs a reason so a future reviewer knows why
# it's here, not just that it was silenced.
ALLOWLIST: set[tuple[str, str]] = {
    # thursday/brain.py: logs len(content), not content itself -- the fixed
    # version of the exact leak this script exists to catch.
    ("thursday/brain.py", "Raw content length"),
    # automix_worker.py: logs ref_path.name (filename only) and
    # len(feedback_text), not the raw values -- both already redacted.
    ("server/app/automix_worker.py", "ref_path.name"),
    ("server/app/automix_worker.py", "len(feedback_text)"),
}

LOG_CALL_PATTERN = re.compile(
    r'(?:logger\.\w+|logging\.\w+|print)\(\s*f["\']'
)


def _line_interpolates_raw_sensitive_name(line: str) -> str | None:
    """Return the offending variable name if `line` is a log/print call that
    interpolates a sensitive-looking name *without* a safe derived accessor
    (.name, len(...)) guarding it. None if the line looks safe."""
    if not LOG_CALL_PATTERN.search(line):
        return None
    for match in re.finditer(r"\{([^}]+)\}", line):
        expr = match.group(1).strip()
        bare_name = expr.split(".")[0].split("(")[0].strip()
        if bare_name in SAFE_BARE_NAMES:
            continue
        if not SENSITIVE_NAME_PATTERN.search(expr):
            continue
        # Safe derived accessors: len(x), x.name, x.stem -- these expose a
        # count or a non-path-revealing identifier, not raw content.
        if re.match(r"^len\(", expr) or expr.endswith((".name", ".stem")):
            continue
        return expr
    return None


def find_violations() -> list[tuple[str, int, str, str]]:
    """Returns (relative_path, line_number, line_text, offending_expr) for
    every unallowlisted violation found under SCAN_DIRS."""
    violations: list[tuple[str, int, str, str]] = []
    for scan_dir in SCAN_DIRS:
        base = ROOT / scan_dir
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            if "__pycache__" in path.parts or "/tests/" in path.as_posix() or path.name.startswith("test_"):
                continue
            relative = path.relative_to(ROOT).as_posix()
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (UnicodeDecodeError, OSError):
                continue
            for line_number, line in enumerate(lines, start=1):
                offending = _line_interpolates_raw_sensitive_name(line)
                if offending is None:
                    continue
                if any(relative == entry_path and needle in line for entry_path, needle in ALLOWLIST):
                    continue
                violations.append((relative, line_number, line.strip(), offending))
    return violations


def main() -> int:
    violations = find_violations()
    if not violations:
        print("OK: no unallowlisted raw sensitive-value logging found.")
        return 0
    print(f"Found {len(violations)} potential log-redaction violation(s):\n")
    for relative, line_number, line, offending in violations:
        print(f"  {relative}:{line_number}  (interpolates raw `{offending}`)")
        print(f"    {line}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
