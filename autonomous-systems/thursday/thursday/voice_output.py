"""Voice Output / Text-to-Speech — Thursday speaks aloud.

Supports:
  - Kokoro (MIT, local, high-quality neural TTS — preferred)
  - macOS `say` command (built-in fallback)

Kokoro model files live at:
  studio/kenn/kenn/artifacts/models/kokoro/
"""

from __future__ import annotations

import logging
import platform
import queue
import re
import json
import os
import subprocess
import sys
import tempfile
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any

# ONNX_SESSION_INIT_LOCK coordinates native ONNX runtime initialisation
# process-wide. In the live deployment (Thursday running inside the
# Audio_Too Flask process) it must be the *same* lock object audio_too's own
# model_runtime uses, so the two don't race each other in-process -- a real
# integration point, not vendorable as an independent object without losing
# that shared coordination. Standalone (this repo, no audio_too in-process),
# there is nothing else in the process to coordinate with, so a fresh local
# lock is a safe, correct fallback -- see docs/EXTRACTION_COUPLING.md.
try:
    from audio_too.model_runtime import ONNX_SESSION_INIT_LOCK
except ImportError:
    ONNX_SESSION_INIT_LOCK = threading.RLock()

from thursday.repo_root import audio_too_root

# Kokoro's G2P (misaki) pulls in the HuggingFace Rust `tokenizers` lib. When the
# TTS worker is forked, tokenizers disables its own parallelism after the fork and
# emits a blocking warning on first tokenise — measurable added latency on
# time-to-first-audio. Declaring the intent up front (before any tokeniser import)
# avoids that post-fork stall. setdefault so an explicit env override still wins.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

logger = logging.getLogger(__name__)

# ─── Kokoro TTS ──────────────────────────────────────────────────────────

_KOKORO_DIR = audio_too_root() / "studio" / "kenn" / "kenn" / "artifacts" / "models" / "kokoro"
_KOKORO_MODEL = _KOKORO_DIR / "kokoro-v1.0.int8.onnx"
_KOKORO_VOICES = _KOKORO_DIR / "voices-v1.0.bin"

_kokoro: Any = None
_kokoro_lock = threading.Lock()
_synthesis_lock = threading.Lock()
_kokoro_available: bool | None = None

KOKORO_VOICE = "af_heart"   # Thursday's voice — warm female
KOKORO_SPEED = 1.1          # slightly faster than default for studio use

KENN_VOICE = "am_onyx"      # KENN's voice — distinct male
KENN_SPEED = 1.0

AGENT_VOICES = {
    "thursday": "af_heart",
    "kenn": "am_onyx",
    "adam": "am_adam",
    "admin": "am_adam",
    "mark": "af_bella",
    "marketing": "af_bella",
    "rhianna": "am_michael",
    "research": "am_michael",
}


def _load_kokoro() -> Any:
    global _kokoro, _kokoro_available
    with _kokoro_lock:
        if _kokoro_available is False:
            return None
        if _kokoro is not None:
            return _kokoro
        try:
            from kokoro_onnx import Kokoro
            import onnxruntime as ort
            import sys
            
            providers = ort.get_available_providers()
            if "CoreMLExecutionProvider" in providers and sys.platform == "darwin":
                try:
                    cache_dir = audio_too_root() / "data" / "coreml_cache"
                    cache_dir.mkdir(parents=True, exist_ok=True)
                    
                    with ONNX_SESSION_INIT_LOCK:
                        sess = ort.InferenceSession(
                            str(_KOKORO_MODEL),
                            providers=[
                                ("CoreMLExecutionProvider", {"ModelCacheDirectory": str(cache_dir)}),
                                "CPUExecutionProvider"
                            ]
                        )
                        _kokoro = Kokoro.from_session(sess, str(_KOKORO_VOICES))
                    _kokoro_available = True
                    return _kokoro
                except Exception:
                    logger.warning(
                        "Kokoro TTS CoreML initialization failed; falling back to CPU",
                        exc_info=True
                    )
            
            with ONNX_SESSION_INIT_LOCK:
                _kokoro = Kokoro(str(_KOKORO_MODEL), str(_KOKORO_VOICES))
            _kokoro_available = True
            return _kokoro
        except Exception:
            logger.warning(
                "Kokoro TTS model failed to load; silently downgrading to macOS `say` "
                "for the rest of this process's lifetime",
                exc_info=True,
            )
            _kokoro_available = False
            return None


