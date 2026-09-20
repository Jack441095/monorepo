"""Interaction metrics and candidate evaluation.

Interaction convention: interaction_db = 10log10(||a+b||^2 / (||a||^2+||b||^2))
    0 dB   -> orthogonal / non-interacting
    < 0 dB -> cancellation
    > 0 dB -> reinforcement
"""
from __future__ import annotations

import numpy as np

from . import methods as M

EPS = 1e-12


def sps_windows_tukey(n: int, alpha: float = 0.5) -> np.ndarray:
    from scipy import signal as _sps
    return _sps.windows.tukey(n, alpha=alpha)


def apply_alignment(b: np.ndarray, delay_samples: float, fs: int,
                    polarity: int = 1) -> np.ndarray:
    """Shift B by -delay (advancing it when delay>0) and flip polarity."""
    d = -float(delay_samples)
    if abs(d) < 1e-9:
        y = b.astype(np.float64).copy()
    else:
        pad = len(b) + int(abs(np.ceil(abs(d)))) + 64
        B = np.fft.rfft(b, n=pad)
        f = np.fft.rfftfreq(pad, d=1.0 / fs)
        y = np.fft.irfft(B * np.exp(-2j * np.pi * f * d / fs), n=pad)[: len(b)]
    return polarity * y


def band_interactions(a, b, fs, bands=None):
    bands = bands or M.DEFAULT_BANDS
    out = {}
    for name, lo, hi in bands:
        fa = M.band_filter(a, fs, lo, hi)
        fb = M.band_filter(b, fs, lo, hi)
        ea, eb = float(np.sum(fa ** 2)), float(np.sum(fb ** 2))
        if ea < 1e-10 and eb < 1e-10:
            out[name] = None
            continue
        e_sum = float(np.sum((fa + fb) ** 2))
        out[name] = float(10 * np.log10((e_sum + EPS) / (ea + eb + EPS)))
    return out


def summary_metrics(a, b):
    s = a + b
    peak = float(np.max(np.abs(s)) + EPS)
    rms = float(np.sqrt(np.mean(s ** 2)) + EPS)
    crest = peak / rms
    return {"peak": peak, "rms": rms, "crest": float(crest)}


def low_energy_db(x, fs, f_lo=20, f_hi=120):
    xb = M.band_filter(x, fs, f_lo, f_hi)
    return float(10 * np.log10(float(np.sum(xb ** 2)) + EPS))


def candidate_score(a, b, fs, delay: float, polarity: int,
                    weights=None) -> dict:
    """Evaluate one alignment hypothesis.

    Objective components (higher better):
      sub_gain_db     low-band summation gain vs unity-sum reference
      bass_gain_db    same for bass band
      bb_gain_db      broadband sum energy vs unity-sum reference
      peak_ratio      summed peak after / before (>=1 means louder peaks)
      crest_delta     crest factor after - before (dB-ish ratio)
    """
    weights = weights or {"sub": 3.0, "bass": 2.0, "bb": 1.0}
    y = apply_alignment(b, delay, fs, polarity)

    def gains(x, yy):
        out = {}
        for nm, lo, hi in (("sub", 20, 120), ("bass", 120, 250),
                           ("bb", 20, min(16000, fs * 0.45))):
            xa = M.band_filter(x, fs, lo, hi)
            xb_ = M.band_filter(yy, fs, lo, hi)
            xs = M.band_filter(x + yy, fs, lo, hi)
            e_ind = float(np.sum(xa ** 2) + np.sum(xb_ ** 2)) + EPS
            out[nm] = float(10 * np.log10(float(np.sum(xs ** 2)) / e_ind + EPS))
        return out

    g_before = gains(a, b)
    g_after = gains(a, y)
    m_before = summary_metrics(a, b)
    m_after = summary_metrics(a, y)
    J = (weights["sub"] * g_after["sub"] + weights["bass"] * g_after["bass"]
         + weights["bb"] * g_after["bb"])
    J_before = (weights["sub"] * g_before["sub"]
                + weights["bass"] * g_before["bass"]
                + weights["bb"] * g_before["bb"])
    return {
        "J": float(J),
        "J_identity": float(J_before),
        "improvement": float(J - J_before),
        "sub_gain_db": g_after["sub"], "bass_gain_db": g_after["bass"],
        "bb_gain_db": g_after["bb"],
        "peak_ratio": float(m_after["peak"] / m_before["peak"]),
        "crest_delta": float(m_after["crest"] / m_before["crest"]),
        "delay": float(delay), "polarity": int(polarity),
    }


def _shift(x: np.ndarray, d: int) -> np.ndarray:
    """Delay x by d samples (positive d delays) with zero fill."""
    if d == 0:
        return x
    out = np.zeros_like(x)
    if d > 0:
        out[d:] = x[: len(x) - d]
    else:
        out[: len(x) + d] = x[-d:]
    return out


def _frac_shift(x: np.ndarray, d: float, fs: int) -> np.ndarray:
    """Exact fractional advance (d>0 advances) via spectral phase ramp."""
    if abs(d) < 1e-9:
        return x.copy()
    n = len(x)
    pad = 1 << int(np.ceil(np.log2(n + int(abs(np.ceil(d))) + 64)))
    X = np.fft.rfft(x, n=pad)
    f = np.fft.rfftfreq(pad, d=1.0 / fs)
    # advance by d  <=>  delay by -d
    return np.fft.irfft(X * np.exp(2j * np.pi * f * d / fs), pad)[:n]


