"""Crash-isolated native TTS worker; WAV bytes are written to stdout."""

from __future__ import annotations

import json
import sys

from thursday.voice_output import KOKORO_VOICE, synthesise


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--persistent", action="store_true")
    args = parser.parse_args()

    if args.persistent:
        while True:
            try:
                line = sys.stdin.readline()
                if not line:
                    break
                payload = json.loads(line)
                wav = synthesise(
                    str(payload.get("text", "")),
                    voice=str(payload.get("voice", KOKORO_VOICE)),
                    speed=payload.get("speed"),
                )
            except (json.JSONDecodeError, TypeError, ValueError):
                # Write 0 length to indicate error and keep the worker loop alive
                sys.stdout.buffer.write((0).to_bytes(4, byteorder="big"))
                sys.stdout.buffer.flush()
                continue

            if not wav:
                sys.stdout.buffer.write((0).to_bytes(4, byteorder="big"))
            else:
                sys.stdout.buffer.write(len(wav).to_bytes(4, byteorder="big"))
                sys.stdout.buffer.write(wav)
            sys.stdout.buffer.flush()
        return 0
    else:
        try:
            payload = json.loads(sys.stdin.buffer.read())
            wav = synthesise(
                str(payload.get("text", "")),
                voice=str(payload.get("voice", KOKORO_VOICE)),
                speed=payload.get("speed"),
            )
        except (json.JSONDecodeError, TypeError, ValueError):
            return 2
        if not wav:
            return 1
        sys.stdout.buffer.write(wav)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

