"""Real-model benchmark proving parallel-chunk TTS synthesis actually reduces
wall time (docs/audits/2026-07-19-tts-latency-optimization.md).

Unlike tests/test_tts_parallel_chunks.py (fast, fake-Kokoro logic tests),
this loads the real Kokoro ONNX model and times both the current sequential
path and the opt-in parallel-chunk path on the same text.

Runs in an explicit native-arm64 subprocess (via
voice_output._tts_worker_python_command(), the same dispatch production
already uses) regardless of what interpreter invokes pytest -- direct
in-process Kokoro loading under this repo's main x86_64/Rosetta .venv
measured ~3x slower (6.0s vs 2.1s for the same call), which would make this
benchmark non-representative of the real synthesis path production and
tts_worker.py actually use.

Marked slow: loads a real ONNX model and does real inference, same reasoning
as tests/test_release_health_latency.py.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.slow

_BENCHMARK_SNIPPET = """
import json, sys, time
sys.path.insert(0, {root!r})
from thursday import voice_output as vo

kokoro = vo._load_kokoro()
if kokoro is None:
    print(json.dumps({{"error": "kokoro unavailable"}}))
    sys.exit(0)

text = "Cut two point five kilohertz, to reduce harshness, and boost the low end."
chunks = vo._split_into_synthesis_chunks(text)

# Warm up (first call after session creation has extra one-time cost).
kokoro.create("warm up sentence.", voice="af_heart", speed=1.1, lang="en-us")

t0 = time.time()
seq_samples, seq_sr = kokoro.create(text, voice="af_heart", speed=1.1, lang="en-us")
sequential_s = time.time() - t0

t0 = time.time()
result = vo._synthesise_chunks_parallel(kokoro, chunks, voice="af_heart", speed=1.1)
parallel_s = time.time() - t0

print(json.dumps({{
    "num_chunks": len(chunks),
    "sequential_s": sequential_s,
    "parallel_s": parallel_s,
    "sequential_duration_s": len(seq_samples) / seq_sr,
    "parallel_duration_s": (len(result[0]) / result[1]) if result else None,
    "parallel_ok": result is not None,
}}))
"""


def _run_native_benchmark() -> dict:
    from thursday.voice_output import _tts_worker_python_command

    command = list(_tts_worker_python_command())
    env = os.environ.copy()
    env["AUDIO_TOO_TTS_WORKER"] = "1"  # matches production's isolated-worker env marker
    snippet = _BENCHMARK_SNIPPET.format(root=str(ROOT))
    completed = subprocess.run(
        [*command, "-c", snippet],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(ROOT),
        env=env,
    )
    assert completed.returncode == 0, (
        f"benchmark subprocess failed (rc={completed.returncode}):\n"
        f"stdout={completed.stdout}\nstderr={completed.stderr}"
    )
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_parallel_chunk_synthesis_is_meaningfully_faster_on_real_model():
    result = _run_native_benchmark()
    if result.get("error") == "kokoro unavailable":
        pytest.skip("Kokoro model not available in this environment")

    assert result["num_chunks"] > 1, "test sentence should have split into multiple chunks"
    assert result["parallel_ok"] is True

    sequential_s = result["sequential_s"]
    parallel_s = result["parallel_s"]
    # Measured ~35% faster (1.38s vs 2.07s) during investigation; assert a
    # conservative 15% margin so normal run-to-run jitter doesn't flake this.
    assert parallel_s < sequential_s * 0.85, (
        f"parallel synthesis ({parallel_s:.3f}s) was not meaningfully faster than "
        f"sequential ({sequential_s:.3f}s) -- expected at least a 15% reduction"
    )

    # Sanity: parallel output isn't wildly shorter/longer than sequential
    # (the inserted inter-chunk silence gaps are small and fixed; this just
    # guards against dropped or duplicated audio, not exact duration parity).
    seq_dur = result["sequential_duration_s"]
    par_dur = result["parallel_duration_s"]
    assert par_dur is not None
    assert 0.5 * seq_dur < par_dur < 1.5 * seq_dur, (
        f"parallel output duration ({par_dur:.2f}s) implausible vs. "
        f"sequential ({seq_dur:.2f}s)"
    )
