import base64
import gzip
import io
import math
import struct
import wave
import pytest

import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "core"))

from reference_matching import (
    analyze_mix_without_reference,
    compare_mix_to_reference,
    compare_mix_to_reference_spread,
    compute_7band_spectrum,
    compute_dynamics_profile,
    compute_stereo_profile,
    compute_eq_matching_curve,
    detect_tonal_bumps,
    export_eq8_preset_adv,
    generate_eq8_preset_xml,
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
    # 80 Hz sits below the 120 Hz bass cutoff, so both correlation readings have energy to measure.
    mono_wav = _make_wav(duration_s=0.5, freq_left=80.0, freq_right=80.0)
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


# E2 reference-match part (14 Oct 2026): scored only from the supplied reference, never rescaled.
from reference_matching import score_reference_match  # noqa: E402


def _comparison(gains=None, crest_delta=0.0, mix_stereo=None, ref_stereo=None):
    stereo = {"low_mono_correlation": 0.95, "side_mid_ratio_db": -9.0, "is_mono": False}
    return {
        "matching_gains_db": gains if gains is not None else {b: 0.0 for b in ("sub", "bass", "mids", "air")},
        "dynamics": {"crest_factor_delta_db": crest_delta, "mix": {"rms_dbfs": -18.0}, "reference": {"rms_dbfs": -18.0}},
        "stereo": {"mix": {**stereo, **(mix_stereo or {})}, "reference": {**stereo, **(ref_stereo or {})}},
    }


def test_a_mix_that_matches_its_reference_gets_all_forty():
    score = score_reference_match(_comparison())

    assert score["points"] == 40.0
    assert score["points_available"] == 40.0
    assert score["unscored"] == []


def test_a_mix_compared_with_itself_scores_full_marks():
    # Both tones sit below 120 Hz, and their difference gives measurable mid and side power.
    wav = _make_wav(duration_s=0.5, freq_left=80.0, freq_right=110.0)

    score = compare_mix_to_reference(wav, wav)["reference_match_score"]

    assert score["points"] == 40.0


def test_a_gap_inside_the_tolerance_costs_nothing():
    score = score_reference_match(_comparison(gains={"bass": 1.0, "mids": -1.0}, crest_delta=2.5))

    assert score["points"] == 40.0


def test_a_tonal_gap_costs_points_and_names_the_band_and_the_source():
    score = score_reference_match(_comparison(gains={"sub": 0.0, "bass": 6.0, "mids": 0.0, "air": 0.0}))

    tonal = next(p for p in score["parts"] if p["part"] == "tonal_balance")
    assert tonal["points"] == 15.0  # one of four bands fully lost: 20 * (1 - 1/4)
    assert "bass" in tonal["detail"]
    assert tonal["source"] == "the reference track you supplied"


def test_bands_tied_at_the_gain_clamp_name_the_band_whose_energy_moved_most():
    # 17 Oct 2026: a mix that only lifted a 6 kHz partial was told its largest gap was bass,
    # because both bands clamped at 6 dB and bass sorts first.
    comparison = _comparison(gains={"bass": 6.0, "mids": 3.1, "sibilance": -6.0})
    comparison["tonal_balance"] = [
        {"band": "bass", "delta_pct": -23.4},
        {"band": "mids", "delta_pct": -10.4},
        {"band": "sibilance", "delta_pct": 33.8},
    ]

    tonal = next(p for p in score_reference_match(comparison)["parts"] if p["part"] == "tonal_balance")

    assert "sibilance at -6.0 dB" in tonal["detail"]


def test_a_squashed_mix_loses_dynamics_points():
    score = score_reference_match(_comparison(crest_delta=-7.5))

    dynamics = next(p for p in score["parts"] if p["part"] == "dynamics")
    assert dynamics["points"] == 0.0


def test_a_mono_file_has_no_width_to_match_and_the_score_is_not_rescaled():
    score = score_reference_match(_comparison(mix_stereo={"is_mono": True, "side_mid_ratio_db": -90.0}))

    assert set(score["unscored"]) == {"low_end_mono", "stereo_width"}
    assert score["points_available"] == 30.0
    assert score["points"] == 30.0  # mono placeholders earn neither of the two 5-point stereo parts


def test_the_same_comparison_always_gets_the_same_score():
    comparison = _comparison(gains={"bass": 3.3, "air": -2.2}, crest_delta=4.1)

    assert score_reference_match(comparison) == score_reference_match(comparison)


def test_a_missing_comparison_section_is_unscored_not_assumed_good():
    score = score_reference_match({})

    assert set(score["unscored"]) == {"tonal_balance", "dynamics", "low_end_mono", "stereo_width"}
    assert score["points_available"] == 0.0


@pytest.mark.parametrize("source", ["mix", "reference"])
@pytest.mark.parametrize("rms", [None, float("nan"), float("inf"), True, -90.0, -60.0])
def test_missing_or_insignificant_source_rms_withholds_reference_points(source, rms):
    # The old placeholders let two silent files earn full marks just by matching each other.
    comparison = _comparison()
    comparison["dynamics"][source]["rms_dbfs"] = rms

    score = score_reference_match(comparison)

    assert score["points"] == score["points_available"] == 0.0
    assert set(score["unscored"]) == {"tonal_balance", "dynamics", "low_end_mono", "stereo_width"}
    assert source in score["note"]


def test_rms_above_the_significance_boundary_can_be_compared():
    comparison = _comparison()
    comparison["dynamics"]["mix"]["rms_dbfs"] = -59.99  # 0.01 dB above the -60 dBFS gate

    assert score_reference_match(comparison)["points"] == 40.0


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), True])
def test_unavailable_measurements_remove_only_their_reference_parts(value):
    comparison = _comparison(gains={"bass": value}, crest_delta=value,
                             mix_stereo={"low_mono_correlation": value, "side_mid_ratio_db": value})

    score = score_reference_match(comparison)

    assert score["points"] == score["points_available"] == 0.0
    assert len(score["unscored"]) == 4


