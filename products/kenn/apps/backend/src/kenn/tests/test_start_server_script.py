"""scripts/start_server.sh used to export bare HOST/PORT, but server.py only
ever reads KENN_HOST/KENN_PORT (apps/backend/src/kenn/server.py's HOST/PORT module
constants) -- so the script's own 0.0.0.0 default, and any caller override,
was silently ignored: the server always bound to its real 127.0.0.1:8090
default regardless of what the script printed. Fixed to export KENN_HOST/
KENN_PORT (falling back to a plain HOST/PORT the caller may already set).
This starts the real script as a subprocess with a distinct port and proves
the server actually serves on it, rather than silently falling back to 8090.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[5]
SCRIPT = REPO_ROOT / "tooling" / "scripts" / "start_server.sh"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_start_server_script_honors_a_kenn_port_override(tmp_path: Path) -> None:
    port = _free_port()
    env = dict(os.environ)
    env["KENN_PORT"] = str(port)
    env["KENN_HOST"] = "127.0.0.1"
    env["KENN_INSTANCE_LOCK_PATH"] = str(tmp_path / "companion.lock")
    process = subprocess.Popen(
        ["bash", str(SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 30
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2) as response:
                    assert response.status == 200
                    return
            except Exception as exc:  # noqa: BLE001 - server may still be starting up
                last_error = exc
                time.sleep(0.5)
        pytest.fail(f"server never became healthy on the overridden port {port}: {last_error}")
    finally:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)


def test_second_companion_exits_before_serving_http(tmp_path: Path) -> None:
    first_port = _free_port()
    second_port = _free_port()
    lock_path = tmp_path / "shared-companion.lock"
    first_env = dict(os.environ)
    first_env.update(
        KENN_PORT=str(first_port),
        KENN_HOST="127.0.0.1",
        KENN_INSTANCE_LOCK_PATH=str(lock_path),
    )
    first = subprocess.Popen(
        ["bash", str(SCRIPT)],
        cwd=REPO_ROOT,
        env=first_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{first_port}/api/health", timeout=2
                ) as response:
                    assert response.status == 200
                    break
            except Exception:  # noqa: BLE001 - first server is still starting
                time.sleep(0.25)
        else:
            pytest.fail("first companion never became healthy")

        second_env = dict(first_env)
        second_env["KENN_PORT"] = str(second_port)
        second = subprocess.run(
            ["bash", str(SCRIPT)],
            cwd=REPO_ROOT,
            env=second_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=30,
            check=False,
        )
        assert second.returncode == 2
        assert "Another KENN companion already owns" in second.stdout
        assert f"PID {first.pid}" in second.stdout
        with pytest.raises(OSError):
            urllib.request.urlopen(f"http://127.0.0.1:{second_port}/api/health", timeout=1)
    finally:
        os.killpg(os.getpgid(first.pid), signal.SIGTERM)
        try:
            first.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(first.pid), signal.SIGKILL)
