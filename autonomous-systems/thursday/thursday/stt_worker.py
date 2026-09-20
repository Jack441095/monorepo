"""Crash-isolated native STT worker; JSON lines are read from stdin and written to stdout."""

from __future__ import annotations

import json
import sys
import os

def main() -> int:
    try:
        import mlx_whisper
    except ImportError:
        sys.stderr.write("mlx_whisper not installed.\n")
        return 1

    # Read JSON lines from stdin
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        try:
            payload = json.loads(line)
            audio_path = payload.get("audio_path", "")
            if not audio_path or not os.path.exists(audio_path):
                sys.stdout.write(json.dumps({"error": f"File not found: {audio_path}"}) + "\n")
                sys.stdout.flush()
                continue

            result = mlx_whisper.transcribe(
                audio_path,
                path_or_hf_repo="mlx-community/whisper-small-mlx",
                language="en",
                initial_prompt=(
                    "Audio engineering, Ableton Live, mixing, mastering, sidechain, compression, EQ, "
                    "snare, kick drum, bass, hi-hat, transient, attack, release, threshold, ratio, "
                    "frequency, low-pass, high-pass, gain, saturation, distortion, parallel, bus, "
                    "limiter, gate, loudness, LUFS, true peak, render, bounce, automation, MIDI."
                ),
                verbose=False,
            )
            text = result.get("text", "").strip()
            segments = result.get("segments") or []
            no_speech_prob = 0.0
            confidence = 1.0
            if segments:
                no_speech_prob = sum(s.get("no_speech_prob", 0.0) for s in segments) / len(segments)
                avg_logprob = sum(s.get("avg_logprob", 0.0) for s in segments) / len(segments)
                import math
                try:
                    confidence = float(math.exp(avg_logprob))
                except Exception:
                    confidence = 1.0
            
            sys.stdout.write(json.dumps({
                "text": text,
                "confidence": confidence,
                "no_speech_prob": no_speech_prob,
                "language": result.get("language", "en")
            }) + "\n")
        except Exception as e:
            sys.stdout.write(json.dumps({"error": str(e)}) + "\n")
        sys.stdout.flush()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
