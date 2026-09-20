"""Tests for the Audio_Too serve launcher."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import serve  # noqa: E402
from serve import DEFAULT_OPEN_PATH, port_open, wait_for_port  # noqa: E402


def test_default_open_path_is_hub() -> None:
    assert DEFAULT_OPEN_PATH == "/hub"


def test_port_open_localhost_closed_port() -> None:
    assert port_open("127.0.0.1", 59999) is False


def test_wait_for_port_times_out() -> None:
    assert wait_for_port("127.0.0.1", 59998, timeout=0.3) is False


def test_start_prints_already_running_when_website_already_running(monkeypatch, capsys) -> None:
    # business/app/server.py now runs KENN and the Automix worker internally
    # in background threads (see app/background_services.py), so
    # the website port being open already implies KENN/Automix are up too --
    # there is no separate process left to "repair" here.
    opened = []

    monkeypatch.setattr(serve, "load_env", lambda: None)
    monkeypatch.setattr(serve, "python_executable", lambda: "python3")
    monkeypatch.setattr(serve, "port_open", lambda _host, port: port == serve.WEB_PORT)
    monkeypatch.setattr(serve, "open_browser", lambda path: opened.append(path))

    assert serve.main(["--no-open"]) == 0
    assert opened == []
    out = capsys.readouterr().out
    assert f"Port {serve.WEB_PORT} is already in use" in out


def test_start_detach_starts_the_website_process(monkeypatch, capsys, tmp_path) -> None:
    # business/app/server.py now runs KENN and the Automix worker internally
    # in background threads, so --detach only needs to launch the one
    # website process; see the comment in serve.py::main under args.detach.
    started = []
    wait_calls = []

    monkeypatch.setattr(serve, "LOG_DIR", tmp_path)
    monkeypatch.setattr(serve, "load_env", lambda: None)
    monkeypatch.setattr(serve, "python_executable", lambda: "python3")
    monkeypatch.setattr(serve, "port_open", lambda _host, _port: False)
    monkeypatch.setattr(serve, "stop_port", lambda _port, _label: None)
    monkeypatch.setattr(serve, "open_browser", lambda _path: None)

    def fake_start(cmd: list[str], label: str, log_name: str) -> object:
        started.append((cmd, label, log_name))
        return SimpleNamespace(pid=12345)

    def fake_wait(host: str, port: int, timeout: float = 45.0) -> bool:
        wait_calls.append((host, port, timeout))
        return True

    monkeypatch.setattr(serve, "start_detached_process", fake_start)
    monkeypatch.setattr(serve, "wait_for_port", fake_wait)

    assert serve.main(["--restart", "--detach", "--no-open"]) == 0

    assert len(started) == 1
    assert started[0][1] == "Audio_Too website"
    assert started[0][2] == "website.log"
    assert wait_calls[0][1] == serve.WEB_PORT
    out = capsys.readouterr().out
    assert "Website ready" in out
