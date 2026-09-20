"""main.py cmd_stop must also clean up the detached automix worker process.

Found 2026-07-30 (release-health check before sending the repo out): `main.py
start --detach` spawns the automix worker as a separate subprocess that binds
no port, so cmd_stop's lsof-based discovery (built for the website/KENN
servers) could never find or kill it -- every documented start/stop cycle
left an orphaned worker process running. serve.py now writes the worker's
PID to data/logs/worker.pid on start; cmd_stop reads and kills it here.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("audio_too_main", str(ROOT / "main.py"))
audio_too_main = importlib.util.module_from_spec(spec)
sys.modules["audio_too_main"] = audio_too_main
spec.loader.exec_module(audio_too_main)


def _spawn_dummy_process() -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])


def test_cmd_stop_kills_worker_pid_and_removes_the_file(tmp_path, monkeypatch):
    monkeypatch.setattr(audio_too_main, "ROOT", tmp_path)
    monkeypatch.setattr(audio_too_main, "pids_for_port", lambda _port: [])

    proc = _spawn_dummy_process()
    try:
        pid_file = tmp_path / "data" / "logs" / "worker.pid"
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(str(proc.pid))

        rc = audio_too_main.cmd_stop([])

        assert rc == 0
        assert not pid_file.exists(), "the pid file must be cleaned up after stopping"
        proc.wait(timeout=5)
        assert proc.returncode is not None, "the worker process must actually be terminated"
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)


def test_cmd_stop_handles_missing_pid_file_gracefully(tmp_path, monkeypatch):
    monkeypatch.setattr(audio_too_main, "ROOT", tmp_path)
    monkeypatch.setattr(audio_too_main, "pids_for_port", lambda _port: [])

    assert audio_too_main.cmd_stop([]) == 0


def test_cmd_stop_cleans_up_a_stale_pid_file_for_an_already_dead_process(tmp_path, monkeypatch):
    monkeypatch.setattr(audio_too_main, "ROOT", tmp_path)
    monkeypatch.setattr(audio_too_main, "pids_for_port", lambda _port: [])

    proc = _spawn_dummy_process()
    proc.kill()
    proc.wait(timeout=5)  # already exited (and reaped) before cmd_stop runs
    time.sleep(0.1)  # let the OS fully release the pid

    pid_file = tmp_path / "data" / "logs" / "worker.pid"
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(proc.pid))

    rc = audio_too_main.cmd_stop([])

    assert rc == 0
    assert not pid_file.exists()
