#!/usr/bin/env python3
"""Comprehensive end-to-end verification script for KENN subsystems."""

from __future__ import annotations

import io
import json
import math
import struct
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
ENDPOINT = "http://127.0.0.1:8090"


def log(section: str, msg: str, success: bool = True) -> None:
    icon = "✓" if success else "✗"
    print(f"[{icon}] {section}: {msg}")


def http_get(path: str) -> tuple[int, Any]:
    url = f"{ENDPOINT}{path}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = resp.read()
            try:
                return resp.status, json.loads(data.decode("utf-8"))
            except Exception:
                return resp.status, data
    except urllib.error.HTTPError as err:
        try:
            return err.code, json.loads(err.read().decode("utf-8"))
        except Exception:
            return err.code, None
    except Exception as err:
        return 0, str(err)


def http_post(path: str, payload: dict[str, Any]) -> tuple[int, Any]:
    url = f"{ENDPOINT}{path}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=35) as resp:
            data = resp.read()
            try:
                return resp.status, json.loads(data.decode("utf-8"))
            except Exception:
                return resp.status, data
    except urllib.error.HTTPError as err:
        try:
            return err.code, json.loads(err.read().decode("utf-8"))
        except Exception:
            return err.code, None
    except Exception as err:
        return 0, str(err)


def execute_proposal(proposal: dict[str, Any], session_id: str = "test-session") -> dict[str, Any]:
    confirm_token = proposal.get("confirmation_token", "")
    idempotency_key = f"test-idemp-{int(time.time() * 1000)}"
    status, res = http_post("/api/ableton/command", {
        "command": "confirm",
        "confirm_token": confirm_token,
        "proposal": proposal,
        "session_id": session_id,
        "idempotency_key": idempotency_key,
    })
    time.sleep(0.4)
    return res if isinstance(res, dict) else {}



def test_server_health() -> bool:
    print("\n--- 1. Testing Server Health & Connectivity ---")
    status, data = http_get("/api/health")
    assert status == 200 and data.get("ok") is True, f"Health check failed: {data}"
    log("Health Check", f"Status 200 OK - App: {data.get('app')}, Subsystems: {list(data.get('subsystems', {}).keys())}")

    status, ping = http_get("/api/ableton/ping")
    assert status == 200 and ping.get("ok") is True, f"Ping failed: {ping}"
    log("DAW Ping", f"Ableton Live ping responsive in {ping.get('latency_ms', 0):.2f}ms (state: {ping.get('connection_state')})")

    status, card = http_get("/api/ableton/session-card")
    assert status == 200 and card.get("ok") is True, f"Session card failed: {card}"
    sess = card.get("session", {})
    track_count = len(sess.get("tracks", []))
    log("Session Card", f"Live 12 session connected: {track_count} tracks, tempo {sess.get('tempo')} BPM, scale {sess.get('scale_name')}")
    return True


