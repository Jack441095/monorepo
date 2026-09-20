"""Tests for business/agents/Shared/mix_review_cli.py — previously zero
test coverage. docs/CODEBASE_AUDIT_2026-07-06.md found and verified this
whole CLI ("./agent mix-review plan/progress/compare") was completely dead:
MIXREVIEW_DIR pointed at business/agents/MixReview, which no longer exists
(the package moved to studio/agents/MixReview/ during a restructure), so
every command failed with "Could not import revision agent".
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "business" / "agents"))

from Shared.mix_review_cli import MIXREVIEW_DIR, REPORTS_DIR  # noqa: E402


def test_mixreview_dir_points_at_the_real_package() -> None:
    assert MIXREVIEW_DIR.exists(), f"{MIXREVIEW_DIR} does not exist"
    assert (MIXREVIEW_DIR / "revision_agent.py").exists()


def test_mix_review_plan_command_runs_without_import_errors(tmp_path) -> None:
    """Regression test for the verified dead-CLI bug — run as a real
    subprocess since the bug was in the launcher's own import resolution,
    not in Python logic a direct function call would exercise the same way.
    """
    report = {
        "goal_label": "Test Mix",
        "metrics": {"technical_score": 70},
        "flags": [],
    }
    report_path = tmp_path / "cli_test_report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    # cmd_plan always saves its output plan into the real REPORTS_DIR (it only
    # respects an absolute *input* path, not the output location) — clean up
    # after ourselves rather than leaving a generated file in a tracked dir.
    generated_plan = REPORTS_DIR / f"{report_path.stem}_plan.json"
    try:
        agent = ROOT / "business" / "agents" / "agent"
        result = subprocess.run(
            [sys.executable, str(agent), "mix-review", "plan", str(report_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert "Could not import revision agent" not in result.stdout
        assert "ModuleNotFoundError" not in result.stderr
        assert "Mix Review Plan" in result.stdout
    finally:
        generated_plan.unlink(missing_ok=True)


def test_business_server_sys_path_resolves_revision_agent_import() -> None:
    """Regression test for the second instance of the same bug: mix_review.py
    (imported by the real business/app/server.py, not just the CLI) also does
    `from agents.MixReview.revision_agent import ...`, which needs plain
    studio/ on sys.path — server.py only added studio/audio_analysis and
    studio/kenn. Run in a fresh subprocess (no test-file sys.path shims) so
    this proves server.py's own bootstrapping is sufficient on its own.
    """
    code = (
        "import sys; "
        "sys.path.insert(0, 'server/app'); "
        "import server; "
        "from agents.MixReview.revision_agent import revision_agent_plan; "
        "print('OK')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(ROOT),
    )
    assert "OK" in result.stdout
    assert "ModuleNotFoundError" not in result.stderr
