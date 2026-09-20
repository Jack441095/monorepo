"""40-Band Logarithmic LTAS Spectrum Matcher module for AutoMix.

Computes 40-band logarithmic spectrum (20 Hz - 20 kHz) and generates
corrective master EQ bands to match commercial reference genre profiles.
"""

from __future__ import annotations

import math
import numpy as np


# 40 Logarithmic Frequency Band Centers (20 Hz to 20 kHz)
LOG_BANDS_40_HZ = np.logspace(np.log10(20.0), np.log10(20000.0), num=40)

# Commercial Target Spectrum Energy Profiles (normalized dB energy relative to 1 kHz)
GENRE_LTAS_PROFILES = {
    "pop": {
        "sub": +1.5,       # 20-60 Hz
        "bass": +1.0,      # 60-250 Hz
        "low_mids": -0.5,  # 250-1000 Hz
        "high_mids": +0.5, # 1-4 kHz
        "presence": +1.2,  # 4-8 kHz
        "air": +1.5,       # 8-20 kHz
    },
    "edm": {
        "sub": +3.0,
        "bass": +2.5,
        "low_mids": -1.0,
        "high_mids": +0.0,
        "presence": +1.5,
        "air": +2.0,
    },
    "hiphop": {
        "sub": +4.0,
        "bass": +3.0,
        "low_mids": -1.5,
        "high_mids": -0.5,
        "presence": +0.5,
        "air": +1.0,
    },
    "rock": {
        "sub": -0.5,
        "bass": +1.0,
        "low_mids": +0.5,
        "high_mids": +1.5,
        "presence": +1.0,
        "air": +0.5,
    },
    "acoustic": {
        "sub": -2.0,
        "bass": +0.0,
        "low_mids": +0.0,
        "high_mids": +0.5,
        "presence": +0.5,
        "air": +0.5,
    },
}


def calculate_40_band_ltas(
    samples: np.ndarray | list[float],
    sample_rate: int = 44100,
) -> list[float]:
    """Computes a 40-band logarithmic Long-Term Average Spectrum (LTAS) in dB.

    Parameters
    ----------
    samples : np.ndarray or list[float]
        Audio samples (mono).
    sample_rate : int
        Sample rate in Hz.

    Returns
    -------
    list[float]
        40 float values representing normalized energy in dB per logarithmic band.
    """
    if len(samples) == 0:
        return [0.0] * 40
    # Slice BEFORE converting to array -- the FFT below only ever uses the
    # first 131072 samples (~3s at 44.1kHz), so converting a multi-minute
    # track's full sample list to float64 first (then immediately
    # discarding all but the first ~3s of it) wasted ~65% of this
    # function's own runtime on a real 205s track (measured: 0.255s of
    # 0.392s total). Slicing a list/ndarray is O(slice length) either way;
    # only the array *conversion* cost scales with the full track length.
    arr = np.asarray(samples[: min(len(samples), 131072)], dtype=np.float64)

    # Compute FFT Magnitude Spectrum
    n_fft = 4096
    fft_mag = np.abs(np.fft.rfft(arr, n=n_fft))
    freqs = np.fft.rfftfreq(n_fft, d=1.0 / sample_rate)

    band_energies = []
    edges = np.logspace(np.log10(20.0), np.log10(20000.0), num=41)

    for i in range(40):
        low_f = edges[i]
        high_f = edges[i + 1]
        idx = np.where((freqs >= low_f) & (freqs < high_f))[0]
        if len(idx) > 0:
            power = np.mean(fft_mag[idx] ** 2)
            db_val = 10.0 * math.log10(max(1e-12, power))
        else:
            db_val = -60.0
        band_energies.append(db_val)

    # Normalize relative to 1 kHz band (index ~20)
    ref_db = band_energies[20] if len(band_energies) > 20 else -30.0
    norm_bands = [float(b - ref_db) for b in band_energies]
    return norm_bands


_LTAS_REGIONS = (
    (list(range(0, 8)), "sub"),
    (list(range(8, 16)), "bass"),
    (list(range(16, 24)), "low_mids"),
    (list(range(24, 32)), "high_mids"),
    (list(range(32, 40)), "air"),
)


def expand_genre_profile_to_40_bands(genre: str) -> list[float]:
    """The same GENRE_LTAS_PROFILES target generate_ltas_match_eq_bands()
    falls back to, expanded to a 40-band step curve (each band takes its
    region's flat target dB value) so it can be plotted alongside a real
    measured 40-band LTAS on the same dB-relative-to-1kHz scale.

    This is a hand-tuned estimate, not a measurement -- prefer
    reference_target_40_band_ltas() against a real reference-track
    directory when one is available (see automix_worker.py's
    default_reference_dir/_GENRE_REFERENCE_FOLDER). Kept as the fallback
    for genres with no curated reference folder.
    """
    profile = GENRE_LTAS_PROFILES.get(genre.lower(), GENRE_LTAS_PROFILES["pop"])
    bands = [0.0] * 40
    for band_indices, target_key in _LTAS_REGIONS:
        for i in band_indices:
            bands[i] = float(profile[target_key])
    return bands


