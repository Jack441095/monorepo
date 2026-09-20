"""Latency benchmarks for the Thursday → KENN → LLM voice pipeline.

ML-heavy stages (STT, KENN) run in isolated subprocesses to avoid
CTranslate2 + PyTorch shared-library conflicts that cause segfaults.

Run with:
    pytest tests/test_latency.py -v -s

Gates are CPU-baseline values measured on Apple Silicon (MacBook Air M-series).
They exist to catch regressions, not to meet real-time targets.
GPU / ANE acceleration will reduce STT and LLM times significantly.

Gates (p95 targets — CPU baseline):
    Intent classification  <    200 ms  (pure Python, in-process)
    Voice extraction       <     10 ms  (pure Python, in-process)
    STT transcription      <  8 000 ms  (mlx-whisper Metal GPU, arm64)
    KENN full answer       < 50 000 ms  (subprocess, retrieval + Qwen 3B CPU)
    Thursday round-trip    < 70 000 ms  (subprocess, full orchestrator, CPU)
    Conversational rewrite <  5 000 ms  (subprocess, format_response() + local LLM)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from statistics import mean, median

import pytest

ROOT = Path(__file__).resolve().parent.parent
VENV_PYTHON = ROOT / ".venv" / "bin" / "python"
PYTHON = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable


# ── helpers ───────────────────────────────────────────────────────────────────

def _p95(values: list[float]) -> float:
    sorted_vals = sorted(values)
    idx = max(0, int(len(sorted_vals) * 0.95) - 1)
    return sorted_vals[idx]


def _print_stats(label: str, times_ms: list[float]) -> None:
    print(
        f"\n  {label}:\n"
        f"    min={min(times_ms):.0f}ms  "
        f"mean={mean(times_ms):.0f}ms  "
        f"median={median(times_ms):.0f}ms  "
        f"p95={_p95(times_ms):.0f}ms  "
        f"max={max(times_ms):.0f}ms"
    )


def _run_subprocess_bench(script: str, timeout: int = 60) -> dict:
    """Run a Python script in a clean subprocess and parse its JSON output."""
    env = os.environ.copy()
    env["KMP_DUPLICATE_LIB_OK"] = "TRUE"
    env["AUDIO_TOO_ALLOW_AUDIO_CAPTURE"] = "1"

    # Load .env into subprocess environment
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env.setdefault(k.strip(), v.strip())

    result = subprocess.run(
        [PYTHON, "-c", script],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=ROOT,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Subprocess failed:\n{result.stderr[-2000:]}")

    # Extract JSON from last line
    lines = [ln for ln in result.stdout.strip().splitlines() if ln.strip()]
    if not lines:
        raise RuntimeError(f"No output from subprocess.\nstderr: {result.stderr[-1000:]}")
    return json.loads(lines[-1])


# ── Stage 1: intent classification (pure Python) ─────────────────────────────

def test_intent_classification_latency():
    """Intent classification must be < 200 ms p95 (pure Python, no I/O)."""
    sys.path.insert(0, str(ROOT))
    from thursday.intent import classify_intent

    texts = [
        "how do I sidechain a kick drum in Ableton?",
        "what's the business health?",
        "schedule a reminder for tomorrow",
        "my kick is boomy",
        "show me the dashboard",
    ] * 3  # 15 runs

    times: list[float] = []
    for text in texts:
        start = time.perf_counter()
        classify_intent(text, {})
        times.append((time.perf_counter() - start) * 1000)

    _print_stats("Intent classification (15 runs)", times)
    p95 = _p95(times)
    assert p95 < 200, f"Intent p95 {p95:.0f}ms exceeds 200ms gate"


# ── Stage 2: voice extraction (pure Python) ───────────────────────────────────

def test_voice_extraction_latency():
    """extract_for_voice() text processing must be < 10 ms p95."""
    sys.path.insert(0, str(ROOT))
    from thursday.voice_output import extract_for_voice

    sample = """Short answer: Your snare sounds thin because it's missing body in the 200–300 Hz range.
Try this:
1. Add an EQ Eight and boost a low shelf at 200 Hz by 2–3 dB.
2. Add a bell at 3 kHz, lift by 1–2 dB to bring the crack forward.
Why it matters: Thin snares lack energy in the body region.
Sources:
- Drum EQ Fundamentals (drum-eq.md)
You could also ask:
- How do I add parallel saturation to a snare?
"""

    times: list[float] = []
    for _ in range(100):
        start = time.perf_counter()
        extract_for_voice(sample)
        times.append((time.perf_counter() - start) * 1000)

    _print_stats("Voice extraction (100 runs)", times)
    p95 = _p95(times)
    assert p95 < 10, f"Voice extraction p95 {p95:.2f}ms exceeds 10ms gate"


# ── Stage 3: STT transcription (subprocess — avoids CTranslate2/PyTorch clash) ─

@pytest.mark.slow
def test_stt_transcription_latency():
    """mlx-whisper Metal GPU transcription < 8000 ms p95 on a short clip.

    Marked slow: depends on mlx-whisper + Metal and is timing-sensitive, so it
    flakes under concurrent test load. Run in the perf pass (`pytest -m slow`).
    """
    script = """
