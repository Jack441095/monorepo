#!/usr/bin/env python3
"""Shared spectrum-comparison plotting logic, factored out of
plot_spectrum_comparisons.py so both that standalone script and
automix_local.py's optional end-of-render chart can call the same code
without duplicating it.

Averaged spectrum (Welch PSD, 8192-sample Hann windows, 50% overlap),
mid/side split, +3dB/octave tilt so a pink-noise-balanced signal plots flat
(matches the convention Jack asked for on the original stranger-vs-reference
chart).

Kept out of the core audio_analysis package deliberately -- matplotlib is not
a declared runtime dependency of the production mixdown pipeline
(mix_delivery.py's HTML report has no chart dependency), so this stays
eval-tier/dev-only tooling, imported lazily and best-effort by anything that
calls it.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np


def _welch_db(signal: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray]:
    from scipy.signal import welch

    if len(signal) < 8192:
        nperseg = max(256, 1 << (len(signal).bit_length() - 1))
    else:
        nperseg = 8192
    freqs, psd = welch(signal, fs=sr, window="hann", nperseg=nperseg, noverlap=nperseg // 2)
    psd = np.maximum(psd, 1e-16)
    return freqs, 10.0 * np.log10(psd)


def _tilt_correction_db(freqs: np.ndarray) -> np.ndarray:
    """+3dB/octave tilt (relative to 1kHz) so a pink-noise-balanced signal
    plots as a flat line."""
    freqs_safe = np.maximum(freqs, 1.0)
    octaves_from_1k = np.log2(freqs_safe / 1000.0)
    return 3.0 * octaves_from_1k


def render_mid_side_spectrum_comparison(
    *,
    mix_left: np.ndarray,
    mix_right: np.ndarray,
    mix_sr: int,
    ref_left: np.ndarray,
    ref_right: np.ndarray,
    ref_sr: int,
    mix_label: str,
    ref_label: str,
    output_path: Path,
) -> Path:
    """Render a mid/side, +3dB/octave-tilted averaged-spectrum comparison PNG
    and save it to ``output_path``. Requires matplotlib + scipy; raises
    ImportError if unavailable, letting the caller decide whether that's
    fatal (a standalone eval script) or best-effort/skippable (a render
    pipeline hook)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    mix_left = np.asarray(mix_left, dtype=np.float64)
    mix_right = np.asarray(mix_right, dtype=np.float64)
    ref_left = np.asarray(ref_left, dtype=np.float64)
    ref_right = np.asarray(ref_right, dtype=np.float64)

    mix_mid = 0.5 * (mix_left + mix_right)
    mix_side = 0.5 * (mix_left - mix_right)
    ref_mid = 0.5 * (ref_left + ref_right)
    ref_side = 0.5 * (ref_left - ref_right)

    fig, axes = plt.subplots(2, 1, figsize=(11, 8), sharex=True)

    for ax, mix_sig, ref_sig, title in (
        (axes[0], mix_mid, ref_mid, "Mid (M)"),
        (axes[1], mix_side, ref_side, "Side (S)"),
    ):
        f_mix, db_mix = _welch_db(mix_sig, mix_sr)
        f_ref, db_ref = _welch_db(ref_sig, ref_sr)
        db_mix_tilted = db_mix + _tilt_correction_db(f_mix)
        db_ref_tilted = db_ref + _tilt_correction_db(f_ref)

        ax.semilogx(f_mix, db_mix_tilted, label=mix_label, color="#1f77b4", linewidth=1.4)
        ax.semilogx(f_ref, db_ref_tilted, label=ref_label, color="#d62728", linewidth=1.4, alpha=0.85)
        ax.set_xlim(30, 20000)
        ax.set_ylabel("Level (dB, +3dB/oct tilt)")
        ax.set_title(title)
        ax.grid(True, which="both", alpha=0.25)
        ax.legend(loc="lower left", fontsize=9)

    axes[1].set_xlabel("Frequency (Hz)")
    fig.suptitle(f"{mix_label} vs {ref_label} -- averaged spectrum, mid/side, +3dB/oct tilt", fontsize=12)
    fig.tight_layout()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=140)
    plt.close(fig)
    return output_path
