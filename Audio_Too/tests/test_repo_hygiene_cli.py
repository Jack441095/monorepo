"""scripts/repo_hygiene.py CLI — bare invocation must default to "check", not crash.

Found 2026-07-30: `python scripts/repo_hygiene.py` (no subcommand, the
documented default) raised AttributeError, because argparse only applies a
subparser's own defaults (--max-mb) when that subparser is actually named
on the command line. Verifies every documented invocation shape returns
without raising.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import repo_hygiene


def test_bare_invocation_defaults_to_check_and_does_not_raise():
    assert repo_hygiene.main([]) == 0


def test_bare_invocation_with_none_argv_uses_sys_argv(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["repo_hygiene.py"])
    assert repo_hygiene.main(None) == 0


def test_explicit_check_still_works():
    assert repo_hygiene.main(["check"]) == 0


def test_explicit_check_with_flag_still_works():
    assert repo_hygiene.main(["check", "--max-mb", "5"]) == 0


def test_sizes_and_doctor_subcommands_still_work(capsys):
    assert repo_hygiene.main(["sizes"]) == 0
    assert repo_hygiene.main(["doctor"]) == 0
