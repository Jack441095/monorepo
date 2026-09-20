"""Smoke tests for main_llm.py one-shot chorus loop entry point."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "studio" / "audiogen" / "audiogen"


def _run_main_llm(*args: str) -> tuple[int, dict]:
    cmd = [sys.executable, str(ROOT / "main_llm.py"), *args, "--quiet"]
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, check=False)
    line = (proc.stdout or "").strip().splitlines()[-1] if (proc.stdout or "").strip() else ""
    payload = json.loads(line) if line else {}
    return int(proc.returncode), payload


def test_main_llm_list_emotions_json():
    code, payload = _run_main_llm("--list-emotions-json")
    assert code == 0
    assert payload.get("type") == "emotions"
    assert payload.get("ok") is True
    assert len(payload.get("emotions") or []) == 28


def test_main_llm_no_play_chorus_loop():
    code, payload = _run_main_llm("--emotion", "joy", "--no-play", "--seed", "42", "--bars", "8")
    assert code == 0
    assert payload.get("type") == "chorus_loop_playback"
    assert payload.get("ok") is True
    assert payload.get("emotion") == "joy"
    assert int(payload.get("seed", -1)) == 42
    assert int(payload.get("bars", 0)) == 8
    assert int(payload.get("event_count", 0)) > 0
    assert payload.get("played") is False


def test_main_llm_schema_json():
    code, payload = _run_main_llm("--schema-json")
    assert code == 0
    assert payload.get("type") == "tool_schema"
    assert payload.get("ok") is True
    schema = payload.get("schema") or {}
    assert schema.get("entrypoint") == "main_llm.py"
    assert schema.get("response_type") == "chorus_loop_playback"


def test_main_llm_wav_out_no_play(tmp_path):
    wav_path = tmp_path / "joy_chorus.wav"
    code, payload = _run_main_llm(
        "--emotion",
        "joy",
        "--no-play",
        "--seed",
        "7",
        "--wav-out",
        str(wav_path),
    )
    assert code == 0
    assert payload.get("ok") is True
    assert payload.get("wav_written") is True
    assert wav_path.is_file()
    assert wav_path.stat().st_size > 44
