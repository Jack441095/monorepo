"""Voice Input / Speech-to-Text — enables Thursday to hear and transcribe speech.

Uses faster-whisper (CTranslate2) for efficient local transcription on Apple Silicon.

Usage:
    from thursday.voice import listen_for_wake_word, transcribe, continuous_mode
    text = listen_for_wake_word()  # Blocks until wake word + command detected
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))
from action_policy import action_allowed  # noqa: E402

logger = logging.getLogger(__name__)


# ─── STT backend selection ────────────────────────────────────────────────

# Prevent duplicate OpenMP runtime crash (PyTorch + CTranslate2 both ship libiomp5)
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

_fw_model = None
_MLX_PYTHON = "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13"
# Venv is x86_64 (Rosetta); MLX requires arm64 — force native arch for the subprocess
_MLX_CMD = ["arch", "-arm64", _MLX_PYTHON]


def _mlx_available() -> bool:
    """Check if mlx-whisper is available under arm64 Python."""
    try:
        result = subprocess.run(
            _MLX_CMD + ["-c", "import mlx_whisper; print('ok')"],
            capture_output=True, timeout=10,
        )
        return result.returncode == 0 and b"ok" in result.stdout
    except Exception:
        return False


_use_mlx: bool | None = None  # lazily detected


def normalize_transcript(text: str) -> str:
    """Correct assistant names when speech recognition returns common homophones."""
    cleaned = str(text or "").strip()
    if re.search(r"\b(?:speak|talk|switch|connect)\b.*\bken\b", cleaned, re.IGNORECASE):
        cleaned = re.sub(r"\bken\b", "KENN", cleaned, flags=re.IGNORECASE)
    return cleaned


_stt_worker_proc: subprocess.Popen | None = None
_stt_worker_lock = threading.Lock()


def _cleanup_stt_worker() -> None:
    global _stt_worker_proc
    if _stt_worker_proc is not None:
        try:
            _stt_worker_proc.kill()
        except Exception:
            pass
        _stt_worker_proc = None


import atexit
atexit.register(_cleanup_stt_worker)


def _get_persistent_stt_worker() -> subprocess.Popen | None:
    global _stt_worker_proc
    if _stt_worker_proc is not None:
        if _stt_worker_proc.poll() is None:
            return _stt_worker_proc
        else:
            try:
                _stt_worker_proc.kill()
            except Exception:
                pass
            _stt_worker_proc = None

    try:
        env = os.environ.copy()
        _stt_worker_proc = subprocess.Popen(
            _MLX_CMD + ["thursday/stt_worker.py"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            env=env,
        )
        return _stt_worker_proc
    except Exception:
        return None


def _transcribe_mlx_fallback(audio_path: str) -> str:
    """Per-call fallback: spawn a fresh subprocess that loads mlx-whisper."""
    script = f"""