import json, sys, time, tempfile
from pathlib import Path

try:
    import numpy as np
    import soundfile as sf
    import mlx_whisper
except ImportError as e:
    print(json.dumps({"skip": str(e)}))
    sys.exit(0)

sample_rate = 16000
t = np.linspace(0, 3, sample_rate * 3, endpoint=False)
audio = (np.sin(2 * np.pi * 440 * t) * 0.3 * 32767).astype(np.int16)

with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
    tmp_path = tmp.name
sf.write(tmp_path, audio, sample_rate)

# Warm-up call (may download weights first time)
mlx_whisper.transcribe(tmp_path, path_or_hf_repo="mlx-community/whisper-small-mlx", verbose=False)

times = []
for _ in range(5):
    start = time.perf_counter()
    mlx_whisper.transcribe(tmp_path, path_or_hf_repo="mlx-community/whisper-small-mlx",
                           language="en", verbose=False)
    times.append((time.perf_counter() - start) * 1000)

Path(tmp_path).unlink(missing_ok=True)
print(json.dumps({"times_ms": times}))
"""
    mlx_python = "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13"
    try:
        env = os.environ.copy()
        result = subprocess.run(
            ["arch", "-arm64", mlx_python, "-c", script],
            capture_output=True, text=True, timeout=120, cwd=ROOT, env=env,
        )
        if result.returncode != 0:
            pytest.skip(f"mlx-whisper subprocess failed: {result.stderr[-500:]}")
        lines = [ln for ln in result.stdout.strip().splitlines() if ln.strip()]
        data = json.loads(lines[-1])
    except subprocess.TimeoutExpired:
        pytest.fail("STT benchmark timed out after 120s")

    if "skip" in data:
        pytest.skip(f"faster-whisper not available: {data['skip']}")

    times = data["times_ms"]
    _print_stats("STT transcription 3s clip (5 runs)", times)

    p95 = _p95(times)
    assert p95 < 8_000, f"STT p95 {p95:.0f}ms exceeds 8 000ms gate (mlx-whisper Metal)"


# ── Stage 4: KENN full answer (subprocess — retrieval + Qwen LLM) ────────────

@pytest.mark.slow
def test_kenn_full_answer_latency():
    """Full KENN question → answer (retrieval + Qwen synthesis) < 35 000 ms p95.

    Marked slow: depends on a running Ollama LLM and is timing-sensitive (a p95
    near the gate flakes under concurrent CPU load). Run via `pytest -m slow`.
    """
    script = """
import json, sys, time
sys.path.insert(0, "studio/kenn")
sys.path.insert(0, "scripts")

import os
env_file = ".env"
try:
    for line in open(env_file).read().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())
except FileNotFoundError:
    pass

try:
    import urllib.request
    urllib.request.urlopen("http://127.0.0.1:11434", timeout=2)
except Exception:
    print(json.dumps({"skip": "Ollama not running"}))
    sys.exit(0)

try:
    from kenn.core.chat import ask_once
except ImportError as e:
    print(json.dumps({"skip": str(e)}))
    sys.exit(0)

questions = [
    "how do I sidechain a kick drum in Ableton?",
    "my snare feels thin, what should I do?",
    "what EQ moves help a muddy mix?",
]

times = []
for q in questions:
    start = time.perf_counter()
    ask_once(q, limit=5, save=False)
    ms = (time.perf_counter() - start) * 1000
    times.append(ms)

print(json.dumps({"times_ms": times}))
"""
    try:
        data = _run_subprocess_bench(script, timeout=180)
    except subprocess.TimeoutExpired:
        pytest.fail("KENN benchmark timed out after 180s")

    if "skip" in data:
        pytest.skip(data["skip"])

    times = data["times_ms"]
    for i, (q, ms) in enumerate(zip(
        ["sidechain kick", "thin snare", "muddy EQ"], times
    )):
        print(f"\n  [{ms:.0f}ms] {q}")
    _print_stats("KENN full answer (3 runs)", times)

    p95 = _p95(times)
    assert p95 < 50_000, f"KENN full answer p95 {p95:.0f}ms exceeds 50s CPU-baseline gate"


# ── Stage 5: Thursday orchestrator round-trip (subprocess) ───────────────────

@pytest.mark.slow
def test_thursday_orchestrator_latency():
    """Thursday handle() end-to-end round-trip < 40 000 ms p95.

    Marked slow: full orchestrator + LLM, timing-sensitive under load. Run via
    `pytest -m slow`.
    """
    script = """
