"""Psychoacoustic reference profile matching and Ableton EQ Eight preset generation."""

from __future__ import annotations
import gzip
import xml.etree.ElementTree as ET

def compute_eq_matching_curve(mix_bands: dict, ref_bands: dict) -> dict[str, float]:
    """Compute target EQ gains (in dB) to match the reference spectral balance."""
    bands_keys = ["sub", "bass", "low_mids", "mids", "presence", "sibilance", "air"]
    matching_gains = {}
    
    for k in bands_keys:
        m_val = float(mix_bands.get(k, 0.0))
        r_val = float(ref_bands.get(k, 0.0))
        
        # Energy difference
        diff = r_val - m_val
        
        # Map energy differences to target dB.
        # A 10% energy difference corresponds roughly to 3dB of gain.
        gain = diff * 30.0
        
        # Limit the corrections to a musical range [-6.0, +6.0] dB to avoid drastic changes
        gain = max(-6.0, min(6.0, gain))
        matching_gains[k] = round(gain, 1)
        
    return matching_gains

def generate_eq8_preset_xml(matching_gains: dict[str, float]) -> str:
    """Create the Ableton EQ Eight XML representation for the matching curve."""
    # Ableton EQ Eight XML Schema Structure
    # Modes: 0 = Low Cut, 1 = Low Shelf, 2 = Bell, 3 = High Shelf, 4 = High Cut
    bands_config = [
        # Band 1: Low Cut (Highpass) to clear sub rumble (always on)
        {"id": 0, "mode": 0, "freq": 30.0, "gain": 0.0, "q": 0.71, "on": "true"},
        # Band 2: Low Shelf for sub-bass adjustments
        {"id": 1, "mode": 1, "freq": 80.0, "gain": matching_gains.get("sub", 0.0), "q": 0.5, "on": "true" if abs(matching_gains.get("sub", 0.0)) > 0.2 else "false"},
        # Band 3: Bell for bass adjustments
        {"id": 2, "mode": 2, "freq": 120.0, "gain": matching_gains.get("bass", 0.0), "q": 0.71, "on": "true" if abs(matching_gains.get("bass", 0.0)) > 0.2 else "false"},
        # Band 4: Bell for low-mids adjustments
        {"id": 3, "mode": 2, "freq": 250.0, "gain": matching_gains.get("low_mids", 0.0), "q": 0.9, "on": "true" if abs(matching_gains.get("low_mids", 0.0)) > 0.2 else "false"},
        # Band 5: Bell for mids adjustments
        {"id": 4, "mode": 2, "freq": 1000.0, "gain": matching_gains.get("mids", 0.0), "q": 0.71, "on": "true" if abs(matching_gains.get("mids", 0.0)) > 0.2 else "false"},
        # Band 6: Bell for presence adjustments
        {"id": 5, "mode": 2, "freq": 4000.0, "gain": matching_gains.get("presence", 0.0), "q": 0.71, "on": "true" if abs(matching_gains.get("presence", 0.0)) > 0.2 else "false"},
        # Band 7: Bell for sibilance adjustments
        {"id": 6, "mode": 2, "freq": 7000.0, "gain": matching_gains.get("sibilance", 0.0), "q": 1.2, "on": "true" if abs(matching_gains.get("sibilance", 0.0)) > 0.2 else "false"},
        # Band 8: High Shelf for air adjustments
        {"id": 7, "mode": 3, "freq": 12000.0, "gain": matching_gains.get("air", 0.0), "q": 0.71, "on": "true" if abs(matching_gains.get("air", 0.0)) > 0.2 else "false"},
    ]

    root = ET.Element("Ableton", MajorVersion="5", MinorVersion="12.0_394", Creator="Ableton Live 11")
    eq8 = ET.SubElement(root, "Eq8")
    
    # Standard properties
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

    # Pretty print or convert to string
    try:
        ET.indent(root, space="  ")
    except AttributeError:
        pass  # Python < 3.9 fallback
        
    xml_str = ET.tostring(root, encoding="utf-8").decode("utf-8")
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_str}'