def _kokoro_speak(text: str, voice: str | None = None, block: bool = True) -> bool:
    """Synthesise text with Kokoro and play via afplay. Returns True on success."""
    try:
        v = voice if voice is not None else KOKORO_VOICE
        v = AGENT_VOICES.get(v.lower(), v)
        wav = synthesise_isolated(text, voice=v, speed=KOKORO_SPEED)
        if not wav:
            return False
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp = f.name
            f.write(wav)
        if block:
            subprocess.run(["afplay", tmp], check=False, timeout=max(30, len(text) // 5))
        else:
            subprocess.Popen(["afplay", tmp], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


# ─── SSML-style expressive pauses ─────────────────────────────────────────
#
# A minimal, deliberately narrow SSML subset -- just <break time="500ms"/> /
# <break time="1s"/> -- so an LLM-generated voice answer (or a hand-written
# static fallback) can ask for a real pause between phrases instead of
# Kokoro reading everything at one flat pace. Not a general SSML parser: no
# nesting, no other tags, no attribute variations -- exactly the one shape
# thursday/voice_output.py's callers are expected to produce.
_BREAK_TAG_RE = re.compile(r'<break\s+time="(\d+)(ms|s)"\s*/>')


def _parse_ssml_breaks(text: str) -> list[tuple[str, float]]:
    """Split text on <break time="..."/> tags into (segment_text, pause_after_s) pairs.

    Each pair's pause_after_s is the silence to insert immediately after that
    segment's speech, before the next one. Text with no break tags returns a
    single ``[(text.strip(), 0.0)]`` entry -- callers can treat "len == 1"
    as "no breaks present, use the normal synthesis path unchanged".
    """
    segments: list[tuple[str, float]] = []
    pos = 0
    for match in _BREAK_TAG_RE.finditer(text):
        segments.append((text[pos:match.start()].strip(), _break_seconds(match)))
        pos = match.end()
    segments.append((text[pos:].strip(), 0.0))
    return segments


def _break_seconds(match: re.Match) -> float:
    value, unit = match.group(1), match.group(2)
    return float(value) / 1000.0 if unit == "ms" else float(value)


# ─── Synthesise to bytes (for browser playback) ──────────────────────────


# --- Opt-in parallel-chunk synthesis (2026-07-19) -------------------------
#
# Investigation (docs/audits/2026-07-19-tts-latency-optimization.md): the
# ~2s steady-state TTS SLO miss is genuine ONNX CPU inference compute, not
# IPC/phonemization overhead (cProfile: 2.15s of 2.15s total inside
# onnxruntime's session.run()). The model is already int8-quantized;
# CoreML and thread-count tuning were already tried and re-confirmed here
# to give no improvement (both previously rejected, see project memory).
# session.run() DOES release the GIL during inference, though: splitting
# a sentence into independent chunks and synthesising them concurrently in
# threads measured ~35% faster wall time (1.38s vs 2.07s for the same
# text) with no wire-protocol change needed -- still one complete WAV out.
#
# NOT wired in as the default: splitting happens at clause boundaries
# (commas/semicolons), not sentence boundaries, because the SLO test
# sentences are single sentences with no safe sentence-boundary split
# point. Each chunk is synthesised independently with no shared prosody
# context, which risks sounding choppier at the split than one continuous
# read -- an audible-quality question nothing in this codebase can verify
# without a human listening. Opt-in via THURSDAY_TTS_PARALLEL_CHUNKS=1
# (unset/0 = today's unchanged sequential behaviour) until validated by
# ear and explicitly promoted.
_CLAUSE_BOUNDARY = re.compile(r"[,;:]\s+")
_MIN_CHUNK_CHARS = 12  # avoid splitting off fragments too short to amortise thread overhead
_MAX_CHUNKS = 4


def _split_at_word_midpoint(text: str) -> list[str]:
    """Fallback for punctuation-free text: split at the word boundary
    closest to the character midpoint.

    Punctuation-free single sentences (e.g. "Cut two point five kilohertz to
    reduce harshness.") have no clause boundary for ``_CLAUSE_BOUNDARY`` to
    find, but are exactly the case where parallel synthesis has the most
    latency to gain (nothing to overlap with a real clause boundary if the
    sentence never had one). Word-boundary splitting has no grammatical
    signal for *where* a listener would expect a pause, unlike a comma/
    semicolon, so this carries more prosody risk than the clause-boundary
    path above -- accepted as a known, unverified tradeoff (see
    docs/audits/2026-07-19-tts-latency-optimization.md's promotion note).
    """
    words = text.split(" ")
    if len(words) < 4:
        return [text]
    target = len(text) / 2
    best_i, best_dist = None, None
    running = 0
    for i in range(1, len(words)):
        running += len(words[i - 1]) + 1  # +1 for the space
        dist = abs(running - target)
        if best_dist is None or dist < best_dist:
            best_i, best_dist = i, dist
    if best_i is None:
        return [text]
    first = " ".join(words[:best_i]).strip()
    second = " ".join(words[best_i:]).strip()
    if len(first) < _MIN_CHUNK_CHARS or len(second) < _MIN_CHUNK_CHARS:
        return [text]
    return [first, second]


def _split_into_synthesis_chunks(text: str) -> list[str]:
    """Split text for parallel synthesis: clause boundaries first, falling
    back to a word-midpoint split for punctuation-free text.

    Falls back to a single chunk (no parallelism) whenever splitting
    wouldn't produce at least two chunks that both clear
    ``_MIN_CHUNK_CHARS`` -- there's nothing to gain from parallelising a
    short phrase, and every extra chunk is an extra full model-inference
    call.
    """
    text = text.strip()
    if not text:
        return []
    pieces = [p.strip() for p in _CLAUSE_BOUNDARY.split(text) if p.strip()]
    if len(pieces) < 2:
        return _split_at_word_midpoint(text)
    if any(len(p) < _MIN_CHUNK_CHARS for p in pieces):
        return [text]
    if len(pieces) > _MAX_CHUNKS:
        # Merge the tail into the last kept chunk rather than spawning
        # unbounded threads for a very long, comma-heavy sentence.
        pieces = pieces[: _MAX_CHUNKS - 1] + [" ".join(pieces[_MAX_CHUNKS - 1 :])]
    return pieces


def _synthesise_chunks_parallel(
    kokoro: Any, chunks: list[str], *, voice: str, speed: float
) -> tuple[Any, int] | None:
    """Synthesise each chunk concurrently and concatenate in original order.

    Returns ``(samples, sample_rate)`` or ``None`` if any chunk failed.
    A short fixed silence gap is inserted between chunks to approximate the
    pause the source punctuation implied -- not perceptually tuned, just a
    placeholder pending a real listen.
    """
    import numpy as np

    from concurrent.futures import ThreadPoolExecutor

    results: list[tuple[Any, int] | None] = [None] * len(chunks)

    def _run(i: int, chunk: str) -> None:
        try:
            results[i] = kokoro.create(chunk, voice=voice, speed=speed, lang="en-us")
        except Exception:
            results[i] = None

    with ThreadPoolExecutor(max_workers=len(chunks)) as pool:
        list(pool.map(lambda item: _run(*item), enumerate(chunks)))

    if any(r is None for r in results):
        return None

    sample_rates = {sr for _samples, sr in results}
    if len(sample_rates) != 1:
        return None
    sr = sample_rates.pop()

    gap = np.zeros(int(sr * 0.08), dtype=results[0][0].dtype)
    pieces: list[Any] = []
    for i, (samples, _sr) in enumerate(results):
        if i > 0:
            pieces.append(gap)
        pieces.append(samples)
    return np.concatenate(pieces), sr


def _synthesise_with_breaks(
    kokoro: Any, segments: list[tuple[str, float]], *, voice: str, speed: float
) -> tuple[Any, int] | None:
    """Synthesise each (text, pause_after_s) segment in order, splicing in
    real silence for each requested pause. Sequential, not parallel (unlike
    _synthesise_chunks_parallel above) -- pause placement/ordering fidelity
    matters more here than throughput, since the pause was explicitly
    requested, not inferred from punctuation.

    Returns ``(samples, sample_rate)``, or None if any non-empty segment
    fails to synthesise or segments disagree on sample rate.
    """
    import numpy as np

    pieces: list[Any] = []
    sr: int | None = None
    dtype = None
    pending_leading_pause = 0.0

    for seg_text, pause_after_s in segments:
        if seg_text:
            try:
                samples, seg_sr = kokoro.create(seg_text, voice=voice, speed=speed, lang="en-us")
            except Exception:
                return None
            if sr is None:
                sr, dtype = seg_sr, samples.dtype
                if pending_leading_pause > 0:
                    pieces.append(np.zeros(int(sr * pending_leading_pause), dtype=dtype))
                    pending_leading_pause = 0.0
            elif seg_sr != sr:
                return None
            pieces.append(samples)
            if pause_after_s > 0:
                pieces.append(np.zeros(int(sr * pause_after_s), dtype=dtype))
        elif pause_after_s > 0:
            # Empty segment (a leading break, or two breaks back-to-back) --
            # if nothing has been synthesised yet, sr/dtype aren't known, so
            # carry the pause forward and apply it once the first real
            # segment establishes them.
            if sr is not None:
                pieces.append(np.zeros(int(sr * pause_after_s), dtype=dtype))
            else:
                pending_leading_pause += pause_after_s

    if not pieces or sr is None:
        return None
    return np.concatenate(pieces), sr


def _parallel_chunks_enabled() -> bool:
    # Promoted to default-on 2026-07-20 (Jack's explicit call, docs/audits/
    # 2026-07-19-tts-latency-optimization.md's "what would need to happen to
    # promote" checklist item 1 -- a real listen for the mid-sentence-split
    # prosody risk -- was accepted as an unverified risk rather than done).
    # THURSDAY_TTS_PARALLEL_CHUNKS=0 remains a fast rollback switch if an
    # audible seam turns up in practice.
    return os.getenv("THURSDAY_TTS_PARALLEL_CHUNKS", "1").strip() not in ("0", "false", "no")


@lru_cache(maxsize=32)
def synthesise(text: str, voice: str = KOKORO_VOICE, speed: float | None = None) -> bytes | None:
    """Generate speech as raw WAV bytes without playing. Returns None on failure.

    Used by the HTTP server to stream audio to the browser.
    """
    import io
    clean_text = _sanitize_for_speech(text)
    if not clean_text.strip():
        return None
    kokoro = _load_kokoro()
    if kokoro is None:
        return None
    try:
        import soundfile as sf
        _speed = speed if speed is not None else (KENN_SPEED if voice == KENN_VOICE else KOKORO_SPEED)
        v = AGENT_VOICES.get(voice.lower(), voice)
        # ONNX sessions may be called by multiple request threads.  Serialising
        # generation avoids corrupt/failed audio while still allowing the web
        # server to answer unrelated requests concurrently.
        with _synthesis_lock:
            break_segments = _parse_ssml_breaks(clean_text)
            if len(break_segments) > 1:
                # <break time="..."/> tags present -- synthesise segment-by-
                # segment with real silence spliced in, bypassing the normal
                # clause-based parallel-chunk path below (pause fidelity and
                # ordering matter more here than synthesis throughput).
                break_result = _synthesise_with_breaks(kokoro, break_segments, voice=v, speed=_speed)
                if break_result is not None:
                    samples, sr = break_result
                else:
                    # Fall back to reading the segments back-to-back with no
                    # pauses, never the raw clean_text -- that still contains
                    # the literal <break time="..."/> tag text, which Kokoro
                    # would otherwise try to pronounce verbatim.
                    flattened = " ".join(seg for seg, _pause in break_segments if seg)
                    samples, sr = kokoro.create(flattened, voice=v, speed=_speed, lang="en-us")
            else:
                chunks = _split_into_synthesis_chunks(clean_text) if _parallel_chunks_enabled() else [clean_text]
                if len(chunks) > 1:
                    parallel_result = _synthesise_chunks_parallel(kokoro, chunks, voice=v, speed=_speed)
                    if parallel_result is not None:
                        samples, sr = parallel_result
                    else:
                        samples, sr = kokoro.create(clean_text, voice=v, speed=_speed, lang="en-us")
                else:
                    samples, sr = kokoro.create(clean_text, voice=v, speed=_speed, lang="en-us")
        buf = io.BytesIO()
        sf.write(buf, samples, sr, format="WAV")
        return buf.getvalue()
    except Exception:
        return None


def _system_voice_wav(text: str) -> bytes | None:
    """Use the macOS system voice when the isolated neural worker fails."""
    if sys.platform != "darwin":
        return None
    aiff_path = ""
    try:
        import io
        import soundfile as sf

        with tempfile.NamedTemporaryFile(suffix=".aiff", delete=False) as handle:
            aiff_path = handle.name
        completed = subprocess.run(
            ["say", "-o", aiff_path, text],
            capture_output=True,
            timeout=max(15, len(text) // 5),
            check=False,
        )
        if completed.returncode:
            return None
        samples, sample_rate = sf.read(aiff_path, dtype="float32")
        output = io.BytesIO()
        sf.write(output, samples, sample_rate, format="WAV")
        return output.getvalue()
    except (OSError, subprocess.SubprocessError, RuntimeError, ValueError):
        return None
    finally:
        if aiff_path:
            Path(aiff_path).unlink(missing_ok=True)


import atexit

_worker_proc: subprocess.Popen | None = None
_worker_lock = threading.Lock()


def _cleanup_worker() -> None:
    global _worker_proc
    if _worker_proc is not None:
        try:
            _worker_proc.kill()
        except Exception:
            pass
        _worker_proc = None


atexit.register(_cleanup_worker)


def _read_exact(stream, n: int) -> bytes:
    data = b""
    while len(data) < n:
        chunk = stream.read(n - len(data))
        if not chunk:
            break
        data += chunk
    return data


# ─── Optional MLX-native fast path (local-only, GPL-adjacent — see
# thursday/tts_worker_mlx.py's module docstring and
# docs/AUDIO_MVP_MASTER_PLAN.md §5b before touching this). Opt-in only via
# AUDIO_TOO_MLX_TTS=1 — never auto-detected/auto-enabled, so a distributed
# build with no env config for this is guaranteed to stay on the MIT/Apache
# ONNX path with zero code changes needed. ~5-6x faster when enabled
# (measured 2026-07-09: ~0.5s/sentence steady-state vs ~3.6-4.2s for ONNX).
_MLX_PYTHON = "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13"
_MLX_CMD = ["arch", "-arm64", _MLX_PYTHON]
_mlx_worker_proc: subprocess.Popen | None = None
_mlx_worker_lock = threading.Lock()
_mlx_tts_available: bool | None = None


def _mlx_tts_enabled() -> bool:
    return os.getenv("AUDIO_TOO_MLX_TTS", "") == "1"


def _cleanup_mlx_worker() -> None:
    global _mlx_worker_proc
    if _mlx_worker_proc is not None:
        try:
            _mlx_worker_proc.kill()
        except Exception:
            pass
        _mlx_worker_proc = None


atexit.register(_cleanup_mlx_worker)


def _get_persistent_mlx_worker() -> subprocess.Popen | None:
    global _mlx_worker_proc, _mlx_tts_available
    if _mlx_tts_available is False:
        return None
    if _mlx_worker_proc is not None:
        if _mlx_worker_proc.poll() is None:
            return _mlx_worker_proc
        _cleanup_mlx_worker()

    try:
        _mlx_worker_proc = subprocess.Popen(
            _MLX_CMD + ["-m", "thursday.tts_worker_mlx", "--persistent"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        _mlx_tts_available = True
        return _mlx_worker_proc
    except Exception:
        _mlx_tts_available = False
        return None


def _synthesise_mlx(text: str, voice: str, speed: float | None) -> bytes | None:
    """Try the MLX-native fast path; returns None on any failure so the
    caller falls through to the standard ONNX worker automatically."""
    if not _mlx_tts_enabled():
        return None
    try:
        with _mlx_worker_lock:
            proc = _get_persistent_mlx_worker()
            if proc is None or proc.stdin is None or proc.stdout is None:
                return None
            payload = json.dumps({"text": text, "voice": voice, "speed": speed})
            proc.stdin.write((payload + "\n").encode("utf-8"))
            proc.stdin.flush()

            len_bytes = _read_exact(proc.stdout, 4)
            if len(len_bytes) != 4:
                _cleanup_mlx_worker()
                return None
            length = int.from_bytes(len_bytes, byteorder="big")
            if length <= 0:
                return None
            wav = _read_exact(proc.stdout, length)
            if len(wav) == length and wav.startswith(b"RIFF"):
                return wav
            _cleanup_mlx_worker()
            return None
    except Exception:
        _cleanup_mlx_worker()
        return None


def _get_persistent_worker() -> subprocess.Popen | None:
    global _worker_proc
    if _worker_proc is not None:
        if _worker_proc.poll() is None:
            return _worker_proc
        else:
            try:
                _worker_proc.kill()
            except Exception:
                pass
            _worker_proc = None

    try:
        env = os.environ.copy()
        env["AUDIO_TOO_TTS_WORKER"] = "1"
        _worker_proc = subprocess.Popen(
            [*_tts_worker_python_command(), "-m", "thursday.tts_worker", "--persistent"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
        )
        return _worker_proc
    except Exception:
        return None


@lru_cache(maxsize=1)
def _tts_worker_python_command() -> tuple[str, ...]:
    """Prefer a native-arm64 ONNX worker when the main app runs under Rosetta.

    Kokoro's ONNX synthesis is materially faster natively. The parent process
    may still use the x86_64 compatibility environment for legacy Torch, so run
    only the isolated TTS worker with native Python when that interpreter has
    the required MIT/Apache runtime dependencies. Fall back to the current
    interpreter if the probe fails; synthesis already has its own safe system-
    voice fallback.
    """
    configured = os.getenv("AUDIO_TOO_TTS_PYTHON", "").strip()
    if configured and Path(configured).expanduser().is_file():
        return (str(Path(configured).expanduser()),)
    if sys.platform != "darwin" or platform.machine() == "arm64":
        return (sys.executable,)

    candidate = Path("/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13")
    if not candidate.is_file():
        return (sys.executable,)
    command = ("arch", "-arm64", str(candidate))
    try:
        completed = subprocess.run(
            [*command, "-c", "import kokoro_onnx, onnxruntime, soundfile"],
            cwd=str(Path(__file__).resolve().parent.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return (sys.executable,)
    return command if completed.returncode == 0 else (sys.executable,)


def synthesise_isolated(
    text: str,
    voice: str = KOKORO_VOICE,
    speed: float | None = None,
) -> bytes | None:
    """Run native neural TTS out of process so an abort cannot kill the hub."""
    clean_text = _sanitize_for_speech(text)
    if not clean_text:
        return None
    if os.getenv("AUDIO_TOO_TTS_WORKER", "") == "1":
        return synthesise(clean_text, voice=voice, speed=speed)

    # 0. Optional MLX-native fast path (opt-in, AUDIO_TOO_MLX_TTS=1 only —
    # see the licensing note above _get_persistent_mlx_worker). No-op
    # (returns None immediately) unless explicitly enabled.
    mlx_wav = _synthesise_mlx(clean_text, voice, speed)
    if mlx_wav is not None:
        return mlx_wav

    # 1. Attempt using the persistent worker process
    global _worker_proc
    try:
        with _worker_lock:
            proc = _get_persistent_worker()
            if proc is not None and proc.stdin is not None and proc.stdout is not None:
                payload = json.dumps({"text": clean_text, "voice": voice, "speed": speed})
                proc.stdin.write((payload + "\n").encode("utf-8"))
                proc.stdin.flush()

                # Read 4-byte length prefix
                len_bytes = _read_exact(proc.stdout, 4)
                if len(len_bytes) == 4:
                    length = int.from_bytes(len_bytes, byteorder="big")
                    if length > 0:
                        wav = _read_exact(proc.stdout, length)
                        if len(wav) == length and wav.startswith(b"RIFF"):
                            return wav
                        # If invalid data is returned, clean up to spawn a new one next time
                        _cleanup_worker()
                    else:
                        # 0 length means synthesis failure or error in worker
                        pass
                else:
                    # Connection closed or failed, clean up
                    _cleanup_worker()
    except Exception:
        _cleanup_worker()

    # 2. Legacy fallback to single-shot execution if persistent mode failed/errored
    payload = json.dumps({"text": clean_text, "voice": voice, "speed": speed})
    env = os.environ.copy()
    env["AUDIO_TOO_TTS_WORKER"] = "1"
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "thursday.tts_worker"],
            input=payload.encode("utf-8"),
            capture_output=True,
            env=env,
            timeout=max(30, len(clean_text) // 4),
            check=False,
        )
        if completed.returncode == 0 and completed.stdout.startswith(b"RIFF"):
            return completed.stdout
    except (OSError, subprocess.SubprocessError):
        pass

    return _system_voice_wav(clean_text)


def warm_tts() -> bool:
    """Probe TTS without exposing the website process to native-library aborts."""
    return synthesise_isolated("Ready.") is not None


# ─── KENN voice (male, distinct from Thursday) ───────────────────────────


def speak_as_kenn(text: str, block: bool = True) -> bool:
    """Synthesise text using KENN's male voice. Returns True on success."""
    clean_text = _sanitize_for_speech(text)
    if not clean_text.strip():
        return False
    try:
        wav = synthesise_isolated(clean_text, voice=KENN_VOICE, speed=KENN_SPEED)
        if not wav:
            return False
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp = f.name
            f.write(wav)
        if block:
            subprocess.run(["afplay", tmp], check=False, timeout=max(30, len(clean_text) // 5))
        else:
            subprocess.Popen(["afplay", tmp], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def speak_kenn_async(text: str) -> bool:
    """Speak as KENN non-blocking. Falls back to macOS 'Alex' voice."""
    if not text:
        return False
    clean_text = _sanitize_for_speech(text)
    if not clean_text.strip():
        return False

    def _run() -> None:
        if not speak_as_kenn(clean_text, block=True):
            try:
                subprocess.Popen(
                    ["say", "-v", "Alex", clean_text],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except (FileNotFoundError, OSError):
                pass

    threading.Thread(target=_run, daemon=True).start()
    return True


# ─── macOS Voices (fallback) ─────────────────────────────────────────────

AVAILABLE_VOICES = {
    "samantha": "Samantha",
    "fiona": "Fiona",
    "kate": "Kate",
    "alex": "Alex",
    "tom": "Tom",
    "daniel": "Daniel",
    "oliver": "Oliver",
    "serena": "Serena",
    "veena": "Veena",
    "moira": "Moira",
}

DEFAULT_VOICE = "Samantha"


def list_available_voices() -> list[dict]:
    """List all available macOS voices.

    Returns:
        List of {"name": voice_name, "language": language_code} dicts.
    """
    try:
        result = subprocess.run(
            ["say", "-v", "?"],
            capture_output=True, text=True, timeout=10,
        )
        voices = []
        for line in (result.stdout or "").split("\n"):
            if line.strip():
                parts = line.split()
                if parts:
                    voice_name = parts[0]
                    lang = parts[1] if len(parts) > 1 else "en"
                    voices.append({"name": voice_name, "language": lang})
        return voices
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return []


def speak(text: str, voice: str = DEFAULT_VOICE, rate: int = 200) -> bool:
    """Read text aloud — Kokoro neural TTS first, macOS say as fallback."""
    if not text:
        return False
    clean_text = _sanitize_for_speech(text)
    if not clean_text.strip():
        return False

    if _kokoro_speak(clean_text, block=True):
        return True

    # macOS say fallback
    try:
        voice_flag = voice if voice in list(AVAILABLE_VOICES.values()) else DEFAULT_VOICE
        subprocess.run(
            ["say", "-v", voice_flag, "-r", str(rate), clean_text],
            capture_output=False,
            timeout=max(30, len(clean_text) * 3),
            check=True,
        )
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.CalledProcessError, OSError):
        return False


def speak_async(text: str, voice: str = "thursday", rate: int = 200) -> bool:
    """Read text aloud non-blocking — Kokoro first, macOS say as fallback."""
    if not text:
        return False
    clean_text = _sanitize_for_speech(text)
    if not clean_text.strip():
        return False

    def _run() -> None:
        if not _kokoro_speak(clean_text, voice=voice, block=True):
            try:
                # Map agent voice to macOS voice fallback
                say_voice = DEFAULT_VOICE
                if voice.lower() in ("kenn", "adam", "admin", "research", "rhianna"):
                    say_voice = "Alex"
                elif voice.lower() in ("marketing", "mark"):
                    say_voice = "Fiona"
                subprocess.Popen(
                    ["say", "-v", say_voice, "-r", str(rate), clean_text],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except (FileNotFoundError, OSError):
                pass

    threading.Thread(target=_run, daemon=True).start()
    return True


def stop_speaking() -> bool:
    """Stop any ongoing speech."""
    try:
        subprocess.run(
            ["killall", "say"],
            capture_output=True, timeout=5,
        )
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def preview_voice(voice: str = DEFAULT_VOICE) -> bool:
    """Preview a voice by having it say a test phrase.

    Args:
        voice: Voice name to preview.

    Returns:
        True if preview played.
    """
    return speak(f"Hello, I am {voice}. Ready to help.", voice=voice)


# ─── Internal ────────────────────────────────────────────────────────────


# ─── Streaming TTS (speak sentences as they generate) ────────────────────

# A sentence ends on . ! ? (not a decimal like "3.5") followed by whitespace or
# end-of-buffer, or on a newline. Abbreviations may occasionally mis-split, which
# is acceptable for spoken output.
_SENTENCE_BOUNDARY = re.compile(r"(?<!\d)[.!?]+(?=\s|$)|\n+")


def _split_speakable(buffer: str) -> tuple[list[str], str]:
    """Split a growing text buffer into complete speakable sentences + remainder.

    Sentences are emitted as soon as a boundary is seen; the trailing partial
    sentence stays in the returned remainder until more text (or a final flush).
    """
    sentences: list[str] = []
    last = 0
    for match in _SENTENCE_BOUNDARY.finditer(buffer):
        end = match.end()
        piece = buffer[last:end].strip()
        if piece:
            sentences.append(piece)
        last = end
    return sentences, buffer[last:]


def _play_wav_bytes(wav: bytes, *, timeout_hint_chars: int = 0) -> bool:
    """Write WAV bytes to a temp file and play it via afplay, blocking."""
    tmp = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp = f.name
            f.write(wav)
        subprocess.run(["afplay", tmp], check=False, timeout=max(30, timeout_hint_chars // 5))
        return True
    except Exception:
        return False
    finally:
        if tmp:
            Path(tmp).unlink(missing_ok=True)


def _pipelined_speak_worker(sentence_q: "queue.Queue", *, voice: str, speed: float) -> None:
    """Consume the sentence queue, synthesising the *next* sentence on a
    background thread while the *current* one plays.

    Without this, each sentence's TTS synthesis (multi-second on the default
    ONNX path) only starts after the previous sentence has finished playing —
    a real, audible dead-air gap between every sentence, most noticeable right
    where KENN's spoken answers chain short clauses (e.g. "...eighty hertz."
    <gap> "Then, cut two point five kilohertz..."). Prefetching the next
    sentence's audio during current playback closes that gap to ~0 once the
    pipeline is warm.
    """
    next_text = sentence_q.get()
    next_wav = synthesise_isolated(next_text, voice=voice, speed=speed) if next_text else None

    while next_text is not None:
        wav, text = next_wav, next_text
        item = sentence_q.get()
        synth_result: dict[str, bytes | None] = {}
        synth_thread = None
        if item is not None:
            def _bg(t: str = item) -> None:
                try:
                    synth_result["wav"] = synthesise_isolated(t, voice=voice, speed=speed)
                except Exception:
                    synth_result["wav"] = None

            synth_thread = threading.Thread(target=_bg, daemon=True)
            synth_thread.start()

        if wav:
            try:
                _play_wav_bytes(wav, timeout_hint_chars=len(text))
            except Exception:
                pass

        if synth_thread is not None:
            synth_thread.join()
            next_wav, next_text = synth_result.get("wav"), item
        else:
            next_wav, next_text = None, None


def speak_streaming(chunks, *, kenn: bool = False, speak_fn=None) -> str:
    """Speak sentences as they arrive from a text-chunk iterator.

    Instead of waiting for the whole answer (6-8 s of LLM generation) before any
    audio plays, this buffers streamed chunks into sentences and speaks each the
    moment it completes — so the first words are heard ~1-2 s in. A background
    worker plays sentences in order while the generator keeps producing. Returns
    the full accumulated text.

    ``speak_fn(text, block)`` lets tests inject a sink; it defaults to Kokoro
    playback (KENN's male voice when ``kenn=True``). When no ``speak_fn`` is
    injected (the real, production path), sentence-to-sentence playback is
    pipelined — see ``_pipelined_speak_worker`` — to close the dead-air gap
    between sentences. An injected ``speak_fn`` combines synth+play into one
    call it doesn't expose separately, so the injected path stays the simpler
    sequential form tests rely on.
    """
    use_default_pipeline = speak_fn is None
    if speak_fn is None:
        speak_fn = speak_as_kenn if kenn else _kokoro_speak

    sentence_q: queue.Queue = queue.Queue()

    if use_default_pipeline:
        voice = KENN_VOICE if kenn else KOKORO_VOICE
        speed = KENN_SPEED if kenn else KOKORO_SPEED

        def _worker() -> None:
            _pipelined_speak_worker(sentence_q, voice=voice, speed=speed)
    else:
        def _worker() -> None:
            while True:
                item = sentence_q.get()
                if item is None:
                    break
                try:
                    speak_fn(item, block=True)  # synth + play, in order
                except Exception:
                    pass

    worker = threading.Thread(target=_worker, daemon=True)
    worker.start()

    collected: list[str] = []
    buffer = ""
    try:
        for chunk in chunks:
            if not chunk:
                continue
            collected.append(chunk)
            buffer += chunk
            sentences, buffer = _split_speakable(buffer)
            for sentence in sentences:
                spoken = _sanitize_for_speech(sentence)
                if spoken.strip():
                    sentence_q.put(spoken)
        tail = _sanitize_for_speech(buffer)
        if tail.strip():
            sentence_q.put(tail)
    finally:
        sentence_q.put(None)
        worker.join()
    return "".join(collected)


def extract_for_voice(text: str) -> str:
    """Extract the speakable portion from a structured KENN answer.

    Pulls Short answer + first 2 Try this steps, discards Sources/You could also ask.
    Falls back to the full text if no structure is found.
    """
    import re

    # Find Short answer section
    short_match = re.search(r"short answer\s*:(.+?)(?=try this\s*:|why it matters\s*:|sources\s*:|you could also ask\s*:|$)", text, re.IGNORECASE | re.DOTALL)
    try_match = re.search(r"try this\s*:(.+?)(?=why it matters\s*:|sources\s*:|you could also ask\s*:|$)", text, re.IGNORECASE | re.DOTALL)

    parts = []
    if short_match:
        parts.append(short_match.group(1).strip())
    if try_match:
        # Extract only first 2 numbered steps
        steps = re.findall(r"\d+\.\s+(.+?)(?=\d+\.|$)", try_match.group(1), re.DOTALL)
        if steps:
            parts.append("To fix it: " + " Then, ".join(s.strip() for s in steps[:2]))

    if parts:
        return " ".join(parts)

    # No structure found \u2014 return as-is for sanitization
    return text


def _sanitize_for_speech(text: str) -> str:
    """Clean text for speech output.

    Removes markdown formatting, emoji, URLs, and other non-speech elements.
    """
    import re

    # Protect <break time="..."/> tags from every filter below -- most
    # obviously the length-truncation cut near the end, which could
    # otherwise slice a tag in half and leave Kokoro trying to pronounce a
    # garbled fragment like "less than break time equals 5" out loud. Each
    # tag is swapped for a short, whitespace-free placeholder (safe against
    # the "collapse whitespace" pass too) and restored once every filter has
    # run. This function is called twice for the isolated-worker path
    # (synthesise_isolated() sanitises once before sending text to the
    # subprocess, then the worker's own synthesise() call sanitises again)
    # -- protect/restore is idempotent, so that's safe.
    protected_breaks: list[str] = []

    def _protect_break(match: re.Match) -> str:
        protected_breaks.append(match.group(0))
        return f"\x00BREAK{len(protected_breaks) - 1}\x00"

    text = _BREAK_TAG_RE.sub(_protect_break, text)

    # Found 2026-07-27 (Jack live-testing, "what's written doesn't match
    # what's said"): the dashboard's non-KENN streaming path (hub.html ->
    # ask_stream's else-branch) sends the whole formatted answer as a
    # single "token" event, including formatter.py's appended UI-only
    # trailers ("**Try next:** X | Y | Z", "*Suggestion:* ...") -- these
    # were never in the label-stripping list below (that list only covers
    # KENN's own structured-answer section headers), so they were read
    # aloud verbatim as an extra, nonsensical clause tacked onto every
    # spoken answer. Strip both trailers (and anything after them) before
    # any other cleanup, since they're always appended last.
    text = re.sub(r"\n+\*\*Try next:\*\*.*", "", text, flags=re.DOTALL)
    text = re.sub(r"\n+\*Suggestion:\*.*", "", text, flags=re.DOTALL)

    # Remove brackets/parenthetical technical metadata
    text = re.sub(r"\[.*?\]", "", text)

    # Remove markdown formatting
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)  # Bold
    text = re.sub(r"\*(.*?)\*", r"\1", text)       # Italic
    text = re.sub(r"`.*?`", "", text)               # Inline code
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)  # Code blocks

    # Remove markdown tables
    text = re.sub(r"^\s*\|.*\|", "", text, flags=re.MULTILINE)

    # Remove URLs
    text = re.sub(r"https?://\S+", "", text)

    # Remove emoji
    text = re.sub(r'[\U0001F300-\U0001F9FF\U0001F600-\U0001F64F\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\u2600-\u26FF\u2700-\u27BF]', '', text)

    # Remove markdown headers and section labels
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^(Short answer|Try this|Why it matters|Sources|You could also ask)\s*:?\s*", "", text, flags=re.MULTILINE | re.IGNORECASE)

    # Replace ASCII art/separators
    text = re.sub(r"={3,}", ". ", text)
    text = re.sub(r"-{3,}", ". ", text)

    # Remove bullet markers
    text = re.sub(r"^\s*[-*]\s+", "", text, flags=re.MULTILINE)

    # Add commas after conversational opening phrases if not already present
    text = re.sub(r"^(Got it|Alright|Okay|Sure)(?!\b\s*[,.!?])\b", r"\1,", text, flags=re.IGNORECASE)

    # Standardize ellipsis pauses
    text = re.sub(r"\.{2,}", "...", text)

    # Remove extra whitespace
    text = re.sub(r"\s+", " ", text).strip()

    # Limit length for speech. Placeholders are short (~10 chars) but not
    # zero-width, so a naive text[:497] cut can still land inside one --
    # extend the cut point past the whole placeholder rather than split it
    # (a small overshoot past the soft 500-char budget is preferable to
    # either a corrupt \x00BREAK fragment or silently dropping the pause).
    if len(text) > 500:
        cut = 497
        for placeholder_match in re.finditer(r"\x00BREAK\d+\x00", text):
            if placeholder_match.start() < cut < placeholder_match.end():
                cut = placeholder_match.end()
                break
        text = text[:cut] + "..."

    # Restore protected <break time="..."/> tags, now that no filter above
    # can still slice through one.
    for i, tag in enumerate(protected_breaks):
        text = text.replace(f"\x00BREAK{i}\x00", tag)

    return text