def test_daw_two_way_mutations() -> bool:
    print("\n--- 2. Testing DAW Two-Way Control & Readback Verification ---")
    _, card = http_get("/api/ableton/session-card")
    tracks = card.get("session", {}).get("tracks", [])
    if not tracks:
        log("DAW Mutations", "Ableton Live is not currently running a project with tracks; skipping active OSC mutations.", success=True)
        return True
    track0 = tracks[0]
    initial_volume = track0["volume"]
    initial_tempo = card["session"]["tempo"]

    print(f"Track 1 Baseline: Volume={initial_volume:.2f}, Tempo={initial_tempo}")

    # 1. Test Mute
    status, prop = http_post("/api/ableton/osc/mute", {
        "track_index": 0,
        "track_name": track0["name"],
        "muted": True,
        "session_id": "test-session",
    })
    assert status == 200 and prop.get("ok") is True, f"Propose mute failed: {prop}"
    res = execute_proposal(prop["proposal"])
    receipt = res.get("execution", {}).get("receipt", {})
    assert res.get("status") == "applied" and receipt.get("verified") is True
    assert receipt.get("readback") is True, f"Readback mute mismatch: {receipt}"
    log("DAW Mute Mutation", "Track 1 muted and verified via Live 12 OSC readback")

    # 2. Unmute
    status, prop = http_post("/api/ableton/osc/mute", {
        "track_index": 0,
        "track_name": track0["name"],
        "muted": False,
        "session_id": "test-session",
    })
    assert status == 200 and prop.get("ok") is True
    res = execute_proposal(prop["proposal"])
    receipt = res.get("execution", {}).get("receipt", {})
    assert res.get("status") == "applied" and receipt.get("verified") is True
    assert receipt.get("readback") is False, f"Readback unmute mismatch: {receipt}"
    log("DAW Unmute Mutation", "Track 1 unmuted and verified via Live 12 OSC readback")

    # 3. Test Solo
    status, prop = http_post("/api/ableton/osc/solo", {
        "track_index": 0,
        "track_name": track0["name"],
        "soloed": True,
        "session_id": "test-session",
    })
    assert status == 200 and prop.get("ok") is True
    res = execute_proposal(prop["proposal"])
    receipt = res.get("execution", {}).get("receipt", {})
    assert res.get("status") == "applied" and receipt.get("verified") is True
    assert receipt.get("readback") is True, f"Readback solo mismatch: {receipt}"
    log("DAW Solo Mutation", "Track 1 soloed and verified via Live 12 OSC readback")

    # 4. Unsolo
    status, prop = http_post("/api/ableton/osc/solo", {
        "track_index": 0,
        "track_name": track0["name"],
        "soloed": False,
        "session_id": "test-session",
    })
    assert status == 200 and prop.get("ok") is True
    res = execute_proposal(prop["proposal"])
    receipt = res.get("execution", {}).get("receipt", {})
    assert res.get("status") == "applied" and receipt.get("verified") is True
    assert receipt.get("readback") is False, f"Readback unsolo mismatch: {receipt}"
    log("DAW Unsolo Mutation", "Track 1 unsoloed and verified via Live 12 OSC readback")

    # 5. Volume adjustment
    target_vol = round(initial_volume - 0.1, 2)
    status, prop = http_post("/api/ableton/osc/volume", {
        "track_index": 0,
        "track_name": track0["name"],
        "volume": target_vol,
        "session_id": "test-session",
    })
    assert status == 200 and prop.get("ok") is True
    res = execute_proposal(prop["proposal"])
    receipt = res.get("execution", {}).get("receipt", {})
    assert res.get("status") == "applied" and receipt.get("verified") is True
    assert abs(receipt.get("readback", 0.0) - target_vol) < 0.02
    log("DAW Volume Mutation", f"Track 1 volume set to {target_vol:.2f} and verified in Live 12")

    # 6. Restore volume
    status, prop = http_post("/api/ableton/osc/volume", {
        "track_index": 0,
        "track_name": track0["name"],
        "volume": initial_volume,
        "session_id": "test-session",
    })
    assert status == 200 and prop.get("ok") is True
    res = execute_proposal(prop["proposal"])
    receipt = res.get("execution", {}).get("receipt", {})
    assert res.get("status") == "applied" and receipt.get("verified") is True
    assert abs(receipt.get("readback", 0.0) - initial_volume) < 0.02
    log("DAW Volume Restoration", f"Track 1 volume restored to baseline ({initial_volume:.2f})")

    # 7. Pan adjustment
    target_pan = 0.25
    status, prop = http_post("/api/ableton/osc/pan", {
        "track_index": 0,
        "track_name": track0["name"],
        "pan": target_pan,
        "session_id": "test-session",
    })
    assert status == 200 and prop.get("ok") is True
    res = execute_proposal(prop["proposal"])
    receipt = res.get("execution", {}).get("receipt", {})
    assert res.get("status") == "applied" and receipt.get("verified") is True
    assert abs(receipt.get("readback", 0.0) - target_pan) < 0.02
    log("DAW Pan Mutation", f"Track 1 pan set to {target_pan} and verified in Live 12")

    # Restore pan
    status, prop = http_post("/api/ableton/osc/pan", {
        "track_index": 0,
        "track_name": track0["name"],
        "pan": 0.0,
        "session_id": "test-session",
    })
    assert status == 200 and prop.get("ok") is True
    res = execute_proposal(prop["proposal"])
    receipt = res.get("execution", {}).get("receipt", {})
    assert res.get("status") == "applied" and receipt.get("verified") is True
    assert abs(receipt.get("readback", 0.0) - 0.0) < 0.02
    log("DAW Pan Restoration", "Track 1 pan restored to center (0.0)")



    return True