def export_eq8_preset_adv(matching_gains: dict[str, float]) -> bytes:
    """Generate the XML and return the compressed GZIP bytes (.adv format)."""
    xml_str = generate_eq8_preset_xml(matching_gains)
    # Ableton expects Gzipped XML content
    return gzip.compress(xml_str.encode("utf-8"))


def generate_eq8_preset_xml_parametric(solved_bands: list[dict]) -> str:
    """Create the Ableton EQ Eight XML representation for solved parametric bands."""
    bands_config = [
        # Band 1: Low Cut (Highpass) to clear sub rumble (always on)
        {"id": 0, "mode": 0, "freq": 30.0, "gain": 0.0, "q": 0.71, "on": "true"},
    ]
    for i in range(4):
        sb = solved_bands[i] if i < len(solved_bands) else {"freq": 1000.0, "gain": 0.0, "q": 0.7}
        bands_config.append({
            "id": i + 1,
            "mode": 2, # Bell
            "freq": sb["freq"],
            "gain": sb["gain"],
            "q": sb["q"],
            "on": "true" if abs(sb["gain"]) > 0.1 else "false",
        })
    for i in range(5, 8):
        bands_config.append({
            "id": i,
            "mode": 2,
            "freq": 1000.0,
            "gain": 0.0,
            "q": 0.7,
            "on": "false",
        })

    root = ET.Element("Ableton", MajorVersion="5", MinorVersion="12.0_394", Creator="Ableton Live 11")
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


def export_eq8_preset_parametric(solved_bands: list[dict]) -> bytes:
    """Generate the XML and return the compressed GZIP bytes (.adv format) for solved parametric bands."""
    xml_str = generate_eq8_preset_xml_parametric(solved_bands)
    return gzip.compress(xml_str.encode("utf-8"))


def generate_pro_q3_preset_xml(solved_bands: list[dict], name: str = "Audio Too Reference Match") -> str:
    """Serialize solved bell filters as a portable Pro-Q 3 preset exchange document."""
    root = ET.Element(
        "FabFilterPreset",
        Product="Pro-Q 3",
        Version="3",
        Name=str(name or "Audio Too Reference Match")[:120],
    )
    bands = ET.SubElement(root, "Bands")
    for index, band in enumerate(solved_bands[:8], start=1):
        ET.SubElement(
            bands,
            "Band",
            Index=str(index),
            Enabled="1" if abs(float(band.get("gain", 0.0))) > 0.1 else "0",
            Shape="Bell",
            Frequency=f"{max(20.0, min(20_000.0, float(band.get('freq', 1000.0)))):.2f}",
            Gain=f"{max(-6.0, min(6.0, float(band.get('gain', 0.0)))):.2f}",
            Q=f"{max(0.3, min(8.0, float(band.get('q', 0.707)))):.3f}",
        )
    ET.SubElement(root, "Output", Gain="0.00", Phase="Natural")
    try:
        ET.indent(root, space="  ")
    except AttributeError:
        pass
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        root, encoding="unicode"
    )


def export_pro_q3_preset(solved_bands: list[dict], name: str = "Audio Too Reference Match") -> bytes:
    """Return the Pro-Q 3 exchange preset payload for a ``.ffp`` download."""
    return generate_pro_q3_preset_xml(solved_bands, name=name).encode("utf-8")



# ---------------------------------------------------------------------------
# Phase 9.2 — Dynamic Compressor Reference Matching
# ---------------------------------------------------------------------------

import math

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view


