"""Raw source and actual FFT-window activity precede within-stem spectral ranking."""

from __future__ import annotations

import io
import math
import wave

import pytest

from audio_analysis.mixdown.stem_solo import stem_spectrum_comparison
from audio_analysis.utils.audio_io import read_wav_mono


SAMPLE_RATE = 44100  # Hz, matching the existing generated mix-review examples.


def _tone(frequency_hz=80, amplitude=0.1, count=8192):
    return [amplitude * math.sin(2 * math.pi * frequency_hz * index / SAMPLE_RATE) for index in range(count)]


def _stem(name, samples):
    return {"name": name, "samples": samples, "sample_rate": SAMPLE_RATE}


def _wav(samples, sample_rate=SAMPLE_RATE):
    import struct

    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"".join(struct.pack("<h", int(value * 32767)) for value in samples))
    return output.getvalue()


def test_active_sources_keep_own_spectrum_fractions_with_window_provenance():
    result = stem_spectrum_comparison([_stem("bass", _tone()), _stem("vocal", _tone(1200))])
    assert [item["name"] for item in result["low_end_summary"]["ranked"]] == ["bass", "vocal"]
    assert result["dominant_band"]["bass"]["stem"] == "bass"
    assert result["low_end_summary"]["overlap_warning"] is None
    for entry in result["stems"]:
        activity = entry["activity"]
        assert activity["schema"] == "kenn.low_end_stem.activity.v1"
        assert activity["active_floor_dbfs"] == -60.0
        assert activity["source_rms_dbfs"] > -60
        assert activity["window_rms_dbfs"] > -60
        assert activity["sample_rate"] == SAMPLE_RATE
        assert activity["analysis_sample_count"] == 8192
        assert activity["frame_size_samples"] == 4096
        assert activity["window_start_sample"] == 2048


@pytest.mark.parametrize("amplitude", [0.0, 0.000001, 0.001])
def test_quiet_or_exact_floor_sources_cannot_enter_bands_or_ranks(amplitude):
    # Constant input places exact -60 dBFS on the boundary without sine RMS offsets.
    result = stem_spectrum_comparison([_stem("Bass", [amplitude] * 4096)])
    assert result["stems"] == []
    assert result["dominant_band"] == {}
    assert result["low_end_summary"]["ranked"] == []
    assert result["abstentions"][0]["name"] == "Bass"


def test_just_above_floor_stays_eligible_without_rounding_the_level():
    result = stem_spectrum_comparison([_stem("Bass", [0.001000001] * 4096)])
    assert result["stems"][0]["activity"]["window_rms_dbfs"] > -60


@pytest.mark.parametrize("window_samples", [[0.0] * 4096, [0.001] * 4096])
def test_active_full_source_cannot_qualify_quiet_center_window(window_samples):
    samples = _tone(count=4096) + window_samples + _tone(count=4096)
    result = stem_spectrum_comparison([_stem("Bass", samples)])
    assert result["stems"] == []
    assert "window" in result["abstentions"][0]["reason"]


@pytest.mark.parametrize("count,frame_size,start", [(256, 256, 0), (300, 256, 22), (700, 512, 94), (1500, 1024, 238), (3000, 2048, 476), (9000, 4096, 2452)])
def test_short_and_long_inputs_keep_the_existing_centered_fft_geometry(count, frame_size, start):
    result = stem_spectrum_comparison([_stem("Bass", _tone(count=count))])
    activity = result["stems"][0]["activity"]
    assert activity["frame_size_samples"] == frame_size
    assert activity["window_start_sample"] == start
    assert activity["analysis_sample_count"] == count


@pytest.mark.parametrize("bad", [[], [0.1] * 255, [float("nan")] * 4096, [float("inf")] * 4096, None])
def test_unusable_source_preserves_independent_qualified_rankings(bad):
    active = _stem("Bass", _tone())
    baseline = stem_spectrum_comparison([active])
    bad_stem = {"name": "Kick"} if bad is None else _stem("Kick", bad)
    result = stem_spectrum_comparison([bad_stem, active])
    assert result["stems"] == baseline["stems"]
    assert result["dominant_band"] == baseline["dominant_band"]
    assert result["low_end_summary"] == baseline["low_end_summary"]
    assert result["abstentions"][0]["name"] == "Kick"


@pytest.mark.parametrize("source_rms", [None, True, "0.1", -0.1, float("nan"), float("inf"), 0.0, 0.001])
def test_file_decoder_requires_genuine_active_full_source_rms(source_rms):
    def reader(data):
        return {"samples": _tone(), "sample_rate": SAMPLE_RATE, "true_rms": source_rms}

    result = stem_spectrum_comparison([{"name": "Bass.wav", "file_bytes": b"fixture"}], read_wav_mono=reader)
    assert result["stems"] == []
    assert result["low_end_summary"]["ranked"] == []


