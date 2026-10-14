"""The Python loudness meter against signals built from the EBU Tech 3341/3342 recipes.

Written 14 Oct 2026 as part of E2: the grade quotes these numbers and deducts points on them, so we check the
meter before we trust the grade. The signals are generated here from the published recipe, not downloaded, because
we have not confirmed the EBU file URL or its terms. This is a spot check, not a conformance claim: it covers a
handful of the Tech 3341 cases, and the recalled values below should be checked against the EBU PDF before we say
"conforms" anywhere user-facing.
"""

from __future__ import annotations

import math

import numpy as np
import pyloudnorm as pyln
import pytest

from kenn.core.loudness_analysis import _windowed_loudness, loudness_range_lu, measure_loudness, true_peak_dbtp

RATE = 48_000  # Hz; Tech 3341 allows any rate, and 48 kHz is the one broadcast files use
TOLERANCE_LU = 0.1  # +/-0.1 LU, the Tech 3341 tolerance for integrated, momentary and short-term readings


def _stereo_sine(level_dbfs: float, seconds: float, freq_hz: float = 1000.0) -> np.ndarray:
    t = np.arange(int(seconds * RATE)) / RATE
    one = 10.0 ** (level_dbfs / 20.0) * np.sin(2.0 * np.pi * freq_hz * t)
    return np.stack([one, one], axis=1)


def _wav_bytes(data: np.ndarray) -> bytes:
    import io

    import soundfile as sf

    buf = io.BytesIO()
    sf.write(buf, data, RATE, format="WAV", subtype="FLOAT")
    return buf.getvalue()


@pytest.mark.parametrize("level_dbfs", [-23.0, -33.0])
def test_a_1khz_stereo_sine_reads_its_own_level_in_every_loudness_window(level_dbfs):
    # Tech 3341 cases 1 and 2: both channels at the level, so integrated, short-term and momentary all read it.
    result = measure_loudness(_wav_bytes(_stereo_sine(level_dbfs, 20.0)))

    assert result["integrated_lufs"] == pytest.approx(level_dbfs, abs=TOLERANCE_LU)
    assert result["short_term_max_lufs"] == pytest.approx(level_dbfs, abs=TOLERANCE_LU)
    assert result["momentary_max_lufs"] == pytest.approx(level_dbfs, abs=TOLERANCE_LU)


def test_quiet_passages_are_gated_out_of_the_integrated_reading():
    # Tech 3341 gating case: 10 s at -36, 60 s at -23, 10 s at -36. The relative gate drops the quiet ends, so
    # the answer is the loud middle's -23 LUFS, not the ~-24.5 a plain average would give.
    signal = np.concatenate([_stereo_sine(-36.0, 10.0), _stereo_sine(-23.0, 60.0), _stereo_sine(-36.0, 10.0)])

    assert measure_loudness(_wav_bytes(signal))["integrated_lufs"] == pytest.approx(-23.0, abs=TOLERANCE_LU)


def test_loudness_range_of_two_steady_levels_ten_lu_apart_is_ten():
    # Tech 3342 case 1 as we recall it (verify against the PDF): 20 s at -20 LUFS then 20 s at -30 LUFS reads 10 LU
    # with a +/-1 LU tolerance. Per-channel dBFS stands in for LUFS because a 1 kHz stereo sine reads its own level.
    signal = np.concatenate([_stereo_sine(-20.0, 20.0), _stereo_sine(-30.0, 20.0)])
    short_term = _windowed_loudness(pyln.Meter(RATE, block_size=0.400), signal, RATE, 3.0, 1.0)

    assert loudness_range_lu(short_term) == pytest.approx(10.0, abs=1.0)


@pytest.mark.parametrize("freq_hz", [997.0, 3000.0, 9000.0, 15000.0, 20000.0])
def test_true_peak_does_not_under_read_a_sine_wherever_its_peaks_fall(freq_hz):
    # The worst case for a sampled peak is a tone whose crests fall between samples, so we sweep the phase.
    # -0.2 / +0.1 dB is the engineering margin the 14 Oct peak comparison uses, deliberately tighter than Tech 3341.
    amplitude = 0.5  # -6.02 dBFS; a continuous sine's true peak is exactly its amplitude
    for phase in np.linspace(0.0, math.pi, 17):
        n = np.arange(RATE)
        tone = amplitude * np.sin(2.0 * np.pi * freq_hz * n / RATE + phase)
        # An abrupt start or stop is a step, and a step rings above its own level once it is upsampled
        # (a 20 kHz tone started at phase 0 read +0.23 dB). A 50 ms raised-cosine fade keeps the plateau at
        # exactly `amplitude` and leaves only the tone's own crests to measure.
        fade = np.ones(RATE)
        ramp = int(0.05 * RATE)  # 2400 samples
        fade[:ramp] = 0.5 - 0.5 * np.cos(np.pi * np.arange(ramp) / ramp)
        fade[-ramp:] = fade[:ramp][::-1]
        tone = tone * fade
        error_db = true_peak_dbtp(tone[:, None]) - 20.0 * math.log10(amplitude)

        assert -0.2 <= error_db <= 0.1, f"{freq_hz} Hz at phase {phase:.2f} read {error_db:+.3f} dB"
