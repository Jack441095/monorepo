"""E2/E9 regression: a generated fixture with known level, dynamics, spectrum and width gets a pinned grade,
the same inputs always grade the same, and each part moves only when its own measurement does.

Every fixture runs the full uploaded-reference path (`compare_reference_audio`), so a change anywhere between
the WAV decoder and the combined grade shows up here, not just in the scorer's unit tests.
"""
from __future__ import annotations

import io
import wave

import numpy as np
import pytest

from kenn.core.local_mix_review_service import compare_reference_audio

SAMPLE_RATE = 44100
# 4 s: long enough for integrated loudness (400 ms blocks) and the crest/width windows to settle,
# short enough that the six comparisons below cost about 4 s on the M-series Air.
SECONDS = 4


def _fixture(*, low=0.3, high=0.1, side=0.05, gain=1.0, pumped=False) -> bytes:
    """A 16-bit stereo WAV: 80 Hz, 1 kHz and 6 kHz partials in the middle, a 2.5 kHz partial in the side."""
    t = np.arange(SAMPLE_RATE * SECONDS) / SAMPLE_RATE
    mid = low * np.sin(2 * np.pi * 80 * t) + 0.2 * np.sin(2 * np.pi * 1000 * t) + high * np.sin(2 * np.pi * 6000 * t)
    # 1 rad offset keeps the side partial out of phase with the 1 kHz mid one so neither channel cancels.
    side_signal = side * np.sin(2 * np.pi * 2500 * t + 1.0)
    if pumped:
        # A 2 Hz square gate between 0.3 and 1.0 on mid and side together, so only the crest
        # factor moves; gating the mid alone also shifted the side/mid ratio by 2.6 dB.
        envelope = 0.3 + 0.7 * (np.sin(2 * np.pi * 2 * t) > 0)
        mid, side_signal = mid * envelope, side_signal * envelope
    frames = np.clip(np.stack([gain * (mid + side_signal), gain * (mid - side_signal)], axis=1), -1.0, 1.0)
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes((frames * 32767).astype("<i2").tobytes())
    return output.getvalue()


def _parts(result: dict) -> dict[str, float]:
    """Points per part, with the four reference-match components flattened in beside the three top-level parts."""
    points = {part["part"]: part["points"] for part in result["grade"]["parts"]}
    score = result["reference_comparison"]["reference_match_score"]
    points.update({part["part"]: part["points"] for part in score["parts"]})
    return points


@pytest.fixture(scope="module")
def graded():
    reference = _fixture()
    variants = {
        "same": _fixture(),
        # +3.5 dB (x1.5) of plain gain: the comparison is level-matched, the declared target is not.
        "louder": _fixture(gain=1.5),
        # 6 kHz partial up 9.5 dB (0.1 to 0.3).
        "bright": _fixture(high=0.3),
        # Side partial up 12 dB (0.05 to 0.2).
        "wide": _fixture(side=0.2),
        "pumped": _fixture(pumped=True),
    }
    return {name: compare_reference_audio(mix, "mix.wav", reference, "reference.wav") for name, mix in variants.items()}


def test_the_known_fixture_keeps_its_pinned_grade(graded):
    # Pinned 17 Oct 2026 on main 90437949. If this moves, a meter, tolerance or weighting changed:
    # say which in the commit, and re-pin only once the new number is the intended one.
    grade = graded["same"]["grade"]

    assert (grade["points"], grade["points_available"], grade["full_marks"]) == (60.2, 62.0, 100.0)
    assert _parts(graded["same"]) == {
        "technical_health": 10.2,
        "declared_target": 10.0,
        "reference_match": 40.0,
        "tonal_balance": 20.0,
        "dynamics": 10.0,
        "low_end_mono": 5.0,
        "stereo_width": 5.0,
    }


def test_the_same_inputs_grade_the_same_even_after_other_comparisons(graded):
    # The fixture already ran four other comparisons through the process-wide engines in between.
    again = compare_reference_audio(_fixture(), "mix.wav", _fixture(), "reference.wav")

    assert again["grade"] == graded["same"]["grade"]
    assert again["reference_comparison"]["reference_match_score"] == graded["same"]["reference_comparison"]["reference_match_score"]


def test_plain_gain_moves_the_declared_target_and_not_the_reference_match(graded):
    louder, same = _parts(graded["louder"]), _parts(graded["same"])

    assert louder["declared_target"] < same["declared_target"]
    assert louder["reference_match"] == same["reference_match"] == 40.0


def test_a_brighter_mix_loses_tonal_points_and_names_the_band_that_moved(graded):
    bright, same = _parts(graded["bright"]), _parts(graded["same"])
    tonal = next(p for p in graded["bright"]["reference_comparison"]["reference_match_score"]["parts"] if p["part"] == "tonal_balance")

    assert bright["tonal_balance"] < same["tonal_balance"]
    assert "sibilance" in tonal["detail"]
    assert bright["low_end_mono"] == same["low_end_mono"]
    assert bright["dynamics"] == same["dynamics"]


def test_a_wider_mix_loses_width_points_and_keeps_its_tonal_points(graded):
    wide, same = _parts(graded["wide"]), _parts(graded["same"])

    assert wide["stereo_width"] < same["stereo_width"]
    assert wide["tonal_balance"] == same["tonal_balance"]
    assert wide["low_end_mono"] == same["low_end_mono"]


def test_a_pumping_mix_loses_dynamics_points_and_keeps_its_width(graded):
    pumped, same = _parts(graded["pumped"]), _parts(graded["same"])

    assert pumped["dynamics"] < same["dynamics"]
    assert pumped["stereo_width"] == same["stereo_width"]
    assert pumped["tonal_balance"] == same["tonal_balance"]
