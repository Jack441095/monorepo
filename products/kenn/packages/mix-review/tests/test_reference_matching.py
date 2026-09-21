import base64
import gzip
import io
import math
import struct
import wave
import pytest

from reference_matching import (
    compare_mix_to_reference,
    compute_7band_spectrum,
    compute_dynamics_profile,
    compute_stereo_profile,
    compute_eq_matching_curve,
    generate_eq8_preset_xml,
    export_eq8_preset_adv,
)


def _make_wav(
    duration_s: float = 1.0,
    sample_rate: int = 44100,
    channels: int = 2,
    freq_left: float = 440.0,
    freq_right: float = 440.0,
    gain_left: float = 0.5,
    gain_right: float = 0.5,
) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        total_frames = int(duration_s * sample_rate)
        frames = bytearray()
        for i in range(total_frames):
            t = i / sample_rate
            s_l = int(gain_left * 32767.0 * math.sin(2.0 * math.pi * freq_left * t))
            frames.extend(struct.pack("<h", s_l))
            if channels == 2:
                s_r = int(gain_right * 32767.0 * math.sin(2.0 * math.pi * freq_right * t))
                frames.extend(struct.pack("<h", s_r))
        w.writeframes(frames)
    return buf.getvalue()


def test_compute_7band_spectrum():
    # Low frequency tone (100 Hz, Bass band)
    bass_wav = _make_wav(duration_s=0.5, freq_left=100.0, freq_right=100.0)
    from local_engine import _decode_channels
    ch, sr, _ = _decode_channels(bass_wav)
    mono = (ch[0] + ch[1]) * 0.5
    bands = compute_7band_spectrum(mono, sr)
    assert "bass" in bands
    assert "sub" in bands
    assert "air" in bands
    # The bass band should have the lion's share of energy
    assert bands["bass"] > bands["presence"]
    assert bands["bass"] > bands["air"]


def test_compute_dynamics_profile():
    wav = _make_wav(duration_s=0.5, gain_left=0.8, gain_right=0.8)
    from local_engine import _decode_channels
    ch, sr, _ = _decode_channels(wav)
    mono = (ch[0] + ch[1]) * 0.5
    dyn = compute_dynamics_profile(mono, sr)
    assert dyn["peak_dbfs"] > -6.0
    assert dyn["rms_dbfs"] < dyn["peak_dbfs"]
    assert dyn["crest_factor_db"] > 0.0


def test_compute_stereo_profile():
    # Identical L and R -> correlation 1.0
    mono_wav = _make_wav(duration_s=0.5, freq_left=200.0, freq_right=200.0)
    from local_engine import _decode_channels
    ch, sr, _ = _decode_channels(mono_wav)
    stereo = compute_stereo_profile(ch, sr)
    assert stereo["stereo_correlation"] == pytest.approx(1.0, abs=0.01)
    assert stereo["low_mono_correlation"] == pytest.approx(1.0, abs=0.01)

    # Inverted L and R -> correlation -1.0
    inv_wav = _make_wav(duration_s=0.5, freq_left=200.0, freq_right=200.0, gain_left=0.5, gain_right=-0.5)
    ch_inv, sr_inv, _ = _decode_channels(inv_wav)
    stereo_inv = compute_stereo_profile(ch_inv, sr_inv)
    assert stereo_inv["stereo_correlation"] == pytest.approx(-1.0, abs=0.01)


def test_export_eq8_preset_adv():
    gains = {"sub": 2.5, "bass": -1.2, "low_mids": 0.0, "mids": 1.5, "presence": -2.0, "sibilance": 0.5, "air": 1.0}
    adv_bytes = export_eq8_preset_adv(gains)
    assert len(adv_bytes) > 0
    # Must be valid gzip
    decompressed = gzip.decompress(adv_bytes).decode("utf-8")
    assert "<Ableton" in decompressed
    assert "<Eq8" in decompressed
    assert "Eq8Band" in decompressed


def test_compare_mix_to_reference_full_pipeline():
    # Mix is bass-heavy, reference is treble-heavy
    mix_bytes = _make_wav(duration_s=1.0, freq_left=80.0, freq_right=80.0, gain_left=0.7, gain_right=0.7)
    ref_bytes = _make_wav(duration_s=1.0, freq_left=3500.0, freq_right=3500.0, gain_left=0.7, gain_right=0.7)

    result = compare_mix_to_reference(mix_bytes, ref_bytes, mix_name="Test Mix", ref_name="Reference Pro")
    assert result["ok"] is True
    assert result["schema"] == "kenn.mix_review.reference_match.v1"
    assert len(result["tonal_balance"]) == 7
    assert "coaching_summary" in result
    assert "recommendations" in result
    assert len(result["recommendations"]) > 0
    assert "eq8_preset_adv_base64" in result

    # Check decoded .adv preset
    raw_adv = base64.b64decode(result["eq8_preset_adv_base64"])
    xml_str = gzip.decompress(raw_adv).decode("utf-8")
    assert "Eq8Band" in xml_str