def _rolling_rms(samples: list[float], window_samples: int) -> list[float]:
    """Compute rolling RMS over a window (hop = window // 2).

    Vectorized 2026-08-01 (was an O(n/hop * window) Python loop -- the whole
    point of ``dynamics_comparison`` is to run over a full mixdown, so this
    was doing tens of millions of scalar multiply-adds per call). Uses
    ``sliding_window_view`` sliced by hop *before* squaring, so only the
    selected (non-overlapping-by-hop) windows are ever materialized, not
    every overlapping window in the signal.

    NOT bit-exact vs. the old loop: float64 summation order for the RMS
    mean differs between a per-window Python ``sum()`` and numpy's
    reduction (same math, different intermediate rounding) -- expected,
    documented, and verified numerically equivalent within tight tolerance
    on synthetic signals in
    tests/audio_analysis/test_reference_matching_vectorized.py. Accepts
    list or ndarray input identically (``np.asarray`` normalizes either);
    the old ``if not samples`` guard raised on ndarray input, this one
    checks ``.size`` instead.
    """
    if samples is None or window_samples <= 0:
        return []
    arr = np.asarray(samples, dtype=np.float64)
    if arr.size == 0 or arr.size < window_samples:
        return []
    hop = max(1, window_samples // 2)
    windows = sliding_window_view(arr, window_samples)[::hop]
    ms = np.mean(windows * windows, axis=1)
    return np.sqrt(np.maximum(ms, 0.0)).tolist()


def _rolling_peak(samples: list[float], window_samples: int) -> list[float]:
    """Compute rolling peak over a window (hop = window // 2).

    Vectorized alongside ``_rolling_rms`` (see its docstring). Max-of-window
    is exact regardless of reduction order, so unlike ``_rolling_rms`` this
    one IS bit-exact with the old loop for the same list input.
    """
    if samples is None or window_samples <= 0:
        return []
    arr = np.abs(np.asarray(samples, dtype=np.float64))
    if arr.size == 0 or arr.size < window_samples:
        return []
    hop = max(1, window_samples // 2)
    windows = sliding_window_view(arr, window_samples)[::hop]
    return np.max(windows, axis=1).tolist()


def _crest_factor_series(samples: list[float], sample_rate: int, window_seconds: float = 1.0) -> list[float]:
    """Compute rolling crest factor (peak/RMS in dB) over 1-second windows."""
    ws = max(256, int(sample_rate * window_seconds))
    peaks = _rolling_peak(samples, ws)
    rmss = _rolling_rms(samples, ws)
    crest = []
    for p, r in zip(peaks, rmss):
        if r > 1e-9:
            crest.append(20 * math.log10(p / r))
        else:
            crest.append(0.0)
    return crest


def _envelope_attack_slope(samples: list[float], sample_rate: int) -> float:
    """Estimate the steepest transient attack slope in dB/ms.

    Looks at the absolute envelope and measures the fastest rise.

    Vectorized 2026-08-01 (was an O(n*w) nested Python loop -- for every
    sample it re-summed a ~0.5ms window from scratch, ~9M x ~23 scalar adds
    on a full mixdown). The envelope has a growing-then-fixed window
    (average of ``abs_s[max(0, i-smooth_len):i+1]``: expands from 1 sample
    at i=0 up to a fixed ``smooth_len+1``-wide window once i >= smooth_len),
    so it's reproduced here as two pieces rather than one convolution: a
    short (``smooth_len``-sample) cumulative-sum ramp for the leading edge,
    then ``sliding_window_view`` + ``mean`` for the fixed-width steady
    state -- each fixed window's mean is computed directly from its own
    elements (like the original per-window ``sum()``), not via a running
    cumsum difference, to avoid the catastrophic-cancellation precision
    loss a global-cumsum-diff trick would introduce on a long track (window
    is ~23 samples on top of a cumulative sum that can run into the
    millions). NOT bit-exact vs. the old loop (summation order still
    differs slightly) -- see test_reference_matching_vectorized.py for the
    numerical-equivalence tolerance and rationale.
    """
    if samples is None or sample_rate <= 0:
        return 0.0
    arr = np.abs(np.asarray(samples, dtype=np.float64))
    n = arr.size
    if n == 0:
        return 0.0

    # Small smoothing window (~0.5ms)
    smooth_len = max(1, int(sample_rate * 0.0005))
    smoothed = np.empty(n, dtype=np.float64)

    ramp_n = min(smooth_len, n)
    ramp_csum = np.cumsum(arr[:ramp_n])
    smoothed[:ramp_n] = ramp_csum / np.arange(1, ramp_n + 1, dtype=np.float64)

    if n > smooth_len:
        win = smooth_len + 1
        windows = sliding_window_view(arr, win)
        smoothed[smooth_len:] = windows.mean(axis=1)

    # Check slopes over 1ms windows
    step_samples = max(1, int(sample_rate * 0.001))
    if n <= step_samples:
        return 0.0
    v_now = smoothed[step_samples:]
    v_prev = smoothed[:-step_samples]
    mask = (v_prev > 1e-9) & (v_now > v_prev)
    if not np.any(mask):
        return 0.0
    db_rise = 20.0 * np.log10(v_now[mask] / v_prev[mask])  # dB per ms (since step = 1ms)
    return round(float(np.max(db_rise)), 2)


def dynamics_comparison(
    mix_samples: list[float],
    ref_samples: list[float],
    sample_rate: int,
) -> dict:
    """Compare temporal dynamics between user mix and reference track.

    Returns:
      - ``mix_crest_avg``, ``ref_crest_avg``: average crest factor in dB
      - ``crest_delta``: difference (mix - ref), positive means mix is more dynamic
      - ``mix_attack_slope``, ``ref_attack_slope``: transient steepness in dB/ms
      - ``suggested_settings``: dict with recommended compressor attack, release, ratio
      - ``advice``: list of human-readable dynamics matching recommendations
    """
    mix_crest = _crest_factor_series(mix_samples, sample_rate)
    ref_crest = _crest_factor_series(ref_samples, sample_rate)

    mix_avg = sum(mix_crest) / max(len(mix_crest), 1)
    ref_avg = sum(ref_crest) / max(len(ref_crest), 1)
    delta = mix_avg - ref_avg

    mix_slope = _envelope_attack_slope(mix_samples, sample_rate)
    ref_slope = _envelope_attack_slope(ref_samples, sample_rate)

    # Suggest compression settings to match reference dynamics
    settings = _suggest_compressor_settings(delta, mix_slope, ref_slope, mix_avg)

    advice = _dynamics_advice(delta, mix_avg, ref_avg, mix_slope, ref_slope, settings)

    return {
        "mix_crest_avg_db": round(mix_avg, 2),
        "ref_crest_avg_db": round(ref_avg, 2),
        "crest_delta_db": round(delta, 2),
        "mix_attack_slope_db_per_ms": mix_slope,
        "ref_attack_slope_db_per_ms": ref_slope,
        "suggested_settings": settings,
        "advice": advice,
    }


def _suggest_compressor_settings(
    crest_delta: float,
    mix_slope: float,
    ref_slope: float,
    mix_crest: float,
) -> dict:
    """Map dynamics delta to suggested compressor attack/release/ratio."""

    # Attack: faster attack for spikier transients, slower to preserve them
    if mix_slope > ref_slope * 1.5:
        # Mix has much sharper transients → faster attack to tame them
        attack_ms = max(0.1, min(10.0, 5.0 / max(mix_slope / max(ref_slope, 0.1), 1.0)))
    elif mix_slope < ref_slope * 0.5:
        # Mix transients are already soft → slow attack to preserve what's there
        attack_ms = 30.0
    else:
        attack_ms = 10.0

    # Release: match the groove / ring-out of the reference
    if crest_delta > 6.0:
        # Mix is much more dynamic → medium-fast release for consistent level
        release_ms = 100.0
    elif crest_delta > 3.0:
        release_ms = 150.0
    elif crest_delta > 0.0:
        release_ms = 200.0
    else:
        # Mix is already less dynamic than ref → long release or no compression
        release_ms = 300.0

    # Ratio: proportional to how much dynamic range needs reduction
    if crest_delta > 6.0:
        ratio = 4.0
    elif crest_delta > 3.0:
        ratio = 3.0
    elif crest_delta > 1.5:
        ratio = 2.0
    elif crest_delta > 0.0:
        ratio = 1.5
    else:
        ratio = 1.0  # No compression needed

    # Threshold: aim to catch the peaks above the reference's average dynamic range
    # Rough heuristic: set threshold so the compressor engages on the loudest ~30% of content
    threshold_db = round(-18.0 + max(0.0, crest_delta) * -0.5, 1)

    return {
        "attack_ms": round(attack_ms, 1),
        "release_ms": round(release_ms, 1),
        "ratio": round(ratio, 1),
        "threshold_db": threshold_db,
        "makeup_gain_db": round(max(0.0, crest_delta * 0.3), 1),
    }


def _dynamics_advice(
    delta: float,
    mix_crest: float,
    ref_crest: float,
    mix_slope: float,
    ref_slope: float,
    settings: dict,
) -> list[str]:
    """Generate human-readable dynamics matching advice."""
    advice = []

    if abs(delta) < 1.5:
        advice.append(
            f"Your dynamic range (crest factor: {mix_crest:.1f} dB) closely matches "
            f"the reference ({ref_crest:.1f} dB). No significant compression changes needed."
        )
        return advice

    if delta > 0:
        advice.append(
            f"Your mix has {delta:.1f} dB more dynamic range than the reference "
            f"(mix: {mix_crest:.1f} dB, ref: {ref_crest:.1f} dB). Apply gentle "
            f"bus compression to bring the dynamics closer."
        )
    else:
        advice.append(
            f"Your mix is {abs(delta):.1f} dB less dynamic than the reference "
            f"(mix: {mix_crest:.1f} dB, ref: {ref_crest:.1f} dB). Consider using "
            f"less compression or adding parallel compression to restore dynamics."
        )

    if delta > 0 and settings.get("ratio", 1.0) > 1.0:
        advice.append(
            f"Suggested compressor settings: Attack {settings['attack_ms']} ms, "
            f"Release {settings['release_ms']} ms, Ratio {settings['ratio']}:1, "
            f"Threshold {settings['threshold_db']} dBFS."
        )

    if mix_slope > ref_slope * 1.5:
        advice.append(
            f"Your transients are significantly sharper ({mix_slope:.1f} dB/ms) "
            f"than the reference ({ref_slope:.1f} dB/ms). A fast attack "
            f"({settings['attack_ms']} ms) will tame the spikes while preserving feel."
        )
    elif mix_slope < ref_slope * 0.5 and ref_slope > 0.5:
        advice.append(
            f"Your transients are softer ({mix_slope:.1f} dB/ms) than the reference "
            f"({ref_slope:.1f} dB/ms). Consider using a transient shaper to add "
            f"punch, or check if excessive limiting is flattening your attacks."
        )

    return advice


def generate_compressor_preset_xml(settings: dict) -> str:
    """Create Ableton Compressor XML preset from suggested dynamics settings."""
    root = ET.Element("Ableton", MajorVersion="5", MinorVersion="12.0_394", Creator="Ableton Live 11")
    comp = ET.SubElement(root, "Compressor2")

    ET.SubElement(comp, "On", Value="true")
    ET.SubElement(comp, "IsExpanded", Value="true")

    # Map our settings to Ableton Compressor parameters
    ET.SubElement(comp, "Threshold", Value=str(settings.get("threshold_db", -18.0)))
    ET.SubElement(comp, "Ratio", Value=str(settings.get("ratio", 2.0)))

    # Ableton Compressor attack range: 0.01ms to 1000ms (log-scaled)
    ET.SubElement(comp, "Attack", Value=str(settings.get("attack_ms", 10.0)))
    ET.SubElement(comp, "Release", Value=str(settings.get("release_ms", 200.0)))

    # Auto release off for precise control
    ET.SubElement(comp, "AutoRelease", Value="false")

    # Output gain (makeup)
    ET.SubElement(comp, "OutputGain", Value=str(settings.get("makeup_gain_db", 0.0)))

    # Dry/Wet at 100% (full processing)
    ET.SubElement(comp, "DryWet", Value="1.0")

    # Knee: soft knee for gentle compression
    ET.SubElement(comp, "Knee", Value="0.5")

    # Peak mode for transient-sensitive detection
    ET.SubElement(comp, "Model", Value="0")

    # Sidechain: off
    ET.SubElement(comp, "SideChain", Value="false")

    try:
        ET.indent(root, space="  ")
    except AttributeError:
        pass

    xml_str = ET.tostring(root, encoding="utf-8").decode("utf-8")
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_str}'


def export_compressor_preset_adv(settings: dict) -> bytes:
    """Generate the Compressor preset XML and return compressed GZIP bytes (.adv)."""
    xml_str = generate_compressor_preset_xml(settings)
    return gzip.compress(xml_str.encode("utf-8"))


def stereo_image_comparison(mix_metrics: dict, ref_metrics: dict) -> dict:
    """Compare stereo width, balance, and phase correlation against a reference.

    M8.1 — Stereo-Image Reference Matching.

    Args:
        mix_metrics: Metrics dict from the user's mix review (from analyze_wav).
        ref_metrics: Metrics dict from the reference track.

    Returns a dict with:
        width_delta            — mix width_ratio minus ref width_ratio
        balance_delta          — mix L/R balance minus ref balance
        correlation_delta      — mix stereo_correlation minus ref stereo_correlation
        width_correction_db    — suggested gain adjustment for M/S processing
        mono_safety            — True if ref is mono-safe and mix is not (risk flag)
        advice                 — list of human-readable recommendations
    """
    def _f(metrics: dict, key: str, fallback: float = 0.0) -> float:
        try:
            return float(metrics.get(key) or fallback)
        except (TypeError, ValueError):
            return fallback

    mix_width = _f(mix_metrics, "stereo_width_ratio", 0.5)
    ref_width = _f(ref_metrics, "stereo_width_ratio", 0.5)
    mix_balance = _f(mix_metrics, "stereo_balance", 1.0)
    ref_balance = _f(ref_metrics, "stereo_balance", 1.0)
    mix_corr = _f(mix_metrics, "stereo_correlation", 1.0)
    ref_corr = _f(ref_metrics, "stereo_correlation", 1.0)

    width_delta = round(mix_width - ref_width, 3)
    balance_delta = round(mix_balance - ref_balance, 3)
    corr_delta = round(mix_corr - ref_corr, 3)

    # Suggested M/S width correction in dB (simple linear approximation)
    # Positive = boost side; negative = reduce side
    width_correction_db = round(-width_delta * 6.0, 1)  # ±1.0 width → ±6 dB side
    width_correction_db = max(-6.0, min(6.0, width_correction_db))

    # Mono safety flag: ref is mono-compatible but mix is not
    mono_safety = ref_corr >= 0.7 and mix_corr < 0.5

    advice: list[str] = []
    if abs(width_delta) > 0.15:
        direction = "narrower" if width_delta > 0 else "wider"
        advice.append(
            f"Mix is {abs(width_delta):.2f} wider than the reference. "
            f"Consider making the mid/side balance {direction} by adjusting stereo widening or reverb sends."
        )
    if abs(balance_delta) > 0.1:
        side = "right-heavy" if balance_delta > 0 else "left-heavy"
        advice.append(f"Mix is {side} compared with the reference (L/R balance delta {balance_delta:+.2f}).")
    if mono_safety:
        advice.append(
            "Mono risk: the reference is mono-compatible (correlation ≥ 0.7) but your mix is not "
            "(correlation < 0.5). Check bass and lead content for phase cancellation."
        )
    if not advice:
        advice.append("Stereo image is well-matched to the reference.")

    return {
        "width_delta": width_delta,
        "balance_delta": balance_delta,
        "correlation_delta": corr_delta,
        "width_correction_db": width_correction_db,
        "mono_safety": mono_safety,
        "advice": advice,
    }