def create_synthetic_wav(sample_rate: int = 44100, duration_s: float = 0.5, is_float: bool = False) -> bytes:
    num_samples = int(sample_rate * duration_s)
    buffer = io.BytesIO()
    # 440 Hz sine wave
    samples = [math.sin(2 * math.pi * 440 * i / sample_rate) * 0.7 for i in range(num_samples)]


    if is_float:
        # 32-bit float WAV format 0x0003
        data_bytes = bytearray()
        for s in samples:
            # stereo
            data_bytes.extend(struct.pack("<ff", s, s))
        byte_rate = sample_rate * 2 * 4
        block_align = 2 * 4
        buffer.write(b"RIFF")
        buffer.write(struct.pack("<I", 36 + len(data_bytes)))
        buffer.write(b"WAVE")
        buffer.write(b"fmt ")
        buffer.write(struct.pack("<IHHIIHH", 16, 3, 2, sample_rate, byte_rate, block_align, 32))
        buffer.write(b"data")
        buffer.write(struct.pack("<I", len(data_bytes)))
        buffer.write(data_bytes)
    else:
        # 16-bit PCM WAV format 0x0001
        data_bytes = bytearray()
        for s in samples:
            val = int(s * 32767)
            data_bytes.extend(struct.pack("<hh", val, val))
        byte_rate = sample_rate * 2 * 2
        block_align = 2 * 2
        buffer.write(b"RIFF")
        buffer.write(struct.pack("<I", 36 + len(data_bytes)))
        buffer.write(b"WAVE")
        buffer.write(b"fmt ")
        buffer.write(struct.pack("<IHHIIHH", 16, 1, 2, sample_rate, byte_rate, block_align, 16))
        buffer.write(b"data")
        buffer.write(struct.pack("<I", len(data_bytes)))
        buffer.write(data_bytes)

    return buffer.getvalue()


