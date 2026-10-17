"""Reference Mixdown Coach & Matching Engine.

Compares a user mixdown against a commercial reference track across:
1. Tonal balance / Spectral Tilt (7-band energy distribution and EQ Eight curve)
2. Dynamics & Crest Factor (Peak, RMS, Crest Factor, Dynamic Range)
3. Stereo Imaging & Low-End Mono Compatibility (Correlation, Sub-120Hz Phase)
4. Actionable Ableton Live Coaching Recommendations & downloadable EQ Eight (.adv) preset.

Designed for KENN Phase 4 Intelligence. Supports 16-bit, 24-bit, and 32-bit float WAVs
with both vectorized NumPy/SciPy acceleration and pure Python fallbacks.
"""

from __future__ import annotations

import base64
import gzip
import math
import struct
import xml.etree.ElementTree as ET
from typing import Any

try:
    import numpy as np
except ImportError:
    np = None

from local_engine import _decode_channels, validate_wav_upload

BANDS_7: list[tuple[str, float, float]] = [
    ("sub", 20.0, 60.0),
    ("bass", 60.0, 250.0),
    ("low_mids", 250.0, 500.0),
    ("mids", 500.0, 2000.0),
    ("presence", 2000.0, 4000.0),
    ("sibilance", 4000.0, 8000.0),
    ("air", 8000.0, 20000.0),
]

BAND_CENTER_FREQS: dict[str, float] = {
    "sub": 45.0,
    "bass": 120.0,
    "low_mids": 350.0,
    "mids": 1000.0,
    "presence": 3000.0,
    "sibilance": 6000.0,
    "air": 12000.0,
}


def _safe_db(val: float, floor_db: float = -90.0) -> float:
    if val <= 1e-9:
        return floor_db
    return 20.0 * math.log10(val)


def _safe_db_pow(val: float, floor_db: float = -90.0) -> float:
    if val <= 1e-12:
        return floor_db
    return 10.0 * math.log10(val)


