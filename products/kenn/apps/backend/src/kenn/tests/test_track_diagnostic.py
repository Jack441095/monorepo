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


def _stereo_wav(left: list[float], right: list[float], sample_rate: int = 48000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"".join(
            struct.pack("<hh", int(l * 32767.0), int(r * 32767.0)) for l, r in zip(left, right)
        ))
    return buf.getvalue()


def test_stereo_level_and_loudness_are_measured_per_channel():
    # Until 16 Oct 2026 the scan averaged to mono first: L = -R read -96 dBFS,
    # and every stereo LUFS came out 3 dB below the mix-review figure.
    tone = [0.1 * math.sin(2.0 * math.pi * 1000.0 * i / 48000.0) for i in range(48000 * 2)]
    flipped = analyze_track_diagnostic(_stereo_wav(tone, [-v for v in tone]))["metrics"]
    assert abs(flipped["peak_dbfs"] + 20.0) < 0.1
    assert any(abs(p["frequency_hz"] - 1000.0) < 30.0 for p in flipped["resonant_peaks"])
    centred = analyze_track_diagnostic(_stereo_wav(tone, tone))["metrics"]
    if centred["lufs_integrated"] is not None:  # pyloudnorm is optional
        # A -20 dBFS 1 kHz sine on both channels is -20 LUFS (BS.1770 sums channel power).
        assert abs(centred["lufs_integrated"] + 20.0) < 0.2


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


def test_polarity_flipped_stereo_still_shows_a_waveform() -> None:
    # When L = -R the mono sum cancels to zero, so the display falls back to the
    # side signal (L - R) / 2 instead of drawing a flat zero line.
    tone = [0.4 * math.sin(2.0 * math.pi * 440.0 * i / 48000.0) for i in range(48000)]
    res = analyze_track_diagnostic(_stereo_wav(tone, [-v for v in tone]))
    assert res["ok"] is True
    assert max(res["waveform"]["peaks"]) > 0.35
    assert max(res["waveform"]["rms"]) > 0.2


def test_silence_reports_none_for_centroid_and_flatness_instead_of_one() -> None:
    # Bug fixed 17 Oct 2026: librosa scored silent frames as flatness 1.0 and
    # centroid 0 Hz, which made silent stems look like white noise and inflated
    # flatness on stems with rests.
    silent = [0.0] * 48000
    res = analyze_track_diagnostic(_stereo_wav(silent, silent))
    assert res["ok"] is True
    assert res["metrics"]["spectral_centroid_hz"] is None
    assert res["metrics"]["spectral_flatness"] is None
    assert res["metrics"]["lufs_integrated"] is None


def test_a_stale_extension_without_track_diagnostic_abstains_cleanly(monkeypatch) -> None:
    from kenn.core import native_fft

    real_module = native_fft._load()

    class _StaleModule:
        decode_pcm = staticmethod(real_module.decode_pcm)

    monkeypatch.setattr(native_fft, "_load", lambda: _StaleModule)
    res = analyze_track_diagnostic(_make_synth_wav([440.0], duration=0.5))
    assert res["ok"] is False
    assert "out of date" in res["error"]


def test_an_unsupported_wav_format_returns_ok_false_with_a_reason() -> None:
    # Format tag 2 (ADPCM) with 16-bit samples is refused by the native decoder.
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + 400,
        b"WAVE",
        b"fmt ",
        16,
        2,  # ADPCM format tag
        1,
        44100,
        88200,
        2,
        16,
        b"data",
        400,
    )
    res = analyze_track_diagnostic(header + b"\x00" * 400)
    assert res["ok"] is False
    assert "unsupported WAV sample format" in res["error"]


def test_eight_bit_and_multichannel_wavs_decode_natively() -> None:
    # 8-bit WAVs are unsigned with 128 as silence; 4-channel WAVs average across
    # all channels for the display mono sum while measuring peak across channels.
    rate = 44100
    frames = rate // 2
    buf_8bit = io.BytesIO()
    with wave.open(buf_8bit, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(1)
        wf.setframerate(rate)
        wf.writeframes(bytes(
            int(128 + round(64.0 * math.sin(2.0 * math.pi * 440.0 * i / rate)))
            for i in range(frames)
        ))
    res_8 = analyze_track_diagnostic(buf_8bit.getvalue())
    assert res_8["ok"] is True
    assert abs(res_8["metrics"]["peak_dbfs"] - (-6.02)) < 0.25

    buf_4ch = io.BytesIO()
    with wave.open(buf_4ch, "wb") as wf:
        wf.setnchannels(4)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"".join(
            struct.pack(
                "<hhhh",
                int(0.5 * math.sin(2.0 * math.pi * 440.0 * i / rate) * 32767.0),
                0,
                0,
                0,
            )
            for i in range(frames)
        ))
    res_4ch = analyze_track_diagnostic(buf_4ch.getvalue())
    assert res_4ch["ok"] is True
    assert abs(res_4ch["metrics"]["peak_dbfs"] - (-6.02)) < 0.2
    # Mean of channel RMS across 1 active (0.3536 RMS) and 3 silent channels is 0.0884 (-21.07 dBFS).
    assert abs(res_4ch["metrics"]["rms_dbfs"] - (-21.07)) < 0.2
    # 1 active front channel at 0.5 peak (-9.03 dBFS RMS) has BS.1770 LUFS = -0.691 - 9.03 = -9.72 LUFS.
    assert res_4ch["metrics"]["lufs_integrated"] == pytest.approx(-9.72, abs=0.1)


def test_nan_float_wav_fails_track_diagnostic_cleanly() -> None:
    import json

    raw_data = struct.pack("<ff", 0.25, float("nan")) * 4096
    fmt_chunk = struct.pack("<4sIHHIIHH", b"fmt ", 16, 3, 2, 48000, 48000 * 8, 8, 32)
    data_chunk = struct.pack("<4sI", b"data", len(raw_data)) + raw_data
    payload = struct.pack("<4sI4s", b"RIFF", 4 + len(fmt_chunk) + len(data_chunk), b"WAVE") + fmt_chunk + data_chunk

    res = analyze_track_diagnostic(payload)
    assert res["ok"] is False
    assert "NaN or infinite" in res["error"]
    json.dumps(res, allow_nan=False)