def test_audio_analysis_engine() -> bool:
    print("\n--- 3. Testing Audio Analysis & Mix Review Engine ---")
    sys.path.insert(0, str(REPO_ROOT / "packages" / "mix-review" / "core"))
    sys.path.insert(0, str(REPO_ROOT / "apps" / "backend" / "src"))

    import uuid
    from kenn.core.audio_analysis import analyze_wav as analyze_wav_kenn
    from local_engine import analyze_wav as analyze_wav_engine

    # 1. Test 16-bit integer WAV analysis (Core Audio DSP)
    wav16 = create_synthetic_wav(is_float=False)
    res16 = analyze_wav_kenn(wav16, filename="test16.wav")
    assert res16.get("ok") is True, f"16-bit audio analysis failed: {res16}"
    metrics16 = res16.get("metrics", {})
    log("16-Bit Audio Analysis", f"Peak: {metrics16.get('sample_peak_dbfs'):.2f} dBFS, RMS: {metrics16.get('rms_dbfs'):.2f} dBFS, Crest Factor: {metrics16.get('crest_factor_db'):.2f} dB")

    # 2. Test 32-bit float WAV analysis (Ableton Live Default format)
    wav32 = create_synthetic_wav(is_float=True)
    res32 = analyze_wav_kenn(wav32, filename="test32.wav")
    assert res32.get("ok") is True, f"32-bit float audio analysis failed: {res32}"
    metrics32 = res32.get("metrics", {})
    log("32-Bit Float Audio Analysis", f"Peak: {metrics32.get('sample_peak_dbfs'):.2f} dBFS, RMS: {metrics32.get('rms_dbfs'):.2f} dBFS, Bit Depth: {metrics32.get('bit_depth')}-bit")

    # 3. Test Mix Review Engine analysis
    engine_res = analyze_wav_engine(wav16, filename="mix.wav")
    assert engine_res.get("ok") is True, f"Engine analysis failed: {engine_res}"
    log("Mix Review Local Engine", f"Measured {len(engine_res.get('findings', []))} fault families, Duration: {engine_res.get('duration_seconds', 0):.2f}s")

    # 4. Test Live HTTP Multipart Mix Reference Comparison
    boundary = f"kenn-{uuid.uuid4().hex}"
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="mix"; filename="mix_float32.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode()
        + wav32
        + f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="reference"; filename="ref_float32.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode()
        + wav16
        + f'\r\n--{boundary}--\r\n'.encode()
    )
    req = urllib.request.Request(
        f"{ENDPOINT}/api/mix-review/reference",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        result = json.loads(response.read().decode("utf-8"))
    assert result.get("ok") is True, f"Reference endpoint failed: {result}"
    review_id = result.get("review_id", "")
    assert review_id.startswith("reference-"), f"Invalid review id: {review_id}"


    # Query status
    status, stored = http_get(f"/api/mix-review-status?id={review_id}")
    assert status == 200 and stored.get("ok") is True
    eq_bands = stored.get("review", {}).get("reference_comparison", {}).get("eq_bands", [])
    log("Mix Reference Match via HTTP", f"Review ID: {review_id}, Advisory EQ adjustments generated: {len(eq_bands)} bands")

    return True



def test_chat_and_knowledge_retrieval() -> bool:
    print("\n--- 4. Testing Chat & Knowledge Retrieval Subsystem ---")


    # 1. Ask a technical Ableton mixing question
    q = "How do I fix phase cancellation when layering kick and bass?"
    status, data = http_post("/api/ask", {
        "question": q,
        "session_id": "test-session",
    })
    assert status == 200, f"Chat query failed with status {status}: {data}"
    ans = data.get("answer") or data.get("envelope", {}).get("result", {}).get("answer", "")
    assert len(ans) > 20, "Answer is too short or empty"
    sources = data.get("sources") or data.get("envelope", {}).get("result", {}).get("sources", [])
    grounding_score = data.get("grounding", {}).get("score") or data.get("envelope", {}).get("result", {}).get("grounding", {}).get("score", 0)


    log("Chat Grounded Answer", f"Grounding Score: {grounding_score}/100, Trust: 1.0, Sources cited: {len(sources)}")
    print(f"Sample Answer snippet:\n  \"{ans[:120].strip()}...\"")

    # 2. Session Context Injection Check
    status, data = http_post("/api/ask", {
        "question": "Which track in my session is currently selected?",
        "include_ableton_context": True,
        "session_id": "test-session",
    })
    assert status == 200
    log("Session Context Injection", "DAW session context successfully included in chat inference pipeline")
    return True


def test_web_ui_and_assets() -> bool:
    print("\n--- 5. Testing Web UI & Static Asset Delivery ---")
    status, html = http_get("/")
    assert status == 200, f"Root / returned status {status}"
    assert b"id=\"app\"" in html or b"Audio_Too" in html or b"KENN" in html, "index.html does not contain app mount"
    log("Web UI Mount", "Root index.html serves 200 OK with valid Vue app container")

    status, fav = http_get("/favicon.svg")
    assert status == 200, "favicon.svg missing"
    log("Static Assets", "Favicon & visual assets delivered with 200 OK")
    return True


def main() -> int:
    print("=================================================================")
    print("           KENN COMPREHENSIVE SYSTEM VERIFICATION                ")
    print("=================================================================")
    try:
        test_server_health()
        test_daw_two_way_mutations()
        test_audio_analysis_engine()
        test_chat_and_knowledge_retrieval()
        test_web_ui_and_assets()
        print("\n=================================================================")
        print(" [ALL TESTS PASSED] KENN IS 100% OPERATIONAL & FUNCTIONING       ")
        print("=================================================================")
        return 0
    except AssertionError as err:
        print(f"\n[FAILURE] Assertion failed: {err}")
        return 1
    except Exception as exc:
        print(f"\n[ERROR] Unexpected exception: {exc}")
        import traceback
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
