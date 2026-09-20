"""A hung build_index.py subprocess must not hang the request thread forever
(P0 fix, 2026-07-12) -- both duplicate implementations must time out cleanly."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
AUDIO_TOO = ROOT / "Audio_Too"
sys.path.insert(0, str(AUDIO_TOO / "server" / "app"))
sys.path.insert(0, str(AUDIO_TOO / "server" / "agents"))
sys.path.insert(0, str(AUDIO_TOO / "studio"))

import ableton_bridge  # noqa: E402
from creative_lab import repair as creative_lab_repair  # noqa: E402


def _raise_timeout(*args, **kwargs):
    raise subprocess.TimeoutExpired(cmd=args[0] if args else "build_index.py", timeout=kwargs.get("timeout", 300))


def test_ableton_bridge_build_index_handles_timeout(monkeypatch):
    monkeypatch.setattr(ableton_bridge.subprocess, "run", _raise_timeout)

    result = ableton_bridge.build_index()

    assert result["ok"] is False
    assert "timed out" in result["output"].lower()


def test_creative_lab_repair_build_index_handles_timeout(monkeypatch):
    monkeypatch.setattr(creative_lab_repair.subprocess, "run", _raise_timeout)

    result = creative_lab_repair._build_index()

    assert result["ok"] is False
    assert "timed out" in result["output"].lower()


def test_ableton_bridge_build_index_passes_timeout_kwargs(monkeypatch):
    captured = []

    def fake_run(*args, **kwargs):
        captured.append(kwargs.get("timeout"))
        return subprocess.CompletedProcess(args[0] if args else [], 0, stdout="ok", stderr="")

    monkeypatch.setattr(ableton_bridge.subprocess, "run", fake_run)

    result = ableton_bridge.build_index()

    assert result["ok"] is True
    assert captured == [300, 180]
