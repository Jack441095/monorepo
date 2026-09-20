"""Tests for scripts/build_m4l_device.py M4L device build & deployment script."""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build_m4l_device.py"


def test_build_m4l_device_script_runs_verification(tmp_path):
    """Assert build_m4l_device.py verifies source files and deploys cleanly to target dir."""
    target_dir = tmp_path / "M4L_Test_Deploy"

    cmd = [sys.executable, str(BUILD_SCRIPT), "--target-dir", str(target_dir)]
    res = subprocess.run(cmd, capture_output=True, text=True)

    assert res.returncode == 0, f"Script failed: {res.stderr}"
    assert "[OK] Verified M4L source files" in res.stdout
    assert "[SUCCESS] KENN Live Suggestion device deployed" in res.stdout

    # Verify deployed files
    assert (target_dir / "live_state_reader.js").exists()
    assert (target_dir / "live_suggestion_client.js").exists()
    assert (target_dir / "package.json").exists()