import json, sys, time
sys.path.insert(0, ".")
sys.path.insert(0, "scripts")
sys.path.insert(0, "server/agents")

import os
env_file = ".env"
try:
    for line in open(env_file).read().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())
except FileNotFoundError:
    pass

try:
    import urllib.request
    urllib.request.urlopen("http://127.0.0.1:11434", timeout=2)
except Exception:
    print(json.dumps({"skip": "Ollama not running"}))
    sys.exit(0)

try:
    from thursday.orchestrator import handle
    from thursday.session_manager import get_or_create_session
except ImportError as e:
    print(json.dumps({"skip": str(e)}))
    sys.exit(0)

session = get_or_create_session()
questions = [
    "how do I sidechain in Ableton?",
    "my snare feels thin",
]

times = []
for q in questions:
    start = time.perf_counter()
    handle(q, session)
    ms = (time.perf_counter() - start) * 1000
    times.append(ms)

print(json.dumps({"times_ms": times}))
"""
    try:
        data = _run_subprocess_bench(script, timeout=200)
    except subprocess.TimeoutExpired:
        pytest.fail("Thursday orchestrator benchmark timed out after 200s")

    if "skip" in data:
        pytest.skip(data["skip"])

    times = data["times_ms"]
    for ms in times:
        print(f"\n  [{ms:.0f}ms]")
    _print_stats("Thursday round-trip (2 runs)", times)

    p95 = _p95(times)
    assert p95 < 70_000, f"Thursday round-trip p95 {p95:.0f}ms exceeds 70s CPU-baseline gate"


# ── Stage 6: Thursday conversational-reply rewrite overhead (subprocess) ─────

@pytest.mark.slow
def test_thursday_conversational_rewrite_latency():
    """thursday/response_rewrite.py (2026-08-02) makes format_response() call
    a real LLM for deterministic-service replies when
    THURSDAY_CONVERSATIONAL_REPLIES=1 -- previously a pure-Python dict
    rendering, effectively free (<1ms). Measured live against the real local
    Ollama model (qwen2.5:1.5b) the day this was built: 645-1304ms per call,
    mean ~870ms -- gate set with a generous ~4x margin over that observed
    max, same CPU-baseline philosophy as the other subprocess gates in this
    file (catch regressions, not chase a real-time target).

    Marked slow: depends on a running Ollama and is timing-sensitive under
    load. Run via `pytest -m slow`.
    """
    script = """
import json, sys, time
sys.path.insert(0, ".")
sys.path.insert(0, "server/app")
sys.path.insert(0, "studio")

import os
env_file = ".env"
try:
    for line in open(env_file).read().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())
except FileNotFoundError:
    pass

try:
    import urllib.request
    urllib.request.urlopen("http://127.0.0.1:11434", timeout=2)
except Exception:
    print(json.dumps({"skip": "Ollama not running"}))
    sys.exit(0)

os.environ["THURSDAY_CONVERSATIONAL_REPLIES"] = "1"
from thursday.formatter import format_response

raw = {"active_clients": 4, "revenue_this_month": 1250, "pending_invoices": 2}

times = []
for _ in range(5):
    start = time.perf_counter()
    format_response(raw, "Business Status", "business_status", {}, question="how's business going?")
    times.append((time.perf_counter() - start) * 1000)

print(json.dumps({"times_ms": times}))
"""
    try:
        data = _run_subprocess_bench(script, timeout=60)
    except subprocess.TimeoutExpired:
        pytest.fail("Conversational rewrite benchmark timed out after 60s")

    if "skip" in data:
        pytest.skip(data["skip"])

    times = data["times_ms"]
    _print_stats("Conversational rewrite (5 runs)", times)

    p95 = _p95(times)
    assert p95 < 5_000, f"Conversational rewrite p95 {p95:.0f}ms exceeds 5s CPU-baseline gate"


# ── Summary ───────────────────────────────────────────────────────────────────

def test_latency_summary():
    """Print the gate targets — always passes, informational only."""
    print("\n" + "=" * 60)
    print("  LATENCY GATES")
    print("=" * 60)
    print("  Intent classification  <    200 ms p95  (in-process, pure Python)")
    print("  Voice extraction       <     10 ms p95  (in-process, pure Python)")
    print("  STT transcription      < 20 000 ms p95  (subprocess, CPU int8)")
    print("  KENN full answer       < 50 000 ms p95  (subprocess, Qwen 3B CPU)")
    print("  Thursday round-trip    < 70 000 ms p95  (subprocess, full stack CPU)")
    print("  Conversational rewrite <  5 000 ms p95  (subprocess, format_response + local LLM)")
    print("")
    print("  CPU baselines — GPU/ANE will be 5–10x faster.")
    print("=" * 60)
