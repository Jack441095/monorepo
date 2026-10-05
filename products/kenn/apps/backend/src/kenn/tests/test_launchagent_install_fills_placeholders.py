"""install_launchagent.sh looked for a placeholder the plist no longer uses, so the installed agent kept a literal <KENN_REPO_ROOT>."""

from __future__ import annotations

import os
import plistlib
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


def test_the_installed_launch_agent_answers_with_the_8b_brain(tmp_path):
    # Regression (5 Oct): the template set KENN_USE_MLX=1, so the installed app answered with MLX's 1.5B.
    env = plistlib.loads(_install(tmp_path).encode())["EnvironmentVariables"]
    assert env["KENN_LLM_ENABLED"] == "1"
    assert env["KENN_USE_MLX"] == "0"
    assert (env["KENN_LLM_PROVIDER"], env["KENN_LLM_MODEL"]) == ("ollama", "kenn-brain-qwen3-8b")
