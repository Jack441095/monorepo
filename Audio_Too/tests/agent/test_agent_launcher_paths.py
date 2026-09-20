"""Regression tests for business/agents/agent's sys.path setup.

docs/CODEBASE_AUDIT_2026-07-06.md's macro-routing investigation surfaced a
second, separate bug while verifying the fix end-to-end: the launcher script
added the wrong directories to sys.path (one level short of the real repo
root for `audio_too`, and a stale "Website" directory instead of "app"),
so importing Shared.draft_sender — and therefore running almost any agent
CLI command ("weekly", "week-ahead", "profit", "sessions", etc.) — crashed
with ModuleNotFoundError. Run as a real subprocess since the whole point is
verifying the script's own sys.path bootstrapping, not just its Python logic.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
AGENT = ROOT / "business" / "agents" / "agent"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(AGENT), *args],
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_agent_launcher_does_not_crash_on_import() -> None:
    result = _run("--help")
    assert "ModuleNotFoundError" not in result.stderr
    assert result.returncode == 0


def test_weekly_review_command_runs_without_import_errors() -> None:
    """This command transitively imports Shared.draft_sender -> app.draft_service
    -> event_store -> the top-level `audio_too` package, and Shared.expenses'
    invoice_pdf import — the exact chain that was broken."""
    result = _run("weekly")
    assert "ModuleNotFoundError" not in result.stderr
    assert "No module named" not in result.stdout
    assert result.returncode == 0
    assert "Weekly" in result.stdout


def test_week_ahead_command_runs_without_import_errors() -> None:
    result = _run("week-ahead")
    assert "ModuleNotFoundError" not in result.stderr
    assert result.returncode == 0
