from __future__ import annotations

from cmath import exp, pi
import math

try:
    import numpy as np

    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False


BANDS = [
    ("sub", 20, 60),
    ("bass", 60, 150),
    ("low_mids", 150, 400),
    ("mids", 400, 2000),
    ("presence", 2000, 6000),
    ("sibilance", 6000, 8000),
    ("air", 8000, 16000),
]
PRESENCE_BANDS = {"presence", "sibilance", "air"}


def _fft(values: list[complex]) -> list[complex]:
    n = len(values)
    if n <= 1:
        return values
    even = _fft(values[0::2])
    odd = _fft(values[1::2])
    factors = [exp(-2j * pi * k / n) * odd[k] for k in range(n // 2)]
    return [even[k] + factors[k] for k in range(n // 2)] + [even[k] - factors[k] for k in range(n // 2)]


def a_weighting_gain(frequency: float) -> float:
    """A-weighting gain, used here as a practical Fletcher-Munson-style approximation."""
    if frequency <= 0:
        return 0.0
    f2 = frequency * frequency
    numerator = (12200**2) * (f2 * f2)
    denominator = (
        (f2 + 20.6**2)
        * math.sqrt((f2 + 107.7**2) * (f2 + 737.9**2))
        * (f2 + 12200**2)
    )
    db = (20 * math.log10(max(numerator / denominator, 1e-12))) + 2.0
    return 10 ** (db / 20)


def spectrum_magnitudes(samples, sample_rate: int, *, size: int = 4096) -> tuple[list[float], int]:
    # len()==0 guard (not `not samples`) so a numpy-array caller doesn't hit the
    # ambiguous-truth-value ValueError -- lets the render pass stem arrays straight
    # in (no array->list conversion) with identical results.
    if samples is None or len(samples) == 0 or sample_rate <= 0:
        return [], 0
    n = 1
    while n * 2 <= min(size, len(samples)):
        n *= 2
    if n < 256:
        return [], 0
    start = max(0, (len(samples) - n) // 2)
    window = samples[start : start + n]

    if NUMPY_AVAILABLE:
        try:
            window_np = np.asarray(window, dtype=np.float64)
            hann = np.hanning(n)
            windowed = window_np * hann
            spectrum = np.fft.rfft(windowed)
            return np.abs(spectrum[: n // 2]).tolist(), n
        except Exception:
            pass

    values = [
        complex(sample * (0.5 - 0.5 * math.cos((2 * math.pi * index) / (n - 1))), 0)
        for index, sample in enumerate(window)
    ]
    spectrum = _fft(values)
    return [abs(item) for item in spectrum[: n // 2]], n


def log_interpolate(freq: float, freq_arr: list[float], val_arr: list[float]) -> float:
    """Perform log-frequency linear interpolation for ISO 226 coefficients."""
    if freq <= freq_arr[0]:
        return val_arr[0]
    if freq >= freq_arr[-1]:
        return val_arr[-1]
    for i in range(len(freq_arr) - 1):
        if freq_arr[i] <= freq <= freq_arr[i+1]:
            log_f = math.log(freq)
            log_f0 = math.log(freq_arr[i])
            log_f1 = math.log(freq_arr[i+1])
            frac = (log_f - log_f0) / (log_f1 - log_f0)
            return val_arr[i] + frac * (val_arr[i+1] - val_arr[i])
    return val_arr[-1]


def equal_loudness_contour(frequency_hz: float, phon_level: float = 60.0) -> float:
    """Calculate the sound pressure level (dB SPL) for a given frequency and phon level.

    Based on ISO 226:2003 standard. Valid for 20 Hz <= frequency_hz <= 20000 Hz.
    """
    phon = max(0.0, min(90.0, float(phon_level)))
    freq_arr = [
        20.0, 25.0, 31.5, 40.0, 50.0, 63.0, 80.0, 100.0, 125.0, 160.0, 200.0, 250.0, 315.0,
        400.0, 500.0, 630.0, 800.0, 1000.0, 1250.0, 1600.0, 2000.0, 2500.0, 3150.0, 4000.0,
        5000.0, 6300.0, 8000.0, 10000.0, 12500.0, 20000.0
    ]
    alpha_arr = [
        0.532, 0.506, 0.480, 0.455, 0.432, 0.409, 0.387, 0.367, 0.349, 0.330, 0.315, 0.301,
        0.288, 0.276, 0.267, 0.259, 0.253, 0.250, 0.246, 0.244, 0.243, 0.243, 0.243, 0.242,
        0.242, 0.245, 0.254, 0.271, 0.301, 0.301
    ]
    lu_arr = [
        -31.6, -27.2, -23.0, -19.1, -15.9, -13.0, -10.3, -8.1, -6.2, -4.5, -3.1, -2.0, -1.1,
        -0.4, 0.0, 0.3, 0.5, 0.0, -2.7, -4.1, -1.0, 1.7, 2.5, 1.2, -2.1, -7.1, -11.2, -10.7,
        -3.1, -3.1
    ]
    tf_arr = [
        78.5, 68.7, 59.5, 51.1, 44.0, 37.5, 31.5, 26.5, 22.1, 17.9, 14.4, 11.4, 8.6, 6.2,
        4.4, 3.0, 2.2, 2.4, 3.5, 1.7, -1.3, -4.2, -6.0, -5.4, -1.5, 6.0, 12.6, 13.9, 12.3, 78.5
    ]

    f = max(20.0, min(20000.0, float(frequency_hz)))
    alpha_f = log_interpolate(f, freq_arr, alpha_arr)
    lu_f = log_interpolate(f, freq_arr, lu_arr)
    tf_f = log_interpolate(f, freq_arr, tf_arr)

    a_f = 0.00447 * ((10.0 ** (0.025 * phon)) - 1.15) + (
        (0.4 * (10.0 ** (((tf_f + lu_f) / 10.0) - 9.0))) ** alpha_f
    )
    if a_f <= 0:
        return tf_f
    spl = ((10.0 / alpha_f) * math.log10(a_f)) - lu_f + 94.0
    return spl


def equal_loudness_gain(frequency: float, phon_level: float = 60.0) -> float:
    """Relative perception gain factor based on equal loudness contours.

    If the threshold is high, sensitivity is low (gain is small).
    At 1 kHz, the gain is 1.0 (0 dB).
    """
    if frequency <= 0:
        return 0.0
    spl = equal_loudness_contour(frequency, phon_level)
    gain_db = phon_level - spl
    return 10.0 ** (gain_db / 20.0)


def fletcher_munson_corrected_spectrum(
    magnitudes: list[float], frequencies: list[float], phon_level: float = 60.0
) -> list[float]:
    """Applies ISO 226 equal-loudness contour correction to an FFT magnitude spectrum."""
    return [
        mag * equal_loudness_gain(freq, phon_level)
        for mag, freq in zip(magnitudes, frequencies)
    ]


def band_ratios(
    magnitudes: list[float],
    sample_rate: int,
    n: int,
    *,
    perceptual: bool = False,
    phon_level: float = 60.0,
) -> dict:
    if not magnitudes or sample_rate <= 0 or n <= 0:
        return {}
    weighted = []
    for index, magnitude in enumerate(magnitudes):
        frequency = index * sample_rate / n
        if perceptual:
            weighted.append(magnitude * equal_loudness_gain(frequency, phon_level))
        else:
            weighted.append(magnitude)
    total = sum(weighted) or 1.0
    out: dict[str, float] = {}
    for name, low, high in BANDS:
        low_bin = max(0, int(low * n / sample_rate))
        high_bin = min(len(weighted), max(low_bin + 1, int(high * n / sample_rate)))
        out[name] = round(sum(weighted[low_bin:high_bin]) / total, 4)
    return out


def spectral_bands(samples: list[float], sample_rate: int, *, size: int = 4096) -> dict:
    magnitudes, n = spectrum_magnitudes(samples, sample_rate, size=size)
    return band_ratios(magnitudes, sample_rate, n)


def perceptual_bands(
    samples: list[float], sample_rate: int, *, size: int = 4096, phon_level: float = 60.0
) -> dict:
    magnitudes, n = spectrum_magnitudes(samples, sample_rate, size=size)
    return band_ratios(magnitudes, sample_rate, n, perceptual=True, phon_level=phon_level)


def perceived_loudness_contribution(bands: dict, phon_level: float = 60.0) -> dict:
    """Reports perceived band contribution versus raw energy."""
    out: dict[str, float] = {}
    total_perceived = 0.0
    for name, low, high in BANDS:
        # Approximate center frequency of the band
        center_freq = math.sqrt(low * high)
        gain = equal_loudness_gain(center_freq, phon_level)
        raw_val = bands.get(name, 0.0)
        perceived_val = raw_val * gain
        out[name] = perceived_val
        total_perceived += perceived_val

    total_perceived = total_perceived or 1.0
    for name in out:
        out[name] = round(out[name] / total_perceived, 4)
    return out


def perceptual_summary(perceived: dict, phon_level: float = 60.0) -> dict:
    if not perceived:
        return {
            "dominant_band": "",
            "presence_share": 0.0,
            "low_end_share": 0.0,
            "description": "No perceptual spectrum available.",
        }
    dominant = max(perceived.items(), key=lambda item: item[1])
    presence_share = round(sum(float(perceived.get(name, 0) or 0) for name in PRESENCE_BANDS), 4)
    low_end_share = round(float(perceived.get("sub", 0) or 0) + float(perceived.get("bass", 0) or 0), 4)
    description = f"Fletcher-Munson style weighting (at {int(phon_level)} phon) puts the perceived focus around {dominant[0].replace('_', ' ')}."
    return {
        "dominant_band": dominant[0],
        "presence_share": presence_share,
        "low_end_share": low_end_share,
        "description": description,
    }


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = max(0.0, min(1.0, q)) * (len(ordered) - 1)
    lower = int(math.floor(pos))
    upper = int(math.ceil(pos))
    if lower == upper:
        return ordered[lower]
    weight = pos - lower
    return ordered[lower] + ((ordered[upper] - ordered[lower]) * weight)


def spectral_features(magnitudes: list[float], sample_rate: int, n: int) -> dict:
    if not magnitudes or sample_rate <= 0 or n <= 0:
        return {"centroid_hz": 0, "rolloff_85_hz": 0, "high_frequency_share": 0.0}
    total = sum(magnitudes) or 1.0
    weighted = sum((index * sample_rate / n) * magnitude for index, magnitude in enumerate(magnitudes))
    threshold = total * 0.85
    running = 0.0
    rolloff = 0.0
    for index, magnitude in enumerate(magnitudes):
        running += magnitude
        if running >= threshold:
            rolloff = index * sample_rate / n
            break
    high_start = int(6000 * n / sample_rate)
    high_share = sum(magnitudes[max(0, high_start) :]) / total if high_start < len(magnitudes) else 0.0
    return {
        "centroid_hz": round(weighted / total, 1),
        "rolloff_85_hz": round(rolloff, 1),
        "high_frequency_share": round(high_share, 4),
    }


def log_spaced_boundaries(start_freq: float = 20.0, end_freq: float = 20000.0, num_bands: int = 40) -> list[float]:
    log_start = math.log10(start_freq)
    log_end = math.log10(end_freq)
    step = (log_end - log_start) / num_bands
    return [10 ** (log_start + i * step) for i in range(num_bands + 1)]


def log_band_ratios(
    magnitudes: list[float],
    sample_rate: int,
    n: int,
    num_bands: int = 40,
) -> list[float]:
    """Calculate normalized log-spaced band energy shares (e.g. 40 bands)."""
    if not magnitudes or sample_rate <= 0 or n <= 0:
        return [0.0] * num_bands
    
    boundaries = log_spaced_boundaries(20.0, 20000.0, num_bands)
    bin_bounds = [int(b * n / sample_rate) for b in boundaries]
    bin_bounds = [max(0, min(len(magnitudes), idx)) for idx in bin_bounds]
    
    band_sums = []
    for i in range(num_bands):
        low_idx = bin_bounds[i]
        high_idx = bin_bounds[i+1]
        if low_idx == high_idx and low_idx < len(magnitudes):
            high_idx += 1
        band_sums.append(sum(magnitudes[low_idx:high_idx]))
        
    total = sum(band_sums) or 1.0
    return [round(v / total, 5) for v in band_sums]


def log_band_ratios_track_average(
    samples: list[float],
    sample_rate: int,
    num_bands: int = 40,
    *,
    num_windows: int = 12,
    window_size: int = 4096,
) -> list[float]:
    """Track-wide log-band spectral fingerprint, for genre/reference-track
    matching specifically (analysis_core.genre_profiles.classify_reference_profile).

    ``log_band_ratios()`` on a single ``spectrum_magnitudes()`` call only sees
    one ~93ms window from the temporal midpoint of the track — fine for the
    per-frame metrics it was originally built for, but genre classification
    needs a whole-song fingerprint. A quiet bridge, vocal-only section, or
    breakdown landing on the midpoint produces a wildly unrepresentative
    spectrum (near-zero high-frequency bands are common for a single short
    window, virtually never for a whole song), which was producing 0.0
    confidence "Ambient" results on every real commercial track tested
    (found 2026-07-10 running scripts/eval/validate_style_classifier.py
    against real reference audio for the first time — the classifier had
    only ever been tested against synthetic full-track archetype profiles,
    never a single-frame-derived one).

    Spreads ``num_windows`` FFT windows evenly across the track, sums their
    magnitude spectra (not the ratios — summing raw magnitude before
    normalizing preserves relative loudness across sections correctly,
    matching how a full-track FFT would weight them), then computes one
    ``log_band_ratios()`` pass over the averaged spectrum.
    """
    if samples is None or len(samples) == 0 or sample_rate <= 0:
        return [0.0] * num_bands

    total_samples = len(samples)
    if total_samples < window_size:
        magnitudes, n = spectrum_magnitudes(samples, sample_rate, size=window_size)
        return log_band_ratios(magnitudes, sample_rate, n, num_bands)

    starts = (
        [max(0, (total_samples - window_size) // 2)]
        if num_windows <= 1
        else [
            int(i * (total_samples - window_size) / (num_windows - 1))
            for i in range(num_windows)
        ]
    )

    summed: list[float] | None = None
    fft_n = 0
    for start in starts:
        window = samples[start : start + window_size]
        magnitudes, n = spectrum_magnitudes(window, sample_rate, size=window_size)
        if not magnitudes:
            continue
        fft_n = n
        if summed is None:
            summed = list(magnitudes)
        else:
            # Windows can differ by one FFT-size step if `samples` is short;
            # only combine the overlapping range to stay shape-safe.
            m = min(len(summed), len(magnitudes))
            summed = [summed[i] + magnitudes[i] for i in range(m)]

    if summed is None:
        return [0.0] * num_bands
    return log_band_ratios(summed, sample_rate, fft_n, num_bands)

