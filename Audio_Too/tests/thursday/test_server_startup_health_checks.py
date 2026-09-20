"""thursday/server.py's start() previously validated only the auth token
before serve_forever() -- no check of Ollama reachability or whether
Thursday's own data directory is writable, so the server could report
"listening" successfully and only fail on the first real request that
needed the missing dependency (P4 fix, 2026-07-13). These checks are
best-effort/warn-only, never blocking startup -- unlike KENN's index check,
Thursday's core routing works without either dependency."""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import thursday.server as server  # noqa: E402


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _FakeOkClient:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, *args, **kwargs):
        return _FakeResponse(200)


class _FakeUnreachableClient:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, *args, **kwargs):
        raise httpx.ConnectError("connection refused", request=None)


def test_prints_ollama_reachable_when_available(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: _FakeOkClient())
    monkeypatch.setenv("THURSDAY_DATA_DIR", str(tmp_path))

    server._startup_health_checks()

    out = capsys.readouterr().out
    assert "Ollama reachable." in out
    assert "WARNING" not in out


def test_warns_but_does_not_raise_when_ollama_unreachable(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: _FakeUnreachableClient())
    monkeypatch.setenv("THURSDAY_DATA_DIR", str(tmp_path))

    server._startup_health_checks()  # must not raise

    out = capsys.readouterr().out
    assert "WARNING: Ollama unreachable" in out


def test_reports_data_directory_writable(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: _FakeOkClient())
    monkeypatch.setenv("THURSDAY_DATA_DIR", str(tmp_path / "data"))

    server._startup_health_checks()

    out = capsys.readouterr().out
    assert "Data directory writable" in out
    # the write probe must not be left behind
    assert not (tmp_path / "data" / ".startup_write_probe").exists()


def test_warns_but_does_not_raise_when_data_directory_unwritable(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: _FakeOkClient())
    unwritable = tmp_path / "data"
    monkeypatch.setenv("THURSDAY_DATA_DIR", str(unwritable))

    def boom_mkdir(*args, **kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "mkdir", boom_mkdir)

    server._startup_health_checks()  # must not raise

    out = capsys.readouterr().out
    assert "WARNING: data directory" in out
