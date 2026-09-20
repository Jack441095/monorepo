"""Regression guard for docs/audits/2026-07-18-log-redaction-audit.md: a
static scan (scripts/eval/check_log_redaction.py) that catches a log/print
call directly interpolating a raw, sensitive-looking variable (a customer
prompt, a filesystem path, a secret/token) instead of a safe derived value.

Exists so a *new* call site can't silently reintroduce the exact class of
mistake found by hand on 2026-07-18 (four sites across thursday/brain.py and
business/app/automix_worker.py) without a test noticing.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "eval"))

import check_log_redaction  # noqa: E402


def test_no_unallowlisted_violations_in_the_real_codebase():
    violations = check_log_redaction.find_violations()
    assert not violations, (
        f"Found {len(violations)} potential log-redaction violation(s) — a log/print call is "
        f"interpolating a raw sensitive-looking value instead of a safe derived one "
        f"(len(x), x.name): {violations}"
    )


def test_checker_actually_catches_the_original_bug_pattern(monkeypatch):
    """The checker's own pattern list must cover the exact leak this guard
    exists for — verified directly against the pre-fix line, not just
    trusting the regex was written correctly. (Caught a real gap while
    building this: the pattern initially listed raw_content/response_content
    but not bare `content`, which is exactly what the original
    thursday/brain.py leak used -- `{content}`.)"""
    assert check_log_redaction._line_interpolates_raw_sensitive_name(
        'logger.warning(f"Failed to parse LLM brain JSON decision: {e}. Raw content: {content}")'
    ) == "content"
    assert check_log_redaction._line_interpolates_raw_sensitive_name(
        'print(f"[automix_worker] Applying revision feedback: \'{feedback_text}\'")'
    ) == "feedback_text"
    assert check_log_redaction._line_interpolates_raw_sensitive_name(
        'print(f"[automix_worker] Found reference track at {ref_path}.")'
    ) == "ref_path"


def test_checker_does_not_flag_the_actual_fixed_lines():
    assert check_log_redaction._line_interpolates_raw_sensitive_name(
        'logger.warning(f"Failed to parse LLM brain JSON decision: {e}. '
        'Raw content length: {len(content)} chars")'
    ) is None
    assert check_log_redaction._line_interpolates_raw_sensitive_name(
        'print(f"[automix_worker] Found reference track \'{ref_path.name}\'. Running reference analysis...")'
    ) is None
    assert check_log_redaction._line_interpolates_raw_sensitive_name(
        'print(f"[automix_worker] Applying revision feedback ({len(feedback_text)} chars)")'
    ) is None


def test_checker_ignores_safe_identifier_names():
    assert check_log_redaction._line_interpolates_raw_sensitive_name(
        'logger.info(f"job {job_id} for project {project_id}")'
    ) is None


def test_checker_ignores_non_log_lines():
    assert check_log_redaction._line_interpolates_raw_sensitive_name(
        'message = f"content: {content}"'
    ) is None


def test_checker_scans_a_real_planted_violation(tmp_path, monkeypatch):
    """End-to-end: plant a real file with the exact bug pattern under a
    scanned directory and confirm find_violations() reports it, then remove
    it and confirm the scan goes clean again -- same canary-verification
    pattern as tests/kenn/test_index_contains_all_notes.py."""
    scan_root = tmp_path / "server" / "app"
    scan_root.mkdir(parents=True)
    bad_file = scan_root / "planted_leak.py"
    bad_file.write_text(
        'import logging\nlogger = logging.getLogger(__name__)\n'
        'def f(feedback_text):\n    logger.warning(f"leak: {feedback_text}")\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(check_log_redaction, "ROOT", tmp_path)
    monkeypatch.setattr(check_log_redaction, "SCAN_DIRS", ("server/app",))
    monkeypatch.setattr(check_log_redaction, "ALLOWLIST", set())

    violations = check_log_redaction.find_violations()
    assert len(violations) == 1
    assert violations[0][0] == "server/app/planted_leak.py"
    assert violations[0][3] == "feedback_text"

    bad_file.unlink()
    assert check_log_redaction.find_violations() == []