def test_a_polarity_flipped_mix_is_withheld_for_cancelling_not_for_silence():
    # Until 17 Oct 2026 levels read the mono downmix, so L = -R measured -90 dBFS and the
    # producer was told the mix was silent rather than that it cancels in mono.
    reference = _make_wav(freq_left=80.0, freq_right=80.0)
    flipped = _make_wav(freq_left=80.0, freq_right=80.0, gain_right=-0.5)

    result = compare_mix_to_reference(flipped, reference)
    score = result["reference_match_score"]

    assert abs(result["dynamics"]["mix"]["rms_dbfs"] - result["dynamics"]["reference"]["rms_dbfs"]) < 0.1
    assert score["points_available"] == 0.0
    assert "mix cancels in mono" in score["note"]


def test_silent_wavs_do_not_earn_a_reference_grade():
    silent = _make_wav(gain_left=0.0, gain_right=0.0)

    score = compare_mix_to_reference(silent, silent)["reference_match_score"]

    assert score["points"] == score["points_available"] == 0.0


def test_numpy_fallback_does_not_grade_its_uniform_spectrum(monkeypatch):
    # The backend can load a second module instance; patch the instance that owns this imported function.
    monkeypatch.setitem(compare_mix_to_reference.__globals__, "np", None)
    wav = _make_wav()

    score = compare_mix_to_reference(wav, wav)["reference_match_score"]

    assert score["points"] == score["points_available"] == 0.0
    assert "NumPy" in score["note"]


@pytest.mark.parametrize("right_gain", [0.0, 1.0])
def test_bass_free_stereo_does_not_earn_low_end_correlation_points(right_gain):
    # Exact 1 kHz PCM periods at 8 kHz have no bass-bin energy; the old 1.0 fallback earned five points anyway.
    period = [0, 4634, 6553, 4634, 0, -4634, -6553, -4634]
    samples = [value for sample in period * 1000 for value in (sample, int(sample * right_gain))]
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(struct.pack(f"<{len(samples)}h", *samples))

    result = compare_mix_to_reference(output.getvalue(), output.getvalue())
    score = result["reference_match_score"]

    assert result["stereo"]["mix"]["low_mono_correlation"] is None
    assert "low_end_mono" in score["unscored"]
    assert all(p["part"] != "low_end_mono" for p in score["parts"])
    assert "unavailable" in result["coaching_summary"]["stereo_assessment"]
    if right_gain:
        # Identical channels also have no side energy, so their old -90 dB width floor earns no points.
        assert result["stereo"]["mix"]["side_mid_ratio_db"] is None
        assert "stereo_width" in score["unscored"]


def test_detect_tonal_bumps_identifies_local_peaks_and_ignores_smooth_slopes():
    # A smooth pink-noise slope (-3 dB/octave) has zero prominence and triggers no bumps
    smooth_slope = [float(-i * 1.5) for i in range(40)]
    assert detect_tonal_bumps(smooth_slope) == []

    # 40-band LTAS with an isolated 6.0 dB resonant peak at index 20
    spiky_spectrum = [-18.0] * 40
    spiky_spectrum[20] = -12.0  # +6.0 dB prominence above -18 dB baseline
    bumps = detect_tonal_bumps(spiky_spectrum, threshold_db=3.5)
    assert len(bumps) == 1
    assert bumps[0]["band_index"] == 20
    assert bumps[0]["prominence_db"] == 6.0
    assert bumps[0]["severity"] == "WARNING"  # >= 5.0 dB is WARNING
    assert bumps[0]["remediation"]["action"] == "apply_eq_cut"
    assert bumps[0]["remediation"]["gain_delta_db"] < 0.0

    # 7-band dict with low-mids resonance
    bands_dict = {"sub": 0.05, "bass": 0.15, "low_mids": 0.50, "mids": 0.15, "presence": 0.07, "sibilance": 0.04, "air": 0.04}
    bumps_7 = detect_tonal_bumps(bands_dict, threshold_db=3.5)
    assert len(bumps_7) == 1
    assert bumps_7[0]["band_name"] == "low_mids"
    assert bumps_7[0]["center_hz"] == 350.0