def test_file_decode_failure_is_an_identity_preserving_local_abstention():
    def reader(data):
        raise ValueError("invalid generated WAV")

    result = stem_spectrum_comparison([{"name": "Kick.wav", "file_bytes": b"fixture"}, _stem("Bass", _tone())], read_wav_mono=reader)
    assert [stem["name"] for stem in result["stems"]] == ["Bass"]
    assert result["abstentions"][0]["name"] == "Kick.wav"


def test_generated_wav_qualifies_effective_decimated_geometry():
    samples = _tone(count=SAMPLE_RATE * 4)
    result = stem_spectrum_comparison([{"name": "Bass.wav", "file_bytes": _wav(samples)}], read_wav_mono=read_wav_mono)
    activity = result["stems"][0]["activity"]
    assert activity["sample_rate"] == 22050.0
    assert activity["analysis_sample_count"] == SAMPLE_RATE * 2
    assert activity["frame_size_samples"] == 4096
    assert activity["window_start_sample"] == (SAMPLE_RATE * 2 - 4096) // 2
    assert result["stems"][0]["bands"]["bass"] > 0.99


def test_generated_file_with_active_ends_and_quiet_center_cannot_rank():
    samples = _tone(count=8192) + [0.0] * 16384 + _tone(count=8192)
    result = stem_spectrum_comparison([{"name": "Bass.wav", "file_bytes": _wav(samples)}], read_wav_mono=read_wav_mono)
    assert result["stems"] == []
    assert "window" in result["abstentions"][0]["reason"]


def test_larger_within_stem_fraction_does_not_trigger_a_masking_repair():
    result = stem_spectrum_comparison([_stem("Kick", _tone(70, 0.1)), _stem("Bass", _tone(90, 0.3))])
    assert len(result["low_end_summary"]["ranked"]) == 2
    assert result["low_end_summary"]["overlap_warning"] is None
    assert "own spectrum" in result["limitations"][0]


def test_finite_overloaded_float_source_is_still_an_actual_source():
    result = stem_spectrum_comparison([_stem("Bass", _tone(amplitude=1.2))])
    assert result["stems"][0]["name"] == "Bass"


def test_ambiguous_source_names_do_not_erase_an_independent_source():
    result = stem_spectrum_comparison([_stem("Bass", _tone()), _stem("Kick", _tone()), _stem("Kick", _tone())])
    assert [stem["name"] for stem in result["stems"]] == ["Bass"]
    assert len(result["abstentions"]) == 2


@pytest.mark.parametrize("name", [None, 12, True, "", "  ", " Kick", "Kick ", "K" * 97])
def test_invalid_source_identity_abstains_without_rewriting_or_erasing_other_sources(name):
    result = stem_spectrum_comparison([_stem(name, _tone()), _stem("Bass", _tone())])
    assert [stem["name"] for stem in result["stems"]] == ["Bass"]
    assert result["abstentions"][0]["name"] == name


def test_source_identity_at_96_character_limit_is_preserved():
    name = "K" * 96  # Characters: the bounded evidence identity limit.
    result = stem_spectrum_comparison([_stem(name, _tone())])
    assert result["stems"][0]["name"] == name


def test_fractional_effective_sample_rate_is_not_truncated():
    stem = _stem("Bass", _tone())
    stem["sample_rate"] = 22050.25  # Hz after a decoder's timing conversion.
    result = stem_spectrum_comparison([stem])
    assert result["stems"][0]["activity"]["sample_rate"] == 22050.25


def test_short_fft_overlapping_bins_preserve_bands_but_withhold_invalid_rank():
    result = stem_spectrum_comparison([_stem("Bass", _tone(count=256))])
    assert len(result["stems"]) == 1
    assert result["stems"][0]["activity"]["frame_size_samples"] == 256
    assert result["dominant_band"]
    assert result["low_end_summary"]["ranked"] == []
    assert "Overlapping FFT bins" in result["abstentions"][0]["reason"]


def test_rounding_cannot_hide_an_invalid_combined_low_end_fraction(monkeypatch):
    # Coarse overlapping bins remain invalid even when four decimals would hide the excess.
    from audio_analysis.mixdown import stem_solo

    monkeypatch.setattr(stem_solo, "_stem_bands", lambda *args, **kwargs: {"sub": .5, "bass": .50001})
    result = stem_spectrum_comparison([_stem("Bass", _tone())])
    assert result["stems"][0]["bands"]["bass"] == .50001
    assert result["low_end_summary"]["ranked"] == []
    assert "exceed 1" in result["abstentions"][0]["reason"]
