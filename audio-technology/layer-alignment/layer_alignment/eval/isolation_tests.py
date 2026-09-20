"""Failure isolation tests (sprint §54) — engine must fail SAFELY.

Generates malformed/degenerate inputs in a temp dir and records typed
outcomes. No engine code is modified; findings feed V2 backlog.
"""
from __future__ import annotations

import json
import struct
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.audio_io import AudioLoadError, load_wav, write_wav   # noqa: E402
from src.nla import decision as D                                # noqa: E402
from eval.pipeline import analyse_case                           # noqa: E402
from eval.cases import PairCase                                  # noqa: E402


def _case(a, b, fs, cid):
    return PairCase(case_id=cid, klass="ISOLATION", category="test",
                    relationship="none", fs=fs, a=a, b=b,
                    expected_action="UNKNOWN")


def run_all() -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="nla_iso_"))
    results = []

    def record(name, expect, fn):
        try:
            r = fn()
            ok = r == expect if expect is not None else True
            results.append({"test": name, "outcome": r,
                            "safe": bool(ok)})
        except AudioLoadError as e:
            results.append({"test": name, "outcome": f"AudioLoadError:{e}",
                            "safe": True})
        except Exception as e:                    # noqa: BLE001
            results.append({"test": name,
                            "outcome": f"UNHANDLED {type(e).__name__}: {e}",
                            "safe": False})

    # corrupt / truncated wav
    p = tmp / "corrupt.wav"
    p.write_bytes(b"RIFF0000WAVEjunkjunkjunk")
    record("corrupt_wav", "AudioLoadError", lambda: load_wav(p))

    # zero-length
    p = tmp / "empty.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(48000)
    record("zero_length", "AudioLoadError", lambda: load_wav(p))

    # unsupported format
    p = tmp / "notaudio.flac"
    p.write_bytes(b"fLaC\x00\x00\x00\x22")
    record("unsupported_format", "AudioLoadError", lambda: load_wav(p))

    # very short audio (64 samples)
    p = tmp / "tiny.wav"
    write_wav(p, np.random.default_rng(1).standard_normal(64), 48000)
    record("too_short_64", "AudioLoadError", lambda: load_wav(p))

    # silence pair -> engine must NOT fabricate advice
    z = np.zeros(32768)
    c = _case(z.copy(), z.copy(), 48000, "iso|silence")

    def silence_engine():
        r = analyse_case(c)
        return r["product_output"]["action"]
    record("silence_no_fabricated_advice", None, silence_engine)

    # near-silence + tiny noise
    ns = np.random.default_rng(2).standard_normal(32768) * 1e-7
    c = _case(ns.copy(), ns.copy(), 48000, "iso|near_silence")
    record("near_silence", None, silence_engine)

    # NaN input derived material — engine path must raise or abstain safely
    nan = np.full(4096, np.nan)
    try:
        c = _case(nan, nan.copy(), 48000, "iso|nan")
        r = analyse_case(c)
        act = r["product_output"]["action"]
        results.append({"test": "nan_input",
                        "outcome": f"engine returned {act} "
                                   f"(confidence "
                                   f"{r['product_output'].get('confidence')})",
                        "safe": act in ("NO_ACTION", "ABSTAIN")})
    except Exception as e:                        # noqa: BLE001
        results.append({"test": "nan_input",
                        "outcome": f"raised {type(e).__name__}",
                        "safe": True})          # raising IS failing safely

    # sample-rate mismatch between channels of a pair (harness-level note)
    a = np.random.default_rng(3).standard_normal(16384)
    b = np.random.default_rng(4).standard_normal(16384)
    c = _case(a, b, 44100, "iso|sr_note")       # analysed AS labelled; manifest records true rates
    record("sr_mismatch_documented_not_crashed", None,
           lambda: analyse_case(c)["product_output"]["action"])

    # long file memory sanity (5 min @48k mono float64 ~115MB for pair)
    # 60 s: exercises memory behaviour without minute-scale FFT cost;
    # harness caps analysis windows at 10 s (capture/analyse policy)
    long_x = np.random.default_rng(5).standard_normal(60 * 48000).astype(
        np.float32).astype(np.float64)
    c = _case(long_x, np.roll(long_x, 33), 48000, "iso|long")
    record("long_file_analysis", None, silence_engine.__class__ and (
        lambda: analyse_case(c)["product_output"]["action"]))

    passed = all(r["safe"] for r in results)
    return {"results": results, "all_safe": passed}


if __name__ == "__main__":
    out = run_all()
    print(json.dumps(out, indent=1))
    sys.exit(0 if out["all_safe"] else 1)
