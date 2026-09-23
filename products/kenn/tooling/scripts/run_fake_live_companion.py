#!/usr/bin/env python3
"""Run a KENN companion against the fake Live backend for Live-free tests.

Every piece of runtime state (lock, receipt journal, chats, DB, shadow log,
session file) goes to a throwaway directory, so this can run beside the real
companion without touching real evidence. Default port 8091.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

KENN_ROOT = Path(__file__).resolve().parents[2]
AUDIO_DIR = KENN_ROOT / ".runtime" / "investor-demo-audio"


def fake_environment(state_dir: Path, port: int) -> dict[str, str]:
    env = {
        "KENN_LIVE_BACKEND": "fake",
        "KENN_PORT": str(port),
        "KENN_ALLOWED_ORIGINS": f"http://127.0.0.1:{port},http://localhost:{port}",
        "KENN_ALLOW_DAW_CONTROL": "1",
        "KENN_INSTANCE_LOCK_PATH": str(state_dir / "companion.lock"),
        "KENN_LIVE_RECEIPT_JOURNAL": str(state_dir / "receipts.jsonl"),
        "KENN_CHATS_DIR": str(state_dir / "chats"),
        "KENN_DB_PATH": str(state_dir / "kenn.db"),
        "KENN_LIVE_LLM_SHADOW_LOG": str(state_dir / "shadow.jsonl"),
        "KENN_SESSION_FILE": str(state_dir / "session.json"),
        "PYTHONPATH": os.pathsep.join([str(KENN_ROOT / "apps/backend/src"), str(KENN_ROOT / "tooling")]),
    }
    mix = AUDIO_DIR / "KENN_Demo_Mix_Analysis.wav"
    vocal = AUDIO_DIR / "KENN_Demo_Lead_Vocal_Analysis.wav"
    if mix.is_file() and vocal.is_file():
        env["KENN_LIVE_AUDIO_CAPTURE_PATH"] = str(mix)
        env["KENN_LIVE_VOCAL_CAPTURE_PATH"] = str(vocal)
    return env


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8091)
    parser.add_argument("--state-dir", type=Path, default=None)
    args = parser.parse_args()
    state_dir = args.state_dir or Path(tempfile.mkdtemp(prefix="kenn-fake-live-"))
    (state_dir / "chats").mkdir(parents=True, exist_ok=True)
    env = {**os.environ, **fake_environment(state_dir, args.port)}
    print(f"KENN fake-Live companion on http://127.0.0.1:{args.port} (state: {state_dir})", flush=True)
    server = KENN_ROOT / "apps/backend/src/kenn/server.py"
    os.execvpe(sys.executable, [sys.executable, str(server)], env)


if __name__ == "__main__":
    raise SystemExit(main())
