"""Hands-free "Hey Jarvis" wake word for Thursday, desktop-only.

**Why "Hey Jarvis" and not "Hey Thursday":** openWakeWord (github.com/
dscripka/openWakeWord, Apache-2.0) ships pretrained models for a handful
of fixed phrases -- alexa, hey_mycroft, hey_jarvis, hey_rhasspy. None say
"Thursday"; training a custom wake-word model is a real, separate ML
pipeline (data collection or synthetic-TTS generation + fine-tuning), not
something to improvise here. "hey_jarvis" is the closest available
pretrained phrase and, given this whole assistant is explicitly framed as
Jarvis-like, a reasonable real choice rather than a compromise -- but it's
worth knowing this says "Jarvis" out loud, not "Thursday", until someone
trains a real custom model.

**Why desktop-only, not the phone:** iOS Safari suspends background
microphone access the moment a browser tab isn't in the foreground --
there is no way for a web page to listen continuously in the background.
A real always-listening wake word needs a native app with a background
audio session entitlement, which this is not. This module uses
`sounddevice` for direct local microphone access, so it only ever runs on
this Mac, as its own background process -- not through thursday/server.py
at all.

**Architecture:** openWakeWord's ONNX models are cheap (~1-2MB, run on
80ms audio frames) -- this runs them continuously as an always-on gate,
and only invokes the heavy path (record a follow-up clip -> faster-whisper
transcription via thursday.voice.transcribe() -> thursday.bridge.ask() ->
Kokoro TTS via thursday.voice_output.speak()) once actually triggered.
This replaces thursday.voice.continuous_mode()'s older approach of
re-running full Whisper transcription on every 4-second clip forever just
to check for the wake word -- openWakeWord's frame-level inference is
dramatically cheaper than that when idle.

**Setup:** `pip install openwakeword` (already installed in Audio_Too's
venv) + `python3 -c "import openwakeword; openwakeword.utils.download_models()"`
(already run, models cached in openwakeword's own package resources).
First run needs an interactive macOS microphone permission prompt --
run this in a foreground Terminal once before making it a background
launchd service, so there's a session to approve the prompt in.
"""

from __future__ import annotations

import logging
import sys
import time

logger = logging.getLogger(__name__)

WAKE_WORD_MODEL = "hey_jarvis"
DEFAULT_THRESHOLD = 0.5
FRAME_SAMPLES = 1280  # openWakeWord's expected chunk size at 16kHz (80ms)
SAMPLE_RATE = 16000


def _load_model():
    """Raises ImportError/FileNotFoundError with a clear message if
    openwakeword or sounddevice aren't available -- never silently no-ops.
    """
    from openwakeword.model import Model
    return Model(wakeword_models=[WAKE_WORD_MODEL], inference_framework="onnx")


def run_wake_word_loop(threshold: float = DEFAULT_THRESHOLD) -> None:
    """Blocks forever, listening for "Hey Jarvis" via the real
    microphone. On trigger: records a follow-up command clip, transcribes
    it (thursday.voice.transcribe, faster-whisper), routes it through
    Thursday's real orchestrator (thursday.bridge.ask), and speaks the
    real response aloud (thursday.voice_output.speak, Kokoro TTS) --
    every step here is the same real pipeline already used by the phone
    chat page and the CLI, just triggered hands-free instead of by typing
    or a mic-button press.

    The wake-detection InputStream is explicitly closed before handling a
    trigger, not left open underneath it -- thursday.voice.record_audio()
    (used for the follow-up command clip) opens its own separate
    sd.rec()/sd.wait() stream, and running a 5-second blocking record call
    from inside this stream's audio callback (the natural-looking place to
    put it) would stall the callback thread and corrupt the ring buffer.
    Closing this stream first, handling the trigger on the main thread,
    then reopening a fresh stream to resume listening is the correct
    shape, not just a defensive extra step.
    """
    import threading

    import numpy as np
    import sounddevice as sd

    from thursday.bridge import ask
    from thursday.voice import record_audio, transcribe
    from thursday.voice_output import speak

    model = _load_model()
    print(f"[wake_word] Listening for \"Hey Jarvis\" (threshold={threshold}). Ctrl+C to stop.")

    while True:
        triggered = threading.Event()

        def _process(indata, frames, time_info, status):
            if status:
                logger.debug("wake_word: audio stream status: %s", status)
            if triggered.is_set():
                return
            audio_chunk = (indata[:, 0] * 32767).astype(np.int16)
            predictions = model.predict(audio_chunk)
            if predictions.get(WAKE_WORD_MODEL, 0.0) >= threshold:
                triggered.set()

        with sd.InputStream(
            samplerate=SAMPLE_RATE, blocksize=FRAME_SAMPLES, channels=1,
            dtype="float32", callback=_process,
        ):
            while not triggered.is_set():
                time.sleep(0.1)

        model.reset()
        _handle_wake(record_audio, transcribe, ask, speak)


def _handle_wake(record_audio, transcribe, ask, speak) -> None:
    print("[wake_word] Wake word detected -- listening for your command...")
    try:
        audio_path = record_audio(duration=5)
        if not audio_path:
            print("[wake_word] Microphone unavailable -- skipping this trigger.")
            return
        command = transcribe(audio_path)
        if not command or not command.strip():
            print("[wake_word] Didn't catch a command, going back to listening.")
            return
        print(f"[wake_word] Heard: {command!r}")
        result = ask(command, session_id="wake-word-desktop")
        answer = result.get("answer") or "I didn't get a response for that."
        print(f"[wake_word] Answer: {answer[:200]}")
        speak(answer)
    except Exception:
        logger.exception("wake_word: error handling a wake trigger")
        print("[wake_word] Something went wrong handling that -- back to listening.")


def main() -> int:
    try:
        run_wake_word_loop()
    except ImportError as exc:
        print(f"[wake_word] Missing dependency: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n[wake_word] Stopped.")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