def fast_search(a, b, fs, max_lag: int, coarse_step: int = 2,
                d_prior: float | None = None, prior_weight: float = 0.05,
                max_dev: int = 10,
                bands=((20, 120, 3.0), (120, 250, 2.0),
                       (20, None, 1.0))) -> dict:
    """Estimate-then-verify search over {delay, fractional refine, polarity}.

    Research finding: pure energy objectives are nearly flat in delay for
    LF material (a 40-sample error at 60 Hz is <1 radian), so they cannot
    own fine timing. Time-domain correlation owns the delay estimate;
    this search VERIFIES it against interaction metrics inside a bounded
    window (d_prior +/- max_dev), chooses polarity, refines fractionally
    and produces trade-off measurements:
        J(d) = J_energy(d) - prior_weight * (d - d_prior)^2

    Peak/crest trade-off metrics are measured ONCE on the winning
    candidate (measuring them inside the loop cost ~40 full-length FFT
    shifts per search for identical results).
    """
    if d_prior is None:
        d_prior = 0.0
    fa, fb = {}, {}
    taper = sps_windows_tukey(len(a), alpha=0.06)
    for i, (lo, hi, _) in enumerate(bands):
        hi_eff = hi or min(16000, fs * 0.45)
        # Tukey taper removes filter boundary transients that otherwise
        # dominate shifted sums and bias the energy objective (measured:
        # ~+15 sample bias without it)
        fa[i] = M.band_filter(a, fs, lo, hi_eff) * taper
        fb[i] = M.band_filter(b, fs, lo, hi_eff) * taper

    def objective(d: float, pol: int):
        # candidate d means "B lags A by d"; the fix advances B by d
        di = int(round(d))
        J, parts = 0.0, {}
        for i, (lo, hi, w) in enumerate(bands):
            s = fa[i] + pol * _shift(fb[i], -di)
            e_ind = float(np.sum(fa[i] ** 2) + np.sum(fb[i] ** 2)) + EPS
            g = float(10 * np.log10(float(np.sum(s ** 2)) / e_ind + EPS))
            parts[f"band{i}_gain_db"] = g
            J += w * g
        return J, parts

    def aux_metrics(d: float, pol: int):
        y_fix = pol * apply_alignment(b, d, fs, 1)
        peak_ratio = float(np.max(np.abs(a + y_fix)) /
                           (np.max(np.abs(a + b)) + EPS))
        crest_after = summary_metrics(a, y_fix)["crest"]
        crest_before = summary_metrics(a, b)["crest"]
        return {"peak_ratio": peak_ratio,
                "crest_delta": float(crest_after / crest_before)}

    best = None
    d0 = int(round(d_prior))
    lo_d, hi_d = max(-max_lag, d0 - max_dev), min(max_lag, d0 + max_dev)
    for pol in (1, -1):
        for d in range(lo_d, hi_d + 1, coarse_step):
            J, parts = objective(d, pol)
            Jr = J - prior_weight * (d - d_prior) ** 2
            if best is None or Jr > best[0]:
                best = (Jr, d, pol, parts)
    # ensure the prior itself is evaluated
    for pol in (1, -1):
        J, parts = objective(d0, pol)
        if best is None or J > best[0]:
            best = (J, d0, pol, parts)
    # fractional refinement (quarter-sample) around best integer
    Jb, db, pb, partsb = best
    for df in np.arange(db - coarse_step, db + coarse_step + 0.26, 0.25):
        if abs(df - round(df)) < 1e-9:
            continue
        J = 0.0
        for i, (lo, hi, w) in enumerate(bands):
            # fractional shift of the PREFILTERED band (commutes with LTI)
            s = fa[i] + pb * _frac_shift(fb[i], df, fs)
            e_ind = float(np.sum(fa[i] ** 2) + float(np.sum(fb[i] ** 2))) + EPS
            J += w * float(10 * np.log10(float(np.sum(s ** 2)) / e_ind + EPS))
        Jr = J - prior_weight * (df - d_prior) ** 2
        if Jr > Jb:
            Jb, db, pb, partsb = Jr, float(df), pb, partsb

    auxb = aux_metrics(db, pb)
    J_id, parts_id = objective(0, 1)
    aux_id = aux_metrics(0.0, 1)
    raw_energy = Jb + prior_weight * (db - d_prior) ** 2

    return {
        "J": float(Jb), "J_energy": float(raw_energy),
        "identity_J": float(J_id),
        "improvement_over_identity": float(raw_energy - J_id),
        "d_prior": float(d_prior),
        "delay_samples": float(db), "polarity": int(pb),
        "band_gains": partsb,
        "band_energy_ratio": {
            f"band{i}": float(max(float(np.sum(fa[i] ** 2)),
                                  float(np.sum(fb[i] ** 2))) /
                              (max(float(np.sum(fa[2] ** 2)),
                                   float(np.sum(fb[2] ** 2))) + EPS))
            for i in range(len(bands))},
        "peak_ratio": auxb["peak_ratio"],
        "crest_delta": auxb["crest_delta"],
        "identity_peak_ratio": aux_id["peak_ratio"],
    }
