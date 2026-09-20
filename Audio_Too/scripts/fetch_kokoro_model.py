#!/usr/bin/env python3
"""Fetch the Kokoro TTS model files for Thursday's voice output.

Thursday/KENN's preferred TTS engine is Kokoro (MIT-licensed, local, neural),
via the `kokoro-onnx` package already in requirements. Without these files,
voice_output.py silently falls back to macOS `say` for CLI/voice-mode speech,
and has no fallback at all for browser-playback TTS (synthesise() just
returns None).

Source: the official kokoro-onnx project's documented release assets
(https://github.com/thewh1teagle/kokoro-onnx, model-files-v1.0 release —
see that package's own PyPI README, which is where these URLs come from).

Model files (~115 MB total) are git-ignored; run this once after setup:

    python scripts/fetch_kokoro_model.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _resumable_download import download  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
MONOREPO = REPO.parent
MODEL_DIR = MONOREPO / "products" / "kenn" / "kenn" / "artifacts" / "models" / "kokoro"
BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
FILES = {
    "kokoro-v1.0.int8.onnx": f"{BASE}/kokoro-v1.0.int8.onnx",
    "voices-v1.0.bin": f"{BASE}/voices-v1.0.bin",
}


def fetch() -> None:
    for name, url in FILES.items():
        dest = MODEL_DIR / name
        if dest.exists() and dest.stat().st_size > 0:
            print(f"  {name}: already present, skipping")
            continue
        download(url, dest)


def main() -> int:
    print("Fetching Kokoro TTS model files...")
    fetch()
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