def compute_7band_spectrum(samples: Any, sample_rate: int) -> dict[str, float]:
    """Calculate relative energy fraction in each of the 7 standard mixing bands."""
    if np is not None:
        arr = np.asarray(samples, dtype=np.float64)
        if arr.ndim > 1:
            arr = np.mean(arr, axis=0)
        n = len(arr)
        if n == 0:
            return {name: 1.0 / len(BANDS_7) for name, _, _ in BANDS_7}
        # Windowed chunked or full rfft
        # Cap to at most 131072 samples evenly spaced to keep calculation under 10ms
        if n > 131072:
            step = max(1, n // 131072)
            arr = arr[::step]
            n = len(arr)
        fft_mag = np.abs(np.fft.rfft(arr))
        freqs = np.fft.rfftfreq(n, d=1.0 / sample_rate)

        total_energy = float(np.sum(fft_mag ** 2))
        if total_energy <= 1e-12:
            return {name: 1.0 / len(BANDS_7) for name, _, _ in BANDS_7}

        band_energies = {}
        for name, f_low, f_high in BANDS_7:
            mask = (freqs >= f_low) & (freqs < f_high)
            b_energy = float(np.sum(fft_mag[mask] ** 2))
            band_energies[name] = b_energy

        tot = sum(band_energies.values()) or 1.0
        return {k: v / tot for k, v in band_energies.items()}

    # Pure Python fallback
    s_list = list(samples)
    if not s_list:
        return {name: 1.0 / len(BANDS_7) for name, _, _ in BANDS_7}
    return {name: 1.0 / len(BANDS_7) for name, _, _ in BANDS_7}


def compute_dynamics_profile(samples: Any, sample_rate: int) -> dict[str, float]:
    """Extract Peak, RMS, Crest Factor, and dynamic spread.

    A (channels, frames) array is measured per channel: peak is the loudest channel and
    RMS the mean channel power, so L = -R reads at its real level instead of silent.
    """
    if np is not None:
        arr = np.asarray(samples, dtype=np.float64)
        if arr.size == 0:
            return {"peak_dbfs": -90.0, "rms_dbfs": -90.0, "crest_factor_db": 0.0, "dynamic_spread_db": 0.0}
        peak = float(np.max(np.abs(arr)))
        # Until 17 Oct 2026 the channels were averaged to mono first, so a polarity-flipped
        # mix read -90 dBFS and the reference gate called it silent. Mean power per frame
        # equals the mono power when L = R, so centred mixes measure as they did before.
        power = np.mean(arr ** 2, axis=0) if arr.ndim > 1 else arr ** 2
        rms = float(np.sqrt(np.mean(power)))
        peak_dbfs = _safe_db(peak)
        rms_dbfs = _safe_db(rms)
        crest_factor_db = max(0.0, peak_dbfs - rms_dbfs)

        # Rolling RMS dynamic spread (500ms windows)
        w_size = max(64, int(sample_rate * 0.5))
        if len(power) >= w_size:
            hop = max(1, w_size // 2)
            n_hops = (len(power) - w_size) // hop + 1
            if n_hops > 0:
                # Subsample up to 200 windows for fast stats
                indices = np.linspace(0, len(power) - w_size, min(n_hops, 200), dtype=int)
                window_rmss = [
                    float(np.sqrt(np.mean(power[idx : idx + w_size])))
                    for idx in indices
                ]
                dbs = [_safe_db(r) for r in window_rmss if r > 1e-6]
                spread = float(np.std(dbs)) if len(dbs) > 1 else 0.0
            else:
                spread = 0.0
        else:
            spread = 0.0

        return {
            "peak_dbfs": round(peak_dbfs, 2),
            "rms_dbfs": round(rms_dbfs, 2),
            "crest_factor_db": round(crest_factor_db, 2),
            "dynamic_spread_db": round(spread, 2),
        }

    # Pure Python
    s_list = list(samples)
    if not s_list:
        return {"peak_dbfs": -90.0, "rms_dbfs": -90.0, "crest_factor_db": 0.0, "dynamic_spread_db": 0.0}
    peak = max(abs(x) for x in s_list)
    rms = math.sqrt(sum(x * x for x in s_list) / len(s_list))
    peak_dbfs = _safe_db(peak)
    rms_dbfs = _safe_db(rms)
    return {
        "peak_dbfs": round(peak_dbfs, 2),
        "rms_dbfs": round(rms_dbfs, 2),
        "crest_factor_db": round(max(0.0, peak_dbfs - rms_dbfs), 2),
        "dynamic_spread_db": 0.0,
    }


def compute_stereo_profile(channels_list: list[Any], sample_rate: int) -> dict[str, Any]:
    """Return existing stereo measurements, using None wherever channel energy cannot support a reading."""
    if len(channels_list) < 2:
        # One channel has no stereo relationship to measure; numeric placeholders would earn grade points.
        return {
            "stereo_correlation": None,
            "low_mono_correlation": None,
            "side_mid_ratio_db": None,
            "is_mono": True,
        }

    left = channels_list[0]
    right = channels_list[1]

    if np is not None:
        l_arr = np.asarray(left, dtype=np.float64)
        r_arr = np.asarray(right, dtype=np.float64)
        min_len = min(len(l_arr), len(r_arr))
        if min_len == 0:
            # Empty channels leave no evidence for any stereo measurement.
            return {"stereo_correlation": None, "low_mono_correlation": None, "side_mid_ratio_db": None, "is_mono": False}
        l_arr = l_arr[:min_len]
        r_arr = r_arr[:min_len]

        # Overall correlation
        l_std = float(np.std(l_arr))
        r_std = float(np.std(r_arr))
        if l_std > 1e-7 and r_std > 1e-7:
            corr = float(np.corrcoef(l_arr, r_arr)[0, 1])
        else:
            # Pearson correlation is undefined when either channel has no variance.
            corr = None

        # Mid and Side
        mid = (l_arr + r_arr) * 0.5
        side = (l_arr - r_arr) * 0.5
        m_pow = float(np.mean(mid ** 2))
        s_pow = float(np.mean(side ** 2))
        # The existing 1e-12 power floor prevents division/log errors; hitting it is not a measured width.
        sm_ratio = _safe_db_pow(s_pow / (m_pow + 1e-12)) if m_pow > 1e-12 and s_pow > 1e-12 else None

        # Low-end mono correlation (FFT low-pass filter below 120 Hz)
        # Check sub 120Hz correlation
        sub_len = min(min_len, 65536)
        l_sub = l_arr[:sub_len]
        r_sub = r_arr[:sub_len]
        l_fft = np.fft.rfft(l_sub)
        r_fft = np.fft.rfft(r_sub)
        freqs = np.fft.rfftfreq(sub_len, d=1.0 / sample_rate)
        low_mask = freqs <= 120.0
        l_fft_low = np.zeros_like(l_fft)
        r_fft_low = np.zeros_like(r_fft)
        l_fft_low[low_mask] = l_fft[low_mask]
        r_fft_low[low_mask] = r_fft[low_mask]
        l_low = np.fft.irfft(l_fft_low, n=sub_len)
        r_low = np.fft.irfft(r_fft_low, n=sub_len)

        l_low_std = float(np.std(l_low))
        r_low_std = float(np.std(r_low))
        if l_low_std > 1e-7 and r_low_std > 1e-7:
            low_corr = float(np.corrcoef(l_low, r_low)[0, 1])
        else:
            # No bass in either channel is absent low-end evidence, not perfect mono compatibility.
            low_corr = None

        return {
            "stereo_correlation": round(float(np.clip(corr, -1.0, 1.0)), 3) if corr is not None else None,
            "low_mono_correlation": round(float(np.clip(low_corr, -1.0, 1.0)), 3) if low_corr is not None else None,
            "side_mid_ratio_db": round(sm_ratio, 2) if sm_ratio is not None else None,
            "is_mono": False,
        }

    # The pure-Python fallback does not calculate stereo measurements.
    return {
        "stereo_correlation": None,
        "low_mono_correlation": None,
        "side_mid_ratio_db": None,
        "is_mono": False,
    }


def compute_eq_matching_curve(mix_bands: dict[str, float], ref_bands: dict[str, float]) -> dict[str, float]:
    """Calculate target EQ gains (in dB) to align mix spectral balance with reference."""
    matching_gains = {}
    for name, _, _ in BANDS_7:
        m_pct = mix_bands.get(name, 0.0)
        r_pct = ref_bands.get(name, 0.0)
        diff = r_pct - m_pct
        # 10% energy delta roughly corresponds to 3 dB of gain adjustment
        gain = diff * 30.0
        gain = max(-6.0, min(6.0, gain))
        matching_gains[name] = round(gain, 1)
    return matching_gains


def generate_eq8_preset_xml(matching_gains: dict[str, float]) -> str:
    """Generate Ableton Live EQ Eight XML representation for the reference matching curve."""
    bands_config = [
        # Band 1: Highpass at 30 Hz to clear subsonic mud
        {"id": 0, "mode": 0, "freq": 30.0, "gain": 0.0, "q": 0.71, "on": "true"},
        # Band 2: Low Shelf for Sub (<60Hz)
        {"id": 1, "mode": 1, "freq": 60.0, "gain": matching_gains.get("sub", 0.0), "q": 0.5, "on": "true" if abs(matching_gains.get("sub", 0.0)) >= 0.3 else "false"},
        # Band 3: Bell for Bass (120Hz)
        {"id": 2, "mode": 2, "freq": 120.0, "gain": matching_gains.get("bass", 0.0), "q": 0.71, "on": "true" if abs(matching_gains.get("bass", 0.0)) >= 0.3 else "false"},
        # Band 4: Bell for Low-Mids (350Hz)
        {"id": 3, "mode": 2, "freq": 350.0, "gain": matching_gains.get("low_mids", 0.0), "q": 0.8, "on": "true" if abs(matching_gains.get("low_mids", 0.0)) >= 0.3 else "false"},
        # Band 5: Bell for Mids (1000Hz)
        {"id": 4, "mode": 2, "freq": 1000.0, "gain": matching_gains.get("mids", 0.0), "q": 0.71, "on": "true" if abs(matching_gains.get("mids", 0.0)) >= 0.3 else "false"},
        # Band 6: Bell for Presence (3000Hz)
        {"id": 5, "mode": 2, "freq": 3000.0, "gain": matching_gains.get("presence", 0.0), "q": 0.71, "on": "true" if abs(matching_gains.get("presence", 0.0)) >= 0.3 else "false"},
        # Band 7: Bell for Sibilance (6000Hz)
        {"id": 6, "mode": 2, "freq": 6000.0, "gain": matching_gains.get("sibilance", 0.0), "q": 1.0, "on": "true" if abs(matching_gains.get("sibilance", 0.0)) >= 0.3 else "false"},
        # Band 8: High Shelf for Air (>8000Hz)
        {"id": 7, "mode": 3, "freq": 10000.0, "gain": matching_gains.get("air", 0.0), "q": 0.71, "on": "true" if abs(matching_gains.get("air", 0.0)) >= 0.3 else "false"},
    ]

    root = ET.Element("Ableton", MajorVersion="5", MinorVersion="12.0_394", Creator="Ableton Live 12")
    eq8 = ET.SubElement(root, "Eq8")
    ET.SubElement(eq8, "On", Value="true")
    ET.SubElement(eq8, "IsExpanded", Value="true")

    bands_parent = ET.SubElement(eq8, "Bands")
    for b in bands_config:
        band_el = ET.SubElement(bands_parent, "Eq8Band")
        ET.SubElement(band_el, "Id", Value=str(b["id"]))
        ET.SubElement(band_el, "Mode", Value=str(b["mode"]))
        ET.SubElement(band_el, "Freq", Value=str(b["freq"]))
        ET.SubElement(band_el, "Gain", Value=str(b["gain"]))
        ET.SubElement(band_el, "Q", Value=str(b["q"]))
        ET.SubElement(band_el, "On", Value=b["on"])

    try:
        ET.indent(root, space="  ")
    except AttributeError:
        pass

    xml_str = ET.tostring(root, encoding="utf-8").decode("utf-8")
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_str}'


def export_eq8_preset_adv(matching_gains: dict[str, float]) -> bytes:
    """Serialize and gzip the Ableton EQ Eight XML into a valid .adv file."""
    xml_str = generate_eq8_preset_xml(matching_gains)
    return gzip.compress(xml_str.encode("utf-8"))


# Reference-match part of the E2 grade (40 points). Every tolerance below is a design choice made on
# 14 Oct 2026, not a measurement: the first two reuse thresholds this module already coaches with, and the rest
# are placeholders to be checked against the owner's ears under E9. Change them in one place, here.
REFERENCE_MATCH_POINTS: dict[str, float] = {"tonal_balance": 20.0, "dynamics": 10.0, "low_end_mono": 5.0, "stereo_width": 5.0}
TONAL_TOLERANCE_DB = 1.0  # same 1.0 dB at which compare_mix_to_reference starts suggesting an EQ move
TONAL_FULL_LOSS_DB = 6.0  # compute_eq_matching_curve clamps at +/-6 dB, so a band cannot read worse than this
CREST_TOLERANCE_DB = 2.5  # same 2.5 dB at which the dynamics coaching switches from "matches" to a compressor tip
CREST_FULL_LOSS_DB = 7.5  # 5 dB past the tolerance
LOW_CORR_TOLERANCE = 0.05  # correlation below 120 Hz may sit this far under the reference's before it costs anything
LOW_CORR_FULL_LOSS = 0.50  # a shortfall this large is a full loss
WIDTH_TOLERANCE_DB = 3.0  # side/mid ratio difference we do not charge for
WIDTH_FULL_LOSS_DB = 9.0
# Same -60 dBFS significance boundary as local_engine's silence detector: a house rule, not an EBU limit.
REFERENCE_MIN_RMS_DBFS = -60.0


def _loss_fraction(gap: float, tolerance: float, full_loss: float) -> float:
    """0.0 inside the tolerance, rising in a straight line to 1.0 at full_loss and staying there."""
    return min(1.0, max(0.0, gap - tolerance) / (full_loss - tolerance))


def _unscored_reference_match(reason: str) -> dict[str, Any]:
    """Leave all reference points unavailable, retaining the reason for the combined grade."""
    return {
        "points": 0.0,
        "points_available": 0.0,
        "full_marks": sum(REFERENCE_MATCH_POINTS.values()),
        "parts": [],
        "unscored": list(REFERENCE_MATCH_POINTS),
        "note": reason,
    }


def score_reference_match(comparison: dict[str, Any]) -> dict[str, Any]:
    """Score a `compare_mix_to_reference` result out of 40, from the producer's own reference only.

    Every point lost names the measured gap and that the source is the supplied reference. A part we could not
    compare (a mono file has no stereo image to match) is listed in `unscored` and its points come off
    `points_available`; the score is never rescaled up to 40. Missing, non-finite or effectively silent source RMS
    withholds the whole reference part, because matching silent placeholders is not evidence of similarity.
    """
    parts: list[dict[str, Any]] = []
    unscored: list[str] = []

    def measured(value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)

    dynamics = comparison.get("dynamics") or {}
    for source in ("mix", "reference"):
        rms = (dynamics.get(source) or {}).get("rms_dbfs")
        if not measured(rms) or rms <= REFERENCE_MIN_RMS_DBFS:
            # Silence can compare perfectly with itself; that is no evidence of a good reference match.
            return _unscored_reference_match(
                f"{source} RMS missing, non-finite or at/below {REFERENCE_MIN_RMS_DBFS:g} dBFS"
            )
        if (dynamics.get(source) or {}).get("mono_cancels") is True:
            # A loud L = -R file has real level, but against a mono reference nothing below
            # can see the cancellation and it would score full marks while vanishing on a
            # mono speaker. Withholding with the cause is the honest answer (17 Oct 2026).
            return _unscored_reference_match(
                f"{source} cancels in mono: left and right are opposite polarity, so flip one channel before comparing"
            )

    def add(name: str, gap: float, unit: str, tolerance: float, full_loss: float, detail: str) -> None:
        available = REFERENCE_MATCH_POINTS[name]
        lost = available * _loss_fraction(abs(gap), tolerance, full_loss)
        parts.append({
            "part": name,
            "points": round(available - lost, 1),
            "points_available": available,
            "gap": round(gap, 2),
            "unit": unit,
            "detail": detail,
            "source": "the reference track you supplied",
        })

    bands = comparison.get("matching_gains_db") or {}
    if bands and all(measured(g) for g in bands.values()):
        # The matching gain is how far each band is from the reference, so the mean of its size is the tonal gap.
        # Per-band losses are averaged rather than summed so one bad band cannot zero the whole part by itself.
        losses = [_loss_fraction(abs(g), TONAL_TOLERANCE_DB, TONAL_FULL_LOSS_DB) for g in bands.values()]
        available = REFERENCE_MATCH_POINTS["tonal_balance"]
        # Gains clamp at +/-6 dB, so a big shift ties two bands at the clamp and plain max() named
        # whichever sorts first. Lifting only a 6 kHz partial was reported as a bass gap (17 Oct 2026),
        # so a tie falls to the larger unclamped energy-share delta, the band that actually moved.
        # A band with no finite delta (a hand-built comparison without tonal_balance) counts as 0.0,
        # which only changes which tied band is named: gap and points are the same either way.
        energy_delta = {
            row.get("band"): abs(row["delta_pct"])
            for row in comparison.get("tonal_balance") or []
            if isinstance(row, dict) and measured(row.get("delta_pct"))
        }
        worst = max(bands, key=lambda b: (abs(bands[b]), energy_delta.get(b, 0.0)))
        parts.append({
            "part": "tonal_balance",
            "points": round(available * (1.0 - sum(losses) / len(losses)), 1),
            "points_available": available,
            "gap": round(abs(bands[worst]), 2),
            "unit": "dB (largest band)",
            "detail": f"largest band gap is {worst} at {bands[worst]:+.1f} dB of suggested correction",
            "source": "the reference track you supplied",
        })
    else:
        # An absent or non-finite spectrum cannot stand in for the reference's tonal balance.
        unscored.append("tonal_balance")

    crest_delta = dynamics.get("crest_factor_delta_db")
    if not measured(crest_delta):
        # Missing crest evidence removes these points instead of treating the gap as zero.
        unscored.append("dynamics")
    else:
        add("dynamics", crest_delta, "dB crest factor", CREST_TOLERANCE_DB, CREST_FULL_LOSS_DB,
            f"crest factor differs from the reference by {crest_delta:+.1f} dB")

    stereo = comparison.get("stereo") or {}
    mix_st, ref_st = stereo.get("mix") or {}, stereo.get("reference") or {}
    stereo_pair = bool(mix_st and ref_st and not mix_st.get("is_mono") and not ref_st.get("is_mono"))
    if (stereo_pair and measured(mix_st.get("low_mono_correlation"))
            and measured(ref_st.get("low_mono_correlation"))):
        shortfall = max(0.0, ref_st["low_mono_correlation"] - mix_st["low_mono_correlation"])
        add("low_end_mono", shortfall, "correlation below the reference", LOW_CORR_TOLERANCE, LOW_CORR_FULL_LOSS,
            f"correlation below 120 Hz is {mix_st['low_mono_correlation']:.2f} against {ref_st['low_mono_correlation']:.2f}")
    else:
        # Neither mono files nor absent bass have a stereo correlation to compare.
        unscored.append("low_end_mono")

    # Width needs measurable mid and side energy in both stereo files.
    if (stereo_pair and measured(mix_st.get("side_mid_ratio_db"))
            and measured(ref_st.get("side_mid_ratio_db"))):
        width_gap = mix_st["side_mid_ratio_db"] - ref_st["side_mid_ratio_db"]
        add("stereo_width", width_gap, "dB side/mid", WIDTH_TOLERANCE_DB, WIDTH_FULL_LOSS_DB,
            f"side/mid ratio is {width_gap:+.1f} dB from the reference")
    else:
        # Mono and unavailable width readings have no measured gap to grade.
        unscored.append("stereo_width")

    points_available = sum(p["points_available"] for p in parts)
    return {
        "points": round(sum(p["points"] for p in parts), 1),
        "points_available": points_available,
        "full_marks": sum(REFERENCE_MATCH_POINTS.values()),
        "parts": parts,
        "unscored": unscored,
        "note": "reference supplied, but no comparable reference measurements" if not points_available else "",
    }


def _equal_length(channels: list[Any]) -> list[Any]:
    frames = min(len(channel) for channel in channels)
    return [channel[:frames] for channel in channels]


def _spectral_signal(channels: list[Any], num_ch: int) -> tuple[Any, bool]:
    """Return the signal the tonal-balance bands read, and whether the mono sum cancels.

    Same rule as track_diagnostic._analysis_signal: an L = -R file sums to nothing, and
    7-band shares of nothing are noise, so we read L - R to keep the real tonal balance.
    """
    if num_ch < 2 or np is None:
        # Mono, or no NumPy: the pure-Python spectrum path has always read channel 0.
        return channels[0], False
    mono = (channels[0] + channels[1]) * 0.5
    channel_peak = float(max(np.max(np.abs(channels[0])), np.max(np.abs(channels[1]))))
    # -60 dB below the louder channel: the sum is gone but the channels are not.
    if channel_peak > 0.0 and float(np.max(np.abs(mono))) < channel_peak * 0.001:
        return (channels[0] - channels[1]) * 0.5, True
    return mono, False


def compare_mix_to_reference(
    mix_bytes: bytes,
    ref_bytes: bytes,
    mix_name: str = "User Mix",
    ref_name: str = "Reference",
) -> dict[str, Any]:
    """Execute complete Reference Mixdown comparison and coaching pipeline."""
    # 1. Validation
    val_mix = validate_wav_upload(mix_bytes, mix_name, label="User Mix")
    if not val_mix.get("ok"):
        return {"ok": False, "error": val_mix.get("error")}
    val_ref = validate_wav_upload(ref_bytes, ref_name, label="Reference Track")
    if not val_ref.get("ok"):
        return {"ok": False, "error": val_ref.get("error")}

    # 2. Decode channels
    mix_channels, mix_sr, mix_num_ch = _decode_channels(mix_bytes)
    ref_channels, ref_sr, ref_num_ch = _decode_channels(ref_bytes)

    if np is not None:
        # A data chunk cut mid-frame leaves channel 0 one sample longer than channel 1,
        # and the sums and stacks below need equal lengths.
        mix_channels = _equal_length(mix_channels)
        ref_channels = _equal_length(ref_channels)
    mix_mono, mix_cancels = _spectral_signal(mix_channels, mix_num_ch)
    ref_mono, ref_cancels = _spectral_signal(ref_channels, ref_num_ch)
    # Dynamics read both channels (see compute_dynamics_profile). Without NumPy the
    # channels are plain arrays, so the pure-Python path keeps reading the first one.
    mix_levels = np.stack(mix_channels[:2]) if mix_num_ch >= 2 and np is not None else mix_channels[0]
    ref_levels = np.stack(ref_channels[:2]) if ref_num_ch >= 2 and np is not None else ref_channels[0]

    # 3. Tonal balance analysis
    mix_bands = compute_7band_spectrum(mix_mono, mix_sr)
    ref_bands = compute_7band_spectrum(ref_mono, ref_sr)
    matching_gains = compute_eq_matching_curve(mix_bands, ref_bands)

    tonal_breakdown = []
    for name, f_low, f_high in BANDS_7:
        m_p = mix_bands.get(name, 0.0) * 100.0
        r_p = ref_bands.get(name, 0.0) * 100.0
        gain = matching_gains.get(name, 0.0)
        tonal_breakdown.append({
            "band": name,
            "range_hz": f"{int(f_low)}-{int(f_high)} Hz",
            "mix_energy_pct": round(m_p, 1),
            "ref_energy_pct": round(r_p, 1),
            "delta_pct": round(m_p - r_p, 1),
            "suggested_eq_gain_db": gain,
        })

    # 4. Dynamics profile
    mix_dyn = compute_dynamics_profile(mix_levels, mix_sr)
    ref_dyn = compute_dynamics_profile(ref_levels, ref_sr)
    # Carried with the levels because score_reference_match and the evidence gate read
    # only this dict; see score_reference_match for why a cancelling source is withheld.
    mix_dyn["mono_cancels"] = mix_cancels
    ref_dyn["mono_cancels"] = ref_cancels
    crest_delta = round(mix_dyn["crest_factor_db"] - ref_dyn["crest_factor_db"], 2)

    # 5. Stereo profile
    mix_stereo = compute_stereo_profile(mix_channels, mix_sr)
    ref_stereo = compute_stereo_profile(ref_channels, ref_sr)

    # 6. Actionable recommendations & coaching
    recommendations: list[dict[str, Any]] = []

    # EQ recommendations for significant deviations (> 1.0 dB suggested correction)
    for band_info in tonal_breakdown:
        gain = band_info["suggested_eq_gain_db"]
        if abs(gain) >= 1.0:
            b_name = band_info["band"]
            c_freq = BAND_CENTER_FREQS.get(b_name, 1000.0)
            recommendations.append({
                "target_device": "EQ Eight",
                "parameter": f"{b_name.capitalize()} Band Gain",
                "suggested_value": f"{gain:+.1f} dB",
                "center_frequency": f"{int(c_freq)} Hz",
                "reason": f"Mix has {abs(band_info['delta_pct']):.1f}% {'more' if band_info['delta_pct'] > 0 else 'less'} energy in the {band_info['range_hz']} range than the reference.",
            })

    # Dynamics coaching
    if crest_delta >= 2.5:
        dynamics_assessment = (
            f"Mix is noticeably more dynamic (+{crest_delta:.1f} dB crest factor) than reference. "
            "To achieve commercial punch and density, apply gentle bus compression."
        )
        recommendations.append({
            "target_device": "Glue Compressor",
            "parameter": "Threshold / Ratio",
            "suggested_value": "Ratio 2:1 or 4:1, 30ms Attack, Auto Release",
            "reason": f"Mix crest factor is {mix_dyn['crest_factor_db']:.1f} dB vs reference {ref_dyn['crest_factor_db']:.1f} dB. Aim for 2-3 dB gain reduction on loud peaks.",
        })
    elif crest_delta <= -2.5:
        dynamics_assessment = (
            f"Mix is over-compressed / squashed (-{abs(crest_delta):.1f} dB crest factor) relative to reference. "
            "Consider backing off bus limiter threshold or compression ratio to regain transient punch."
        )
        recommendations.append({
            "target_device": "Limiter / Compressor",
            "parameter": "Drive / Threshold",
            "suggested_value": "Ease limiter drive by 1.5 - 2.5 dB",
            "reason": f"Mix crest factor ({mix_dyn['crest_factor_db']:.1f} dB) is significantly flatter than reference ({ref_dyn['crest_factor_db']:.1f} dB).",
        })
    else:
        dynamics_assessment = (
            f"Dynamics and crest factor match commercial reference well (Δ {crest_delta:+.1f} dB)."
        )

    # Low-end mono correlation coaching
    if mix_stereo["low_mono_correlation"] is None or ref_stereo["low_mono_correlation"] is None:
        # The comparison needs bass evidence in both files before it can explain a correlation gap.
        stereo_assessment = "Low-end mono comparison unavailable: both files need measurable bass in two channels."
    elif mix_stereo["low_mono_correlation"] < 0.85:
        stereo_assessment = (
            f"Low-end phase cancellation alert: Sub/bass below 120 Hz has correlation {mix_stereo['low_mono_correlation']:.2f} "
            f"(reference is {ref_stereo['low_mono_correlation']:.2f}). Summing to mono will cause low-end loss."
        )
        recommendations.append({
            "target_device": "Utility",
            "parameter": "Bass Mono",
            "suggested_value": "Enabled @ 100 - 120 Hz",
            "reason": f"Sub-120 Hz correlation is {mix_stereo['low_mono_correlation']:.2f}. Mono-centering sub-bass prevents phase cancellations on club sound systems.",
        })
    else:
        stereo_assessment = (
            f"Low-end mono compatibility is solid ({mix_stereo['low_mono_correlation']:.2f} correlation below 120 Hz)."
        )

    # Peak ceiling check
    if mix_dyn["peak_dbfs"] > -0.3:
        recommendations.append({
            "target_device": "Limiter",
            "parameter": "Ceiling",
            "suggested_value": "-1.0 dBFS",
            "reason": f"Mix peak is hot ({mix_dyn['peak_dbfs']:.1f} dBFS). Lowering ceiling prevents inter-sample clipping on streaming lossy codecs.",
        })

    # 7. Generate EQ Eight .adv binary preset
    preset_adv_bytes = export_eq8_preset_adv(matching_gains)
    preset_b64 = base64.b64encode(preset_adv_bytes).decode("ascii")

    result = {
        "ok": True,
        "schema": "kenn.mix_review.reference_match.v1",
        "mix_name": mix_name,
        "reference_name": ref_name,
        "coaching_summary": {
            "tonal_assessment": f"EQ Eight matching curve generated across 7 frequency bands. Max deviation: {max(abs(g) for g in matching_gains.values()):.1f} dB.",
            "dynamics_assessment": dynamics_assessment,
            "stereo_assessment": stereo_assessment,
        },
        "tonal_balance": tonal_breakdown,
        "matching_gains_db": matching_gains,
        "dynamics": {
            "mix": mix_dyn,
            "reference": ref_dyn,
            "crest_factor_delta_db": crest_delta,
            "assessment": dynamics_assessment,
        },
        "stereo": {
            "mix": mix_stereo,
            "reference": ref_stereo,
            "assessment": stereo_assessment,
        },
        "recommendations": recommendations,
        "eq8_preset_adv_base64": preset_b64,
    }
    # Without NumPy the legacy comparison returns uniform bands and placeholder stereo values, not measurements.
    result["reference_match_score"] = (
        score_reference_match(result) if np is not None
        else _unscored_reference_match("reference-match analysis requires NumPy")
    )
    return result