def reference_target_40_band_ltas(reference_dir) -> list[float] | None:
    """A real 40-band LTAS target built from actual reference tracks,
    instead of the hand-tuned GENRE_LTAS_PROFILES estimate above.

    Computes calculate_40_band_ltas() for every audio file in
    reference_dir and returns the per-band MEDIAN (robust to one outlier
    track skewing a single band, same reasoning as
    spectral_match.py's reference_target_40band -- this is the dB-LTAS
    counterpart of that function, kept on the same scale as
    calculate_40_band_ltas() so it's directly comparable to a measured
    mix without a unit conversion). Returns None if reference_dir has no
    usable audio files.
    """
    from pathlib import Path
    from audio_analysis.utils.audio_io import read_wav_mono, decode_audio_bytes
    from audio_analysis.mixdown.spectral_match import AUDIO_SUFFIXES

    p = Path(reference_dir)
    if not p.is_dir():
        return None
    files = sorted(f for f in p.iterdir() if f.is_file() and f.suffix.lower() in AUDIO_SUFFIXES)

    band_rows = []
    for f in files:
        try:
            wav_bytes = decode_audio_bytes(f.read_bytes(), f.name)["wav_bytes"]
            decoded = read_wav_mono(wav_bytes, max_samples=0)
            band_rows.append(calculate_40_band_ltas(decoded["samples"], int(decoded["sample_rate"])))
        except Exception:
            continue
    if not band_rows:
        return None

    stacked = np.asarray(band_rows, dtype=np.float64)
    median = np.median(stacked, axis=0) if stacked.shape[0] >= 2 else stacked[0]
    return [float(v) for v in median]


def generate_ltas_match_eq_bands(
    measured_40_bands: list[float],
    genre: str = "pop",
    ref_40_bands: list[float] | None = None,
    max_boost_db: float = 3.0,
    max_cut_db: float = -3.0,
) -> list[dict]:
    """Generates master EQ correction bands to match a measured LTAS to a target.

    Parameters
    ----------
    measured_40_bands : list[float]
        40-band LTAS in dB.
    genre : str
        Target genre profile ('pop', 'edm', 'hiphop', 'rock', 'acoustic') --
        used for the hand-tuned GENRE_LTAS_PROFILES fallback and in each
        band's "reason" text.
    ref_40_bands : list[float], optional
        A real 40-band LTAS target (e.g. from reference_target_40_band_ltas()
        against actual reference tracks) to correct toward instead of the
        hand-tuned genre profile. Falls back to GENRE_LTAS_PROFILES[genre]
        when not given, preserving every existing caller's behavior.
    max_boost_db : float
        Maximum EQ boost in dB (+3.0 dB).
    max_cut_db : float
        Maximum EQ cut in dB (-3.0 dB).

    Returns
    -------
    list[dict]
        List of ParametricEQ band definitions.
    """
    profile = GENRE_LTAS_PROFILES.get(genre.lower(), GENRE_LTAS_PROFILES["pop"])
    has_real_ref = ref_40_bands is not None and len(ref_40_bands) >= 40
    eq_bands = []

    # Regions to evaluate (frequency, band_indices, target_key, filter_type)
    regions = [
        (60.0, list(range(0, 8)), "sub", "lowshelf"),
        (150.0, list(range(8, 16)), "bass", "peaking"),
        (500.0, list(range(16, 24)), "low_mids", "peaking"),
        (2500.0, list(range(24, 32)), "high_mids", "peaking"),
        (10000.0, list(range(32, 40)), "air", "highshelf"),
    ]

    for center_freq, band_indices, target_key, ftype in regions:
        measured_avg = float(np.mean([measured_40_bands[i] for i in band_indices if i < len(measured_40_bands)]))
        target_val = float(np.mean([ref_40_bands[i] for i in band_indices])) if has_real_ref else profile[target_key]
        diff_db = target_val - measured_avg

        # Only correct if deviation > 1.0 dB
        if abs(diff_db) > 1.0:
            gain = max(max_cut_db, min(max_boost_db, diff_db * 0.5))  # Smooth 50% correction
            eq_bands.append({
                "type": ftype,
                "frequency": float(center_freq),
                "gain_db": round(float(gain), 2),
                "q": 0.707 if "shelf" in ftype else 1.0,
                "reason": (
                    f"40-Band LTAS Match ({genre}, {'real reference tracks' if has_real_ref else 'genre estimate'}): "
                    f"adjusted {target_key} by {gain:+.1f} dB."
                ),
            })

    return eq_bands
