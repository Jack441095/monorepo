"""Native MLX Kokoro TTS worker — optional local-only fast path.

⚠️  LICENSING NOTE, READ BEFORE ANY DISTRIBUTED BUILD ⚠️
This worker uses `mlx-audio` + `misaki` (both MIT/Apache 2.0) for a
~5-6x synthesis speedup over the default ONNX/CPU path (see
docs/AUDIO_MVP_MASTER_PLAN.md §5b "Pre-Distribution Checklist"). Robust
handling of out-of-dictionary/jargon words (unavoidable in an audio-
engineering domain — "sidechain", "LUFS", etc.) requires `phonemizer`,
which is GPL-3.0-licensed, pulled in transitively by `misaki.en`'s espeak
fallback. This module is deliberately isolated in its own subprocess,
invoked only under the native arm64 system Python, and is NEVER imported
by `thursday/voice_output.py` directly — the default ONNX path (fully
MIT/Apache) has no dependency on anything in this file. Before shipping
a distributed build, either get explicit legal clearance for this
subprocess-isolation arrangement, or disable this fast path entirely
(the code already falls back to the ONNX path automatically if this
worker is unavailable/disabled).

Run under: arch -arm64 <native arm64 python> thursday/tts_worker_mlx.py --persistent
(mirrors thursday/tts_worker.py's length-prefixed-WAV-over-stdout protocol
so it's a drop-in alternative backend, not a different protocol.)
"""

from __future__ import annotations

import io
import json
import os
import sys

# Must be set before mlx_audio/misaki import espeak via phonemizer.
os.environ.setdefault(
    "PHONEMIZER_ESPEAK_LIBRARY",
    "/opt/homebrew/Cellar/espeak-ng/1.52.0/lib/libespeak-ng.1.dylib",
)

_VOICE_MAP = {
    "af_heart": "af_heart",
    "am_onyx": "am_onyx",
    "am_adam": "am_adam",
    "af_bella": "af_bella",
    "am_michael": "am_michael",
}


def _synthesize(model, text: str, voice: str, speed: float) -> bytes | None:
    import numpy as np
    import soundfile as sf

    if not text.strip():
        return None
    mapped_voice = _VOICE_MAP.get(voice, "af_heart")
    chunks = list(model.generate(text=text, voice=mapped_voice, speed=speed or 1.1))
    if not chunks:
        return None
    samples = np.concatenate([np.asarray(c.audio) for c in chunks])
    buf = io.BytesIO()
    sf.write(buf, samples, chunks[0].sample_rate, format="WAV")
    return buf.getvalue()


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--persistent", action="store_true")
    args = parser.parse_args()

    try:
        from mlx_audio.tts.utils import load_model
        model = load_model("mlx-community/Kokoro-82M-bf16")
    except Exception as exc:
        print(f"MLX TTS worker failed to load model: {exc}", file=sys.stderr, flush=True)
        return 3

    if args.persistent:
        print("MLX TTS worker ready.", file=sys.stderr, flush=True)
        while True:
            line = sys.stdin.readline()
            if not line:
                break
            try:
                payload = json.loads(line)
                wav = _synthesize(
                    model,
                    str(payload.get("text", "")),
                    str(payload.get("voice", "af_heart")),
                    float(payload.get("speed") or 1.1),
                )
            except Exception as exc:
                print(f"MLX TTS synthesis error: {exc}", file=sys.stderr, flush=True)
                wav = None

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
            wav = _synthesize(
                model,
                str(payload.get("text", "")),
                str(payload.get("voice", "af_heart")),
                float(payload.get("speed") or 1.1),
            )
        except Exception:
            return 2
        if not wav:
            return 1
        sys.stdout.buffer.write(wav)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