def test_analyze_mix_without_reference_evaluates_tonal_bumps_and_absolute_boundaries():
    # 1 kHz tone (Mids band) with moderate level
    mix_wav = _make_wav(duration_s=1.0, freq_left=1000.0, freq_right=1000.0, gain_left=0.6, gain_right=0.6)
    result = analyze_mix_without_reference(mix_wav, mix_name="Standalone Mix")

    assert result["ok"] is True
    assert result["schema"] == "kenn.mix_review.no_reference_analysis.v1"
    assert len(result["tonal_balance"]) == 7
    assert "tonal_bumps" in result
    assert "coaching_summary" in result
    assert "recommendations" in result
    # Reference match score must be unscored with explicit reason
    ref_score = result["reference_match_score"]
    assert ref_score["points"] == 0.0
    assert ref_score["points_available"] == 0.0
    assert "no reference track supplied" in ref_score["note"]


def test_analyze_mix_without_reference_withholds_on_silent_sources():
    silent_wav = _make_wav(duration_s=0.5, gain_left=0.0, gain_right=0.0)
    result = analyze_mix_without_reference(silent_wav, mix_name="Silent Mix")

    assert result["ok"] is True
    assert result["recommendations"] == []
    assert result["tonal_balance"] == []
    assert result["tonal_bumps"] == []
    assert "withheld" in result["coaching_summary"]["tonal_assessment"].lower()
    assert result["reference_match_score"]["points_available"] == 0.0


def test_compare_mix_to_reference_spread_distribution_matching_wilson_fazenda():
    # Test Wilson & Fazenda (2016) multi-reference distribution matching.
    # 3 references at 800 Hz (mids), 1000 Hz (mids), and 1200 Hz (mids)
    ref1 = _make_wav(duration_s=1.0, freq_left=800.0, freq_right=800.0, gain_left=0.6, gain_right=0.6)
    ref2 = _make_wav(duration_s=1.0, freq_left=1000.0, freq_right=1000.0, gain_left=0.6, gain_right=0.6)
    ref3 = _make_wav(duration_s=1.0, freq_left=1200.0, freq_right=1200.0, gain_left=0.6, gain_right=0.6)

    # Mix is closely aligned in mids (1000 Hz)
    mix = _make_wav(duration_s=1.0, freq_left=1000.0, freq_right=1000.0, gain_left=0.6, gain_right=0.6)

    result = compare_mix_to_reference_spread(
        mix, [ref1, ref2, ref3], mix_name="User Mix", ref_names=["Ref 1", "Ref 2", "Ref 3"]
    )

    assert result["ok"] is True
    assert result["schema"] == "kenn.mix_review.reference_spread_match.v1"
    assert result["reference_count"] == 3
    assert len(result["band_distribution"]) == 7
    # Each band distribution row contains mean, std dev, z-score, and suggested matching gain
    for row in result["band_distribution"]:
        assert "ref_mean_pct" in row
        assert "ref_std_pct" in row
        assert "z_score" in row
        assert "suggested_eq_gain_db" in row
    # Mids band should be well within 2.0 sigma of the references
    mids_row = next(r for r in result["band_distribution"] if r["band"] == "mids")
    assert abs(mids_row["z_score"]) < 2.0
    assert mids_row["suggested_eq_gain_db"] == 0.0  # Zero penalty and zero suggested move inside corridor

    # Scored out of 40 full marks
    score = result["reference_match_score"]
    assert score["full_marks"] == 40.0
    assert score["points"] > 30.0


def test_compare_mix_to_reference_spread_withholds_on_silent_reference():
    ref_active = _make_wav(duration_s=1.0, freq_left=440.0, freq_right=440.0, gain_left=0.6, gain_right=0.6)
    ref_silent = _make_wav(duration_s=1.0, gain_left=0.0, gain_right=0.0)
    mix = _make_wav(duration_s=1.0, freq_left=440.0, freq_right=440.0, gain_left=0.6, gain_right=0.6)

    result = compare_mix_to_reference_spread(mix, [ref_active, ref_silent], mix_name="User Mix")
    assert result["ok"] is True
    assert result["recommendations"] == []
    assert result["band_distribution"] == []
    assert "withheld" in result["coaching_summary"]["tonal_assessment"].lower()
    assert result["reference_match_score"]["points_available"] == 0.0


def test_compare_mix_to_reference_withholds_recommendations_and_presets_on_quiet_mix():
    # -60 dBFS significance gate: quiet mix or quiet reference withholds recommendations,
    # EQ preset, matching gains, and tonal breakdown.
    silent_mix = _make_wav(duration_s=1.0, gain_left=0.0, gain_right=0.0)
    ref = _make_wav(duration_s=1.0, freq_left=1000.0, freq_right=1000.0, gain_left=0.7, gain_right=0.7)

    result = compare_mix_to_reference(silent_mix, ref, mix_name="Silent Mix", ref_name="Pro Ref")
    assert result["ok"] is True
    assert result["recommendations"] == []
    assert result["matching_gains_db"] == {}
    assert result["eq8_preset_adv_base64"] is None
    assert result["tonal_balance"] == []
    assert "withheld" in result["coaching_summary"]["tonal_assessment"].lower()
    assert result["reference_match_score"]["points_available"] == 0.0

