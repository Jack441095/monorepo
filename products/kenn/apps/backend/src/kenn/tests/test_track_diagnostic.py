"""Tests for track diagnostic scanner engine.

Verifies ALS session track extraction, audio envelope generation,
2D spectrogram matrix computation, and acoustic weak area detection.
"""

from __future__ import annotations

import io
import math
import struct
import wave
import pytest

from kenn.core.track_diagnostic import (
    analyze_track_diagnostic,
    compute_spectrogram_matrix,
    compute_waveform_envelope,
    detect_weak_areas,
    extract_session_tracks,
)


def _make_synth_wav(
    freqs: list[float],
    duration: float = 0.5,
    sample_rate: int = 44100,
    amplitude: float = 0.5,
) -> bytes:
    """Generate in-memory mono 16-bit PCM WAV with harmonic components."""
    total_frames = int(duration * sample_rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        frames = []
        for i in range(total_frames):
            t = i / sample_rate
            sample_val = sum(math.sin(2.0 * math.pi * f * t) for f in freqs) / len(freqs)
            val_int = int(max(-1.0, min(1.0, sample_val * amplitude)) * 32767.0)
            frames.append(struct.pack("<h", val_int))
        wf.writeframes(b"".join(frames))
    return buf.getvalue()


def test_compute_waveform_envelope():
    samples = [0.1 * math.sin(i * 0.1) for i in range(1000)]
    peaks, rms_list = compute_waveform_envelope(samples, points=50)
    assert len(peaks) == 50
    assert len(rms_list) == 50
    assert max(peaks) > 0.05
    assert all(0.0 <= p <= 1.0 for p in peaks)


def test_compute_spectrogram_matrix():
    samples = [0.5 * math.sin(2.0 * math.pi * 440.0 * i / 44100.0) for i in range(4410)]
    matrix = compute_spectrogram_matrix(samples, 44100, time_slices=16)
    assert len(matrix) == 16
    assert len(matrix[0]) == 31  # 31 standard frequency bands
    # 440 Hz should have higher energy than 20 Hz
    assert matrix[8][12] > matrix[8][0]  # band 12 is near 400 Hz


def test_detect_weak_areas_sub_rumble():
    # Synthetic spectrogram with huge 20 Hz sub energy and low mid energy
    fake_spectrogram = [[-80.0] * 31 for _ in range(10)]
    for row in fake_spectrogram:
        row[0] = -12.0  # 20 Hz rumble
        row[1] = -14.0  # 25 Hz rumble
        row[5] = -35.0  # 63 Hz bass
        row[15] = -40.0  # 630 Hz mid

    weak_areas = detect_weak_areas(
        samples=[0.1] * 100,
        sample_rate=44100,
        peak_dbfs=-3.0,
        rms_dbfs=-15.0,
        spectrogram=fake_spectrogram,
        track_name="Kick",
        track_index=1,
    )

    types = [w["type"] for w in weak_areas]
    assert "sub_rumble" in types
    sub_remedy = next(w for w in weak_areas if w["type"] == "sub_rumble")
    assert sub_remedy["remedy"]["device_name"] == "EQ Eight"
    assert sub_remedy["remedy"]["parameter_value"] == 32.0


def test_analyze_track_diagnostic_full_pipeline():
    wav_bytes = _make_synth_wav([280.0], duration=0.4, amplitude=0.7)  # 280 Hz mud tone
    res = analyze_track_diagnostic(
        payload=wav_bytes,
        filename="synth_mud.wav",
        track_info={"track_name": "Bass", "track_index": 2},
    )

    assert res["ok"] is True
    assert res["track_name"] == "Bass"
    assert res["track_index"] == 2
    assert "waveform" in res
    assert len(res["waveform"]["peaks"]) == 300
    assert "spectrogram" in res
    assert len(res["spectrogram"]["matrix"]) == 64
    assert res["metrics"]["sample_rate_hz"] == 44100


def test_extract_session_tracks_handles_missing_file():
    tracks = extract_session_tracks("/non/existent/path.als")
    assert tracks == []


def test_handle_track_diagnostic_scan_json(tmp_path):
    import json
    from kenn.routes.audio_handler import handle_track_diagnostic_scan

    wav_path = tmp_path / "test_kick.wav"
    wav_bytes = _make_synth_wav([50.0], duration=0.3)
    wav_path.write_bytes(wav_bytes)

    payload = json.dumps({
        "file_path": str(wav_path),
        "track_name": "Kick",
        "track_index": 1,
    }).encode("utf-8")

    class FakeHandler:
        headers = {
            "Content-Type": "application/json",
            "Content-Length": str(len(payload)),
        }
        rfile = io.BytesIO(payload)
        sent = None

        def send_json(self, status, data):
            self.sent = (status, data)

    h = FakeHandler()
    handle_track_diagnostic_scan(h)
    assert h.sent is not None
    status, data = h.sent
    assert status == 200
    assert data["ok"] is True
    assert data["track_name"] == "Kick"
    assert "spectrogram" in data


def test_handle_track_diagnostic_apply():
    import json
    from kenn.routes.audio_handler import handle_track_diagnostic_apply

    payload = json.dumps({
        "remedy": {
            "action": "insert_device_with_parameter",
            "device_name": "EQ Eight",
            "track_index": 1,
            "track_name": "Kick",
            "parameter_name": "1 Frequency A",
            "parameter_value": 32.0,
        }
    }).encode("utf-8")

    class FakeHandler:
        headers = {
            "Content-Type": "application/json",
            "Content-Length": str(len(payload)),
        }
        rfile = io.BytesIO(payload)
        sent = None

        def send_json(self, status, data):
            self.sent = (status, data)

    h = FakeHandler()
    handle_track_diagnostic_apply(h)
    assert h.sent is not None
    status, data = h.sent
    assert status == 200
    assert data["ok"] is True
    assert data["applied"] is True


def test_build_tracks_from_live_session():
    from kenn.core.track_diagnostic import build_tracks_from_live_session

    live_tracks = [
        {"index": 0, "name": "1-MIDI", "devices": []},
        {"index": 1, "name": "2-MIDI", "devices": [{"name": "Operator"}]},
        {"index": 2, "name": "3-Audio", "devices": []},
        {"index": 3, "name": "Guitar Solo", "devices": [{"name": "Amp"}]},
    ]
    bounces = [
        {"label": "Guitar Solo", "filename": "Bounce Guitar Solo.wav", "path": "/path/to/guitar.wav"}
    ]

    tracks = build_tracks_from_live_session(live_tracks, bounces)
    assert len(tracks) == 4
    assert tracks[0]["track_name"] == "1-MIDI"
    assert tracks[0]["track_type"] == "midi"
    assert tracks[0]["has_audio_match"] is False

    assert tracks[1]["track_name"] == "2-MIDI"
    assert tracks[1]["track_type"] == "midi"

    assert tracks[2]["track_name"] == "3-Audio"
    assert tracks[2]["track_type"] == "audio"
    assert tracks[2]["is_audio"] is True

    assert tracks[3]["track_name"] == "Guitar Solo"
    assert tracks[3]["has_audio_match"] is True
    assert tracks[3]["matched_file_path"] == "/path/to/guitar.wav"


