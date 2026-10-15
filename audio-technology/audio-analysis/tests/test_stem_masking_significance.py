"""Generated preview examples keep raw activity and pair timing ahead of normalization."""

from __future__ import annotations

import math

import pytest

from audio_analysis.analysis_core.dsp_metrics import spectral_bands
from audio_analysis.mixdown.stem_analysis import analyze_stems_masking


FRAME_SIZE = 4096  # Samples; the producer requires complete frames, without padding.


def _tone_frame(amplitude=0.1, frequency_hz=220.0, sample_rate=44100):
    return [amplitude * math.sin(2 * math.pi * frequency_hz * index / sample_rate) for index in range(FRAME_SIZE)]


def _analyze(specs):
    stems = [{"name": name, "file_bytes": str(index).encode()} for index, (name, _, _) in enumerate(specs)]

    def read(encoded_index, max_samples):
        _, samples, rate = specs[int(encoded_index)]
        if isinstance(samples, Exception):
            raise samples
        return {"samples": samples, "sample_rate": rate, "analysis_sample_rate": rate}

    return analyze_stems_masking(stems, read_wav_mono=read, spectral_bands=spectral_bands)


def test_active_pair_retains_preview_visibility_and_bounded_provenance():
    result = _analyze([("Bass.wav", _tone_frame() * 2, 44100), ("Keys.wav", _tone_frame(frequency_hz=440) * 2, 44100)])
    assert {stem["name"] for stem in result["stems"]} == {"Bass", "Keys"}
    assert all(0 <= stem["overall_visibility"] <= 1 for stem in result["stems"])
    assert result["activity"] == {
        "schema": "kenn.erb_masking.activity.v1", "active_floor_dbfs": -60.0, "frame_size_samples": FRAME_SIZE,
        "sources": [{"name": name, "sample_rate": 44100.0, "frame_count": 2, "active_frame_count": 2} for name in ("Bass", "Keys")],
        "pairs": [{"stems": ["Bass", "Keys"], "simultaneously_active_frame_count": 2}],
    }
    assert result["erb_details"]["carving_suggestions"] == []
    assert result["erb_details"]["clarity_improvement"] == {}


@pytest.mark.parametrize("amplitude", [0.0, 0.000001, 0.001])
def test_quiet_or_exact_floor_source_cannot_become_normalized_masking(amplitude):
    # Constant frames give exact -60 dBFS RMS at amplitude .001, without sine rounding.
    result = _analyze([("Kick.wav", [amplitude] * FRAME_SIZE, 44100), ("Bass.wav", _tone_frame(), 44100)])
    assert result["stems"] == []
    assert result["activity"]["pairs"] == []
    assert result["activity"]["sources"][0]["active_frame_count"] == 0


def test_just_above_floor_raw_source_is_eligible():
    result = _analyze([("Kick.wav", [0.001000001] * FRAME_SIZE, 44100), ("Bass.wav", _tone_frame(), 44100)])
    assert result["activity"]["pairs"][0]["simultaneously_active_frame_count"] == 1


@pytest.mark.parametrize("samples", [[], [0.1] * (FRAME_SIZE - 1), [float("nan")] * FRAME_SIZE, [float("inf")] * FRAME_SIZE, ValueError("bad WAV")])
def test_unusable_unrelated_source_does_not_erase_active_pair(samples):
    baseline = _analyze([("Bass.wav", _tone_frame(), 44100), ("Keys.wav", _tone_frame(frequency_hz=440), 44100)])
    result = _analyze([("Bass.wav", _tone_frame(), 44100), ("Keys.wav", _tone_frame(frequency_hz=440), 44100), ("Kick.wav", samples, 44100)])
    assert result["stems"] == baseline["stems"]
    assert result["masking_matrix"] == baseline["masking_matrix"]
    assert result["erb_details"] == baseline["erb_details"]
    assert any(item["name"] == "Kick" for item in result["abstentions"])


def test_alternating_active_frames_cannot_be_called_simultaneous():
    tone = _tone_frame()
    silence = [0.0] * FRAME_SIZE
    result = _analyze([("Kick.wav", tone + silence, 44100), ("Bass.wav", silence + tone, 44100)])
    assert result["stems"] == []
    assert result["activity"]["pairs"] == []
    assert [source["active_frame_count"] for source in result["activity"]["sources"]] == [1, 1]


def test_shorter_tail_is_never_repeated_as_simultaneous_audio():
    result = _analyze([("Kick.wav", _tone_frame(), 44100), ("Bass.wav", [0.0] * FRAME_SIZE + _tone_frame(), 44100)])
    assert result["stems"] == []
    assert result["activity"]["pairs"] == []


def test_different_effective_rates_do_not_share_a_frame_timeline():
    result = _analyze([("Kick.wav", _tone_frame(), 44100), ("Bass.wav", _tone_frame(), 22050)])
    assert result["stems"] == []
    assert result["activity"]["pairs"] == []


def test_only_simultaneously_active_frames_contribute_to_visibility():
    baseline = _analyze([("Bass.wav", _tone_frame(), 44100), ("Keys.wav", _tone_frame(frequency_hz=440), 44100)])
    result = _analyze([("Bass.wav", _tone_frame() + _tone_frame(frequency_hz=10000), 44100), ("Keys.wav", _tone_frame(frequency_hz=440) + [0.0] * FRAME_SIZE, 44100)])
    assert result["stems"] == baseline["stems"]
    assert result["masking_matrix"] == baseline["masking_matrix"]
    assert result["erb_details"] == baseline["erb_details"]


def test_preview_budget_does_not_count_seventeenth_frame():
    result = _analyze([("Bass.wav", [0.0] * FRAME_SIZE * 16 + _tone_frame(), 44100), ("Keys.wav", _tone_frame() * 17, 44100)])
    assert result["stems"] == []
    assert all(source["frame_count"] == 16 for source in result["activity"]["sources"])


def test_ambiguous_names_abstain_without_removing_an_independent_pair():
    result = _analyze([("Bass.wav", _tone_frame(), 44100), ("Keys.wav", _tone_frame(), 44100), ("Kick.wav", _tone_frame(), 44100), ("Kick.aiff", _tone_frame(), 44100)])
    assert {stem["name"] for stem in result["stems"]} == {"Bass", "Keys"}
    assert all(source["name"] != "Kick" for source in result["activity"]["sources"])


def test_finite_float_render_above_full_scale_retains_activity():
    # Float WAVs can exceed 0 dBFS; clipping evidence must not erase a real source.
    result = _analyze([("Bass.wav", _tone_frame(amplitude=1.2), 44100), ("Keys.wav", _tone_frame(), 44100)])
    assert {stem["name"] for stem in result["stems"]} == {"Bass", "Keys"}
    assert result["activity"]["pairs"][0]["simultaneously_active_frame_count"] == 1
