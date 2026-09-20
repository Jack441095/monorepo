#!/usr/bin/env python3
"""CLI entry point for AI stem separation (Demucs v4).

Contract (mirrors studio/audiogen/audiogen/main_llm.py, consumed by
business/app/stem_separation_bridge.py): print progress freely to stdout,
then print exactly one JSON dict as the final stdout line --
``{"ok": true, "stems": {...}, "model": ..., "device": ..., "duration_seconds": ...}``
on success, or ``{"ok": false, "error": ...}`` on failure. Never raises past
main() -- the bridge parses the last ``{``-prefixed stdout line and otherwise
treats the process as failed.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from core import STEM_NAMES, separate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Separate a mixed track into stems with Demucs v4.")
    parser.add_argument("--input", required=True, help="Path to the mixed stereo audio file.")
    parser.add_argument("--output-dir", required=True, help="Directory to write stem WAVs into.")
    parser.add_argument("--model", default="htdemucs", help="Demucs pretrained model name.")
    parser.add_argument("--device", default="", help="Force a device (cuda/mps/cpu); auto-detects if omitted.")
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    if not input_path.exists():
        print(json.dumps({"ok": False, "error": f"Input file not found: {input_path}"}))
        return 1

    print(f"Loading Demucs model '{args.model}'...", flush=True)
    started = time.monotonic()
    try:
        stem_paths = separate(
            input_path,
            args.output_dir,
            model_name=args.model,
            device=args.device or None,
        )
    except Exception as exc:  # noqa: BLE001 - reported to the caller as JSON, not raised
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

    missing = [name for name in STEM_NAMES if name not in stem_paths]
    if missing:
        print(json.dumps({"ok": False, "error": f"Model did not produce stems: {missing}"}))
        return 1

    print(f"Separation complete in {time.monotonic() - started:.1f}s.", flush=True)
    print(json.dumps({
        "ok": True,
        "stems": stem_paths,
        "model": args.model,
        "duration_seconds": round(time.monotonic() - started, 2),
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