import mlx_whisper, json, sys
result = mlx_whisper.transcribe(
    {audio_path!r},
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
print(result.get("text", "").strip())
"""
    try:
        r = subprocess.run(
            _MLX_CMD + ["-c", script],
            capture_output=True, text=True, timeout=30,
        )
        return r.stdout.strip()
    except Exception:
        logger.warning(
            "_transcribe_mlx_fallback failed; returning empty transcript "
            "(indistinguishable from the user saying nothing)",
            exc_info=True,
        )
        return ""


def _transcribe_mlx(audio_path: str) -> str:
    """Transcribe using the persistent mlx-whisper (Metal GPU) worker."""
    global _stt_worker_proc
    try:
        with _stt_worker_lock:
            proc = _get_persistent_stt_worker()
            if proc is not None and proc.stdin is not None and proc.stdout is not None:
                payload = json.dumps({"audio_path": audio_path})
                proc.stdin.write(payload + "\n")
                proc.stdin.flush()

                # Read JSON response line
                line = proc.stdout.readline()
                if line:
                    response = json.loads(line)
                    if "error" in response:
                        logger.error(f"STT worker returned error: {response['error']}")
                        return ""
                    return str(response.get("text", "")).strip()
    except Exception:
        logger.exception("Persistent STT transcription failed, falling back to subprocess")
        _cleanup_stt_worker()

    # Fallback to single-shot subprocess if persistent worker failed
    return _transcribe_mlx_fallback(audio_path)


def _get_model():
    """Load and cache the faster-whisper model (CPU fallback)."""
    global _fw_model
    if _fw_model is not None:
        return _fw_model

    thursday_dir = str(Path(__file__).parent)
    removed_indices = [i for i, p in enumerate(sys.path) if p == thursday_dir]
    for i in sorted(removed_indices, reverse=True):
        sys.path.pop(i)

    try:
        from faster_whisper import WhisperModel
        print("Loading speech recognition model (first time only)...")
        _fw_model = WhisperModel("small", device="cpu", compute_type="int8")
        print("Speech recognition ready.")
    except ImportError:
        print("faster-whisper not installed. Run: pip install faster-whisper")
    except Exception:
        logger.exception("Speech recognition model failed to load")
        print("Speech recognition model failed to load (error code: service_unavailable).")
    finally:
        for i in removed_indices:
            sys.path.insert(i, thursday_dir)

    return _fw_model


# ─── Record audio ────────────────────────────────────────────────────────


def record_audio(duration: int = 4, output_path: str | None = None) -> str:
    """Record audio from the microphone.

    Tries sounddevice (pure Python, triggers macOS permission prompt correctly),
    then falls back to sox and ffmpeg subprocesses.

    Returns:
        Path to the recorded WAV file, or empty string on failure.
    """
    if not action_allowed("audio_capture"):
        return ""

    if output_path is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        output_path = tmp.name
        tmp.close()

    # Primary: sounddevice — records in-process, gets macOS mic permission correctly
    try:
        import sounddevice as sd
        import soundfile as sf

        sample_rate = 16000
        audio = sd.rec(
            int(duration * sample_rate),
            samplerate=sample_rate,
            channels=1,
            dtype="int16",
        )
        sd.wait()
        sf.write(output_path, audio, sample_rate)
        if Path(output_path).exists() and Path(output_path).stat().st_size > 1000:
            return output_path
    except Exception:
        pass

    # Fallback: sox (rec)
    try:
        subprocess.run(
            ["rec", "-r", "16000", "-b", "16", "-c", "1", output_path,
             "trim", "0", str(duration)],
            capture_output=True,
            timeout=duration + 5,
        )
        if Path(output_path).exists() and Path(output_path).stat().st_size > 1000:
            return output_path
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    # Fallback: ffmpeg (avfoundation — macOS)
    try:
        subprocess.run(
            ["ffmpeg", "-f", "avfoundation", "-i", ":0",
             "-t", str(duration), "-acodec", "pcm_s16le",
             "-ar", "16000", "-ac", "1", output_path, "-y"],
            capture_output=True,
            timeout=duration + 10,
        )
        if Path(output_path).exists() and Path(output_path).stat().st_size > 1000:
            return output_path
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    return ""


# --- Speech & Audio Analysis (P0 STT metrics) ---

def analyze_clipping_noise(audio_path: str) -> dict[str, float | bool]:
    """Measure signal indicators (clipping, noise floor) and duration on a raw PCM file."""
    import wave
    import struct
    import math
    try:
        with wave.open(audio_path, "rb") as w:
            nchannels, sampwidth, framerate, nframes = w.getparams()[:4]
            if sampwidth != 2:
                return {"clipping": False, "noise_floor_db": -96.0, "duration": 0.0}
            raw_data = w.readframes(nframes)
            fmt = f"<{nframes * nchannels}h"
            samples = struct.unpack(fmt, raw_data)
            duration = nframes / framerate

            # 1. Clipping detection (values close to peak scale 16-bit limits)
            clip_count = sum(1 for s in samples if abs(s) >= 32760)
            clipping = clip_count > 10

            # 2. Quietest 100ms window RMS for noise floor
            window_size = int(framerate * nchannels * 0.1)
            if len(samples) < window_size:
                return {"clipping": clipping, "noise_floor_db": -96.0, "duration": duration}

            min_rms = float("inf")
            for i in range(0, len(samples) - window_size, window_size):
                win = samples[i : i + window_size]
                rms = math.sqrt(sum(s * s for s in win) / len(win))
                if rms < min_rms:
                    min_rms = rms

            max_rms = 32768.0 / math.sqrt(2.0)
            if min_rms <= 0:
                noise_floor_db = -96.0
            else:
                noise_floor_db = 20.0 * math.log10(min_rms / max_rms)

            return {
                "clipping": clipping,
                "noise_floor_db": round(noise_floor_db, 1),
                "duration": round(duration, 2),
            }
    except Exception:
        return {"clipping": False, "noise_floor_db": -96.0, "duration": 0.0}


def _transcribe_mlx_with_metadata(audio_path: str) -> dict:
    global _stt_worker_proc
    try:
        with _stt_worker_lock:
            proc = _get_persistent_stt_worker()
            if proc is not None and proc.stdin is not None and proc.stdout is not None:
                payload = json.dumps({"audio_path": audio_path})
                proc.stdin.write(payload + "\n")
                proc.stdin.flush()

                line = proc.stdout.readline()
                if line:
                    response = json.loads(line)
                    if "error" not in response:
                        return response
    except Exception:
        _cleanup_stt_worker()
    return {"text": _transcribe_mlx_fallback(audio_path), "confidence": 1.0, "no_speech_prob": 0.0, "language": "en"}


def transcribe_with_metadata(audio_path: str) -> dict:
    """Transcribe audio with confidence, no_speech_prob, language, duration, and clipping/noise floor."""
    if not audio_path or not Path(audio_path).exists():
        return {
            "text": "",
            "confidence": 0.0,
            "no_speech_prob": 1.0,
            "language": "en",
            "duration": 0.0,
            "clipping": False,
            "noise_floor_db": -96.0,
        }

    analysis = analyze_clipping_noise(audio_path)
    text = ""
    confidence = 1.0
    no_speech_prob = 0.0
    language = "en"

    global _use_mlx
    if _use_mlx is None:
        _use_mlx = _mlx_available()

    if _use_mlx:
        res = _transcribe_mlx_with_metadata(audio_path)
        text = res.get("text", "")
        confidence = res.get("confidence", 1.0)
        no_speech_prob = res.get("no_speech_prob", 0.0)
        language = res.get("language", "en")
    else:
        model = _get_model()
        if model is not None:
            try:
                segments, info = model.transcribe(audio_path, language="en", beam_size=5)
                segment_list = list(segments)
                text = " ".join(seg.text for seg in segment_list).strip()
                if segment_list:
                    no_speech_prob = sum(s.no_speech_prob for s in segment_list) / len(segment_list)
                    avg_logprob = sum(s.avg_logprob for s in segment_list) / len(segment_list)
                    import math
                    confidence = float(math.exp(avg_logprob))
                language = info.language
            except Exception:
                pass

    return {
        "text": normalize_transcript(text) if text else "",
        "confidence": round(confidence, 3),
        "no_speech_prob": round(no_speech_prob, 3),
        "language": language,
        "duration": analysis.get("duration", 0.0),
        "clipping": analysis.get("clipping", False),
        "noise_floor_db": analysis.get("noise_floor_db", -96.0),
    }


# ─── Transcribe ──────────────────────────────────────────────────────────


def transcribe(audio_path: str) -> str:
    """Transcribe an audio file to text.

    Tries mlx-whisper (Metal GPU, ~1s) first, falls back to faster-whisper (CPU, ~12s).

    Args:
        audio_path: Path to a WAV file.

    Returns:
        Transcribed text or empty string.
    """
    global _use_mlx

    if not audio_path or not Path(audio_path).exists():
        return ""

    # Detect MLX availability once
    if _use_mlx is None:
        _use_mlx = _mlx_available()
        if _use_mlx:
            print("[voice] Using mlx-whisper (Metal GPU) for transcription.")
        else:
            print("[voice] mlx-whisper not available — using faster-whisper (CPU).")

    if _use_mlx:
        text = _transcribe_mlx(audio_path)
        if text:
            return normalize_transcript(text)
        # MLX failed — fall through to faster-whisper

    model = _get_model()
    if model is None:
        return ""

    try:
        segments, _ = model.transcribe(
            audio_path,
            language="en",
            beam_size=5,
            initial_prompt=(
                "Audio engineering, Ableton Live, mixing, mastering, sidechain, compression, EQ, reverb, delay, "
                "snare, kick drum, bass, hi-hat, transient, attack, release, sustain, threshold, ratio, "
                "frequency, low-pass, high-pass, shelf, notch, gain, pan, stereo, mono, phase, "
                "saturation, distortion, parallel, bus, send, return, limiter, gate, de-esser, "
                "loudness, LUFS, true peak, headroom, render, bounce, automation, MIDI, warp."
            ),
        )
        return normalize_transcript(" ".join(seg.text for seg in segments))
    except Exception:
        logger.warning(
            "faster-whisper transcription failed; returning empty transcript "
            "(indistinguishable from the user saying nothing)",
            exc_info=True,
        )
        return ""


# ─── Wake word detection ─────────────────────────────────────────────────


def strip_wake_word(text: str, wake_word: str) -> str:
    """Strip the wake word and any typical suffixes ('s, s, etc.) or leading punctuation."""
    import re
    cleaned = text.strip()
    lowered = cleaned.lower()
    wake_lower = wake_word.lower().strip()
    
    if wake_lower in lowered:
        pattern = rf"\b{re.escape(wake_lower)}(?:'s|s)?\b"
        match = re.search(pattern, lowered)
        if match:
            _, end = match.span()
            command = cleaned[end:].strip()
            command = re.sub(r"^[^\w\s]+", "", command).strip()
            return command
            
    return cleaned


def listen_for_wake_word(wake_word: str = "thursday", timeout: int = 60) -> str | None:
    """Listen for a wake word then return the command that follows it.

    Records 4-second clips in a loop, transcribes each, and checks for
    the wake word. Returns the text after the wake word, or None on timeout.

    Args:
        wake_word: Word(s) to listen for (case-insensitive).
        timeout:   Max seconds to wait before giving up.

    Returns:
        Command text (wake word stripped) or None.
    """
    wake_word_lower = wake_word.lower().strip()
    start_time = time.time()

    print(f"🎤 Listening for '{wake_word.title()}'... (Ctrl+C to stop)")

    while time.time() - start_time < timeout:
        audio_file = record_audio(duration=4)

        if not audio_file:
            elapsed = int(time.time() - start_time)
            sys.stdout.write(f"\r🎤 Listening... ({elapsed}s) [mic not available]")
            sys.stdout.flush()
            time.sleep(1)
            continue

        text = transcribe(audio_file)

        try:
            os.unlink(audio_file)
        except OSError:
            pass

        if text:
            text_lower = text.lower().strip()
            if wake_word_lower in text_lower:
                command = strip_wake_word(text, wake_word)

                # Wake word heard but no command in same clip — record a follow-up clip
                if not command:
                    print("\n🗣  Heard wake word. Listening for your question...")
                    followup_file = record_audio(duration=6)
                    if followup_file:
                        raw_followup = transcribe(followup_file).strip()
                        command = strip_wake_word(raw_followup, wake_word)
                        try:
                            os.unlink(followup_file)
                        except OSError:
                            pass

                if command:
                    print(f"\n🗣  Heard: Thursday, {command}")
                    return command

        elapsed = int(time.time() - start_time)
        sys.stdout.write(f"\r🎤 Listening... ({elapsed}s)")
        sys.stdout.flush()

    print("\n🎤 Listening timed out.")
    return None


# ─── Continuous listening mode ───────────────────────────────────────────


def stream_kenn_answer(query: str, *, limit: int = 6, session_id: str | None = None, _stream_fn=None):
    """Yield speakable text tokens from KENN's streaming answer path.

    Feeds speak_streaming so a voice answer begins speaking sentence-by-sentence
    as KENN generates it, instead of waiting for the whole answer. ``_stream_fn``
    is an injection point for tests.
    """
    if _stream_fn is None:
        from thursday.bridge import ask_stream
        events = ask_stream(query, session_id=session_id or "")
    else:
        events = _stream_fn(query, limit=limit, session_id=session_id)

    for event in events:
        if event.get("event") == "token":
            token = event.get("token")
            if token:
                yield token


def execute_voice_command_result(command: str, session: dict | None, handle_func: Callable):
    """Execute a blocking voice command and retain its typed result envelope."""
    from thursday.command_gateway import command_for_text, execute_command

    envelope = command_for_text(command, actor_id="voice")
    return execute_command(envelope, session=session, handle_fn=handle_func)


def execute_voice_command(command: str, session: dict | None, handle_func: Callable) -> str:
    """Execute a blocking voice command through the shared result contract."""
    result = execute_voice_command_result(command, session, handle_func)
    if result.error is not None:
        return result.error.message
    return str(result.result.get("answer") or "")


def continuous_mode(handle_func: Callable, wake_word: str = "thursday") -> None:
    """Enter continuous listening mode.

    Preloads the STT model, then loops: wake word → command → response → repeat.

    Args:
        handle_func: Thursday orchestrator handle(text, session) function.
        wake_word:   Wake word to listen for.
    """
    print(f"🔊 Thursday continuous mode. Say '{wake_word.title()}' followed by your request.")
    print("Press Ctrl+C to exit.\n")

    # Preload model before the loop — avoids download interruptions
    if _get_model() is None:
        print("Cannot start voice mode: speech recognition unavailable.")
        return

    # Use a persistent session for the whole voice conversation
    try:
        from thursday.session_manager import get_or_create_session
        _session = get_or_create_session()
        # Flag voice mode so orchestrator routes to the fast 1.5b model
        if _session is not None:
            _session.setdefault("context", {})["_voice_mode"] = True
    except Exception:
        _session = None

    try:
        while True:
            command = listen_for_wake_word(wake_word=wake_word, timeout=60)

            if not command:
                # Timeout — just restart the listen loop
                continue

            active_voice = (_session or {}).get("context", {}).get("active_voice", "thursday")

            # Streaming TTS for production questions: speak sentence-by-sentence as KENN
            # generates, so speech begins ~1-2 s in instead of after 6-8 s. On by default
            # (validated); set THURSDAY_STREAMING_VOICE=0 to fall back to blocking playback.
            streaming_voice = os.environ.get("THURSDAY_STREAMING_VOICE", "1").strip().lower() in {
                "1", "true", "yes", "on",
            }
            spoke_streamed = False
            if streaming_voice:
                try:
                    from thursday.voice_output import speak_streaming
                    spoken = speak_streaming(
                        stream_kenn_answer(
                            command,
                            session_id=(_session or {}).get("session_id"),
                        ),
                        kenn=(active_voice == "kenn"),
                    )
                    print(f"🤖 {'KENN' if active_voice == 'kenn' else 'Thursday'}: {spoken}\n")
                    if _session is not None:
                        from thursday.session_manager import load_session
                        _session = load_session(_session.get("session_id", "")) or _session
                    spoke_streamed = bool(spoken.strip())
                except Exception:
                    spoke_streamed = False

            if not spoke_streamed:
                # Route through Thursday (blocking full answer)
                answer = execute_voice_command(command, _session, handle_func)

                print(f"🤖 Thursday: {answer}\n")

                # Speak using the active voice character
                try:
                    from thursday.voice_output import extract_for_voice, speak_async
                    spoken = extract_for_voice(answer)
                    speak_async(spoken, voice=active_voice)
                except Exception:
                    pass

    except KeyboardInterrupt:
        print("\n👋 Exiting voice mode.")


import queue


class StreamingVoicePipeline:
    """Low-latency streaming voice pipeline managing audio chunk queues for sub-300ms speech interaction."""

    def __init__(self, target_latency_ms: float = 300.0):
        self.target_latency_ms = target_latency_ms
        self._audio_queue: queue.Queue[bytes] = queue.Queue()
        self._is_active: bool = False
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            self._is_active = True
            logger.info("StreamingVoicePipeline started with target latency %sms", self.target_latency_ms)

    def stop(self) -> None:
        with self._lock:
            self._is_active = False

    def push_audio_chunk(self, chunk: bytes) -> bool:
        """Enqueue a raw PCM audio chunk for real-time STT processing."""
        if not self._is_active:
            return False
        self._audio_queue.put(chunk)
        return True

    def get_next_chunk(self, timeout: float = 0.5) -> bytes | None:
        """Retrieve the next audio chunk from the queue."""
        try:
            return self._audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None
