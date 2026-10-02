"""install_launchagent.sh looked for a placeholder the plist no longer uses, so the installed agent kept a literal <KENN_REPO_ROOT>."""

from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

PRODUCT_ROOT = Path(__file__).resolve().parents[5]
SCRIPT = PRODUCT_ROOT / "tooling" / "scripts" / "install_launchagent.sh"


def _install(tmp_path: Path) -> str:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "launchctl"
    stub.write_text("#!/bin/sh\nexit 0\n")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    home = tmp_path / "home"
    home.mkdir()
    env = {**os.environ, "HOME": str(home), "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    subprocess.run(["bash", str(SCRIPT)], env=env, check=True, capture_output=True, text=True)
    return (home / "Library" / "LaunchAgents" / "com.shenrendao.kenn.companion.plist").read_text()


def test_the_installed_launch_agent_has_no_unfilled_placeholders(tmp_path):
    installed = _install(tmp_path)
    assert not re.search(r"<[A-Z_]+>", installed)


def test_the_installed_launch_agent_points_at_the_real_server(tmp_path):
    installed = _install(tmp_path)
    assert f"{PRODUCT_ROOT}/apps/backend/src/kenn/server.py" in installed
    assert (PRODUCT_ROOT / "apps" / "backend" / "src" / "kenn" / "server.py").is_file()
