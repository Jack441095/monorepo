"""Alignment estimation methods — reference research implementations.

CANONICAL CONVENTION (enforced numerically by src/nla/selftest.py):
    A = reference layer, B = test layer.
    offset_samples > 0  <=>  B lags A, i.e.  b[n] ~= g*a[n - d], d > 0
    ("advance B by offset samples to align").
"""
from __future__ import annotations

import numpy as np
from scipy import signal as sps

EPS = 1e-12


def _prep(x: np.ndarray) -> np.ndarray:
    return sps.detrend(np.asarray(x, dtype=np.float64), type="constant")


# ----------------------------------------------------------------------
# canonical full linear cross-correlation
# ----------------------------------------------------------------------

def xcorr_full(a: np.ndarray, b: np.ndarray):
    """Returns (lag_axis, values) with values[k] = corr score for
    offset = lag_axis[k]; positive offset <=> B lags A.
    Axis is sorted ascending so neighbour indexing is well-defined."""
    a = _prep(a)
    b = _prep(b)
    # scipy: c[j] = sum_v a[v+j]*b[v], j in [-(len(b)-1), len(a)-1]
    c = sps.correlate(a, b, mode="full")
    lag = -np.arange(-(len(b) - 1), len(a))   # positive lag <=> B lags
    order = np.argsort(lag)
    return lag[order], c[order]


def _slice_lags(lag_axis: np.ndarray, vals: np.ndarray, max_lag: int):
    sel = np.abs(lag_axis) <= max_lag
    return lag_axis[sel], vals[sel]


def _parabolic(vals: np.ndarray, k: int) -> float:
    if k <= 0 or k >= len(vals) - 1:
        return 0.0
    y0, y1, y2 = vals[k - 1], vals[k], vals[k + 1]
    denom = y0 - 2 * y1 + y2
    if abs(denom) < EPS:
        return 0.0
    return float(np.clip(0.5 * (y0 - y2) / denom, -1.0, 1.0))


def ambiguity_ratio(vals: np.ndarray, lag_axis: np.ndarray,
                    rel_threshold: float = 0.90) -> float:
    """Ratio of strongest DISTINCT secondary peak to global peak.

    Only local maxima count, and they must lie outside the mainlobe:
    the required separation is 3x the measured mainlobe half-width
    (distance from global peak to its half-power points). This avoids
    false ambiguity on broad-mainlobe transients while catching genuine
    periodic ambiguity (pure tones, ringing drums) where an almost equal
    explanation exists one period away.
    """
    v = np.abs(vals)
    k = int(np.argmax(v))
    g = v[k] + EPS
    # mainlobe half-width at -6 dB (half power)
    half = g / np.sqrt(2)
    left = k
    while left > 0 and v[left] > half:
        left -= 1
    right = k
    while right < len(v) - 1 and v[right] > half:
        right += 1
    lobe_hw = max(right - k, k - left, 4)
    min_sep = 3 * lobe_hw
    # local maxima of |profile|
    loc = np.where((v[1:-1] >= v[:-2]) & (v[1:-1] >= v[2:]))[0] + 1
    if len(loc) == 0:
        return 0.0
    sec = 0.0
    for j in loc:
        if abs(lag_axis[j] - lag_axis[k]) < min_sep:
            continue
        # distinct basin: require a dip below 0.7*min(v[j],g) between peaks
        lo_, hi_ = (min(j, k), max(j, k))
        dip = v[lo_:hi_ + 1].min() if hi_ > lo_ else 0.0
        if dip < 0.7 * min(v[j], g) and v[j] > sec:
            sec = float(v[j])
    return float(sec / g)


# ----------------------------------------------------------------------
# 1. plain energy-normalised cross-correlation
# ----------------------------------------------------------------------

def xcorr_plain(a: np.ndarray, b: np.ndarray, max_lag: int):
    lag_axis, c = xcorr_full(a, b)
    lags, seg = _slice_lags(lag_axis, c, max_lag)
    a = _prep(a)
    b = _prep(b)
    ca = np.concatenate([[0.0], np.cumsum(a ** 2)])
    cb = np.concatenate([[0.0], np.cumsum(b ** 2)])
    na, nb = len(a), len(b)
    lo = np.maximum(0, -lags)
    hi = np.minimum(na, nb - lags)
    ok = (hi - lo) >= 16
    ea = ca[np.maximum(hi, 0)] - ca[np.maximum(lo, 0)]
    eb = cb[np.maximum(hi + lags, 0)] - cb[np.maximum(lo + lags, 0)]
    norm = np.sqrt(np.maximum(ea, 1e-18) * np.maximum(eb, 1e-18))
    vals = np.where(ok, seg / (norm + EPS), 0.0)
    k = int(np.argmax(np.abs(vals)))
    # NOTE: per-lag energy normalisation subtly reshapes the correlation
    # surface (measured bias up to ~1 sample on decaying transients), so
    # fractional refinement runs on the UNNORMALISED profile.
    k_full = int(np.where(lag_axis == lags[k])[0][0])
    frac = _parabolic(c, k_full)
    off = float(lags[k]) + frac
    peak_sign = np.sign(vals[k])
    return {"offset_samples": off,
            "peak_value": float(abs(vals[k])) * peak_sign,
            "abs_peak": float(abs(vals[k])),
            "ambiguity_ratio": ambiguity_ratio(vals, lags),
            "profile": vals, "lag_axis": lags}


# ----------------------------------------------------------------------
# 2. windowed Pearson cross-correlation (transient-centric)
# ----------------------------------------------------------------------

def xcorr_normalized(a: np.ndarray, b: np.ndarray, max_lag: int, win_ms=60.0,
                     fs: int = 48000):
    a = _prep(a)
    b = _prep(b)
    w = int(win_ms * fs / 1000)

    def centre(x):
        e = np.convolve(x ** 2, np.ones(min(len(x), 256)) / min(len(x), 256),
                        mode="same")
        return int(np.argmax(e))

    ca, cb = centre(a), centre(b)
    xa = a[max(0, ca - w // 2): min(len(a), ca + w // 2)]
    xb = b[max(0, cb - w // 2): min(len(b), cb + w // 2)]
    xa -= xa.mean()
    xb -= xb.mean()
    lag_axis, c = xcorr_full(xa, xb)
    lim = min(max_lag, len(xa) - 8, len(xb) - 8)
    lags, seg = _slice_lags(lag_axis, c, lim)
    vals = seg / (np.linalg.norm(xa) * np.linalg.norm(xb) + EPS)
    k = int(np.argmax(np.abs(vals)))
    frac = _parabolic(vals, k)
    return {"offset_samples": float(lags[k]) + frac,
            "peak_value": float(vals[k]),
            "abs_peak": float(abs(vals[k])),
            "profile": vals, "lag_axis": lags}


# ----------------------------------------------------------------------
# 3. GCC-PHAT
# ----------------------------------------------------------------------

def gcc_phat(a: np.ndarray, b: np.ndarray, max_lag: int, fs: int = 48000,
             gamma: float = 1.0, band: tuple | None = None):
    """Generalised cross-correlation with phase transform.

    gamma=1.0 -> classic hard PHAT whitening (divide by |R|). Measured to be
    fragile on low-frequency-dominant material. gamma<1 applies soft
    weighting |R|^(gamma-1); gamma=0 reduces to plain cross-spectrum.
    `band` optionally restricts whitening to a frequency range (Hz tuple);
    outside it the weighting falls back to plain R."""
    a = _prep(a)
    b = _prep(b)
    nfft = 1 << int(np.ceil(np.log2(len(a) + len(b) - 1)))
    A = np.fft.rfft(a, nfft)
    B = np.fft.rfft(b, nfft)
    R = A * np.conj(B)
    magR = np.abs(R) + EPS
    R_w = R * magR ** (-gamma)
    if band is not None:
        f = np.fft.rfftfreq(nfft, d=1.0 / fs)
        outside = ((f < band[0]) | (f > band[1]))
        R_w[outside] = R[outside]
    cc = np.fft.irfft(R_w, nfft)
    lags = np.arange(-(len(b) - 1), len(a))          # scipy-style j axis
    idx = np.where(lags >= 0, lags, nfft + lags)
    vals = cc[idx]
    lag_axis = -lags
    order = np.argsort(lag_axis)
    lag_axis, vals = _slice_lags(lag_axis[order], vals[order], max_lag)
    lags = lag_axis
    k = int(np.argmax(np.abs(vals)))
    frac = _parabolic(vals, k)
    sidelobe = np.median(np.abs(vals)) + EPS
    return {"offset_samples": float(lags[k]) + frac,
            "peak_value": float(vals[k]),
            "abs_peak": float(abs(vals[k])),
            "prominence": float(abs(vals[k]) / sidelobe),
            "ambiguity_ratio": ambiguity_ratio(vals, lags),
            "profile": vals, "lag_axis": lags}


# ----------------------------------------------------------------------
# 3b. engine default GCC variant (soft whitening)
# ----------------------------------------------------------------------
# Measured on the corpus: hard PHAT (gamma=1) fails on advanced delays of
# LF-dominant material and inside narrow bands; plain cross-spectrum
# (gamma=0) is robust but lower-resolution on broadband clicks. gamma=0.35
# is the compromise validated in the bake-off.

def gcc_soft(a: np.ndarray, b: np.ndarray, max_lag: int, fs: int = 48000):
    return gcc_phat(a, b, max_lag, fs, gamma=0.35)


# ----------------------------------------------------------------------
# 4. polarity decision — sign of the signed correlation peak
# ----------------------------------------------------------------------
# Any correlator satisfies corr(a,-b) == -corr(a,b); comparing separate
# runs is vacuous. The signed peak IS the polarity statistic.

def polarity_decision(a: np.ndarray, b: np.ndarray, max_lag: int,
                      fn=None, fs: int = 48000):
    fn = fn or xcorr_plain
    r = fn(a, b, max_lag, fs) if fn is gcc_phat else fn(a, b, max_lag)
    pol = 1 if r["peak_value"] >= 0 else -1
    return {"polarity": pol,
            "margin": float(r["abs_peak"]),
            "offset_samples": r["offset_samples"],
            "abs_peak": r["abs_peak"],
            "peak_value_signed": r["peak_value"]}


# ----------------------------------------------------------------------
# 5. frequency-domain phase slope (weighted LS on unwrapped cross-phase)
# ----------------------------------------------------------------------

def _cross_spectrum(a, b, fs, smooth_bins=7, floor_db=-70.0):
    """Frequency-smoothed full-length cross-spectrum + coherence.

    Time-segmented Welch averaging is inappropriate for transient material
    (silent segments poison the averages); smoothing across frequency over
    the full-length FFT products is transient-appropriate and consistent
    with the GCC estimators. Bins below `floor_db` relative to peak energy
    are flagged via the returned mask (their smoothed coherence saturates
    toward meaningless values in spectral nulls).
    """
    nfft = 1 << int(np.ceil(np.log2(len(a))))
    # Hann window: without it, rectangular leakage (-13 dB first sidelobe)
    # makes different-frequency tones appear coherent (measured: octave-tone
    # pair scored coherence 1.0 and PHAT prominence >400)
    w = np.hanning(len(a))
    A = np.fft.rfft(_prep(a) * w, nfft)
    B = np.fft.rfft(_prep(b) * w, nfft)
    f = np.fft.rfftfreq(nfft, d=1.0 / fs)
    R = A * np.conj(B)
    kern = np.hanning(smooth_bins + 2)[1:-1]
    kern /= kern.sum()

    def sm(x):
        return np.convolve(x, kern, mode="same")

    Sxy = sm(R)
    Sxx = np.maximum(sm(np.abs(A) ** 2), EPS)
    Syy = np.maximum(sm(np.abs(B) ** 2), EPS)
    coh = np.abs(Sxy) ** 2 / (Sxx * Syy)
    floor = 10 ** (floor_db / 10.0) * max(Sxx.max(), Syy.max())
    valid = (Sxx > floor) | (Syy > floor)
    return f, R, coh, valid


def spectral_overlap(a, b, fs, rel_thr_db=-20.0):
    """Directional spectral overlap fraction (0..1).

    Fraction of each layer's active spectrum that the OTHER layer also
    covers. Low values mean harmonically-related-but-not-alignable pairs
    (e.g. octave tones) that nonetheless produce sharp whitened
    correlation structure; such pairs must abstain rather than suggest.
    """
    _, _, _, valid = _cross_spectrum(a, b, fs)
    nfft = 1 << int(np.ceil(np.log2(len(a))))
    w = np.hanning(len(a))
    A = np.fft.rfft(_prep(a) * w, nfft)
    B = np.fft.rfft(_prep(b) * w, nfft)
    Sxx = np.convolve(np.abs(A) ** 2,
                      np.hanning(9) / np.hanning(9).sum(), mode="same")
    Syy = np.convolve(np.abs(B) ** 2,
                      np.hanning(9) / np.hanning(9).sum(), mode="same")
    thrA = (10 ** (rel_thr_db / 10.0)) * Sxx.max() + EPS
    thrB = (10 ** (rel_thr_db / 10.0)) * Syy.max() + EPS
    actA = Sxx > thrA
    actB = Syy > thrB

    def dir_frac(self_e, other_e, mask):
        """fraction of self energy (in its active bins) covered by other"""
        tot = float(np.sum(self_e[mask]))
        if tot <= 0:
            return 0.0
        return float(np.sum(np.minimum(self_e, other_e)[mask]) / tot)

    oAB = dir_frac(Sxx, Syy, actA)   # how much of A's spectrum B shares
    oBA = dir_frac(Syy, Sxx, actB)   # how much of B's spectrum A shares
    return float(max(oAB, oBA))


def _folded_delay_median(ff, phi, w, fs, nfft):
    T = nfft / fs
    tau_bin = phi / (2 * np.pi * ff)
    tau_bin = (tau_bin + T / 2) % T - T / 2          # fold into (-T/2, T/2]
    order = np.argsort(tau_bin)
    cw = np.cumsum(w[order])
    cw /= cw[-1] + EPS
    k = int(np.searchsorted(cw, 0.5))
    return float(tau_bin[order[min(k, len(order) - 1)]])


def phase_slope_offset(a, b, fs, f_lo=30.0, f_hi=None, coh_weight=True,
                       nperseg=None, min_coh=0.10):
    """Folded per-bin delay estimates + coherence-weighted median.

    Avoids phase unwrapping entirely: each bin's delay is folded into
    (-T/2, T/2] where T = nfft/fs is the estimator ambiguity range.
    Robust to the unwrap failures measured for naive LS fitting.
    """
    f_hi = f_hi or fs * 0.4
    nfft = 1 << int(np.ceil(np.log2(len(a))))
    f, R, coh, valid = _cross_spectrum(a, b, fs)
    sel = (f >= f_lo) & (f <= min(f_hi, fs * 0.45)) & (coh > min_coh) & valid
    if int(sel.sum()) < 8:
        return {"offset_samples": 0.0, "confidence": 0.0,
                "coherence_mean": float(coh.mean()), "n_bins": int(sel.sum())}
    ff, phi, cc = f[sel], np.angle(R[sel]), coh[sel]
    # energy weighting: phase noise scales with 1/|R|, and smoothed
    # coherence saturates near 1 across valid bins, so |R|^2 is the
    # statistically meaningful weight (measured: coh^2 weighting biases
    # the folded median toward 0 on transient material).
    w = np.abs(R[sel]) ** 2 if coh_weight else np.ones_like(ff)
    tau = _folded_delay_median(ff, phi, w, fs, nfft)
    return {"offset_samples": tau * fs,
            "confidence": float(np.mean(cc)),
            "coherence_mean": float(coh[valid & (f >= f_lo) &
                                        (f <= min(f_hi, fs * 0.45))].mean()),
            "n_bins": int(sel.sum()),
            "ambiguity_range_samples": nfft,
            "freqs": ff, "phase": phi, "coherence_band": cc}


def phase_slope_ls_offset(a, b, fs, f_lo=30.0, f_hi=None, nperseg=None):
    """Classic unwrap+weighted-LS slope fit — kept as bake-off comparator
    (expected fragile when coherent bins are sparse)."""
    f_hi = f_hi or fs * 0.4
    f, R, coh, valid = _cross_spectrum(a, b, fs)
    sel0 = (f >= f_lo) & (f <= min(f_hi, fs * 0.45)) & (coh > 0.05) & valid
    if int(sel0.sum()) < 8:
        return {"offset_samples": 0.0, "confidence": 0.0}
    phi = np.unwrap(np.angle(R[sel0]))
    ff = f[sel0]
    w = coh[sel0]
    tau = np.sum(w * ff * phi) / (np.sum(w * ff * ff) + EPS)
    return {"offset_samples": float(tau * fs),
            "confidence": float(np.mean(coh[sel0]))}


def group_delay_offset(a, b, fs, f_lo=30.0, f_hi=None, nperseg=None,
                       min_coh=0.20):
    """Group-delay estimate: folded weighted median of per-bin dφ/dω.

    Originally used the longest contiguous coherent run + unwrap; after
    Hann windowing of the spectrum estimator that run became too short
    for reliable gradients on tonal material. Now computes the spectral
    gradient over the whole grid, folds per-bin delays into ±T/2 and takes
    the |R|-weighted median — same family as phase_slope_offset, sensitive
    to local slope rather than absolute phase.
    """
    f_hi = f_hi or fs * 0.4
    nfft = 1 << int(np.ceil(np.log2(len(a))))
    f, R, coh, valid = _cross_spectrum(a, b, fs)
    sel = (f >= f_lo) & (f <= min(f_hi, fs * 0.45)) & (coh > min_coh) & valid
    if int(sel.sum()) < 8:
        return {"offset_samples": 0.0, "confidence": 0.0}
    phi_full = np.unwrap(np.angle(R))          # smooth across full grid
    dphi = np.gradient(phi_full, 2 * np.pi * f)
    ff, dd, cc = f[sel], dphi[sel], coh[sel]
    T = nfft / fs
    tau_bin = (dd + T / 2) % T - T / 2
    wgt = np.abs(R[sel]) ** 2
    order = np.argsort(tau_bin)
    cw = np.cumsum(wgt[order])
    cw /= cw[-1] + EPS
    k = int(np.searchsorted(cw, 0.5))
    tau = float(tau_bin[order[min(k, len(order) - 1)]])
    return {"offset_samples": tau * fs,
            "confidence": float(np.mean(cc)),
            "n_bins": int(sel.sum())}


# ----------------------------------------------------------------------
# 7. magnitude-squared coherence summary
# ----------------------------------------------------------------------

def coherence_summary(a, b, fs, bands=((100, 8000),), min_coh=0.0):
    out = {}
    f, _, coh, valid = _cross_spectrum(a, b, fs)
    for lo, hi in bands:
        sel = (f >= lo) & (f <= hi) & (coh > min_coh)
        sel_valid = sel & valid
        use = sel_valid if sel_valid.sum() >= 8 else sel
        out[f"{lo}-{hi}"] = float(coh[use].mean()) if bool(use.any()) else 0.0
    out["full"] = float(coh.mean())
    return out


def relationship_coherence(a, b, fs,
                           bands=((20, 60), (60, 250), (250, 2000),
                                  (2000, 8000))):
    """Energy-weighted mean coherence across active bands.

    Fixed-band averages under-weight pairs whose interaction lives
    outside the chosen window (measured: layered-kick pairs scored 0.3
    because their shared 40-80 Hz content sat below a 60 Hz cut).
    Weighting each band by the pair's actual energy concentrates the
    statistic where the layers can actually interact.
    """
    nfft = 1 << int(np.ceil(np.log2(len(a))))
    w = np.hanning(len(a))
    A = np.fft.rfft(_prep(a) * w, nfft)
    B = np.fft.rfft(_prep(b) * w, nfft)
    f, _, coh, valid = _cross_spectrum(a, b, fs)
    E = np.abs(A) ** 2 + np.abs(B) ** 2
    num, den = 0.0, 0.0
    for lo, hi in bands:
        sel = (f >= lo) & (f <= hi) & valid
        if not sel.any():
            continue
        e_band = float(np.sum(E[sel]))
        if e_band <= 0:
            continue
        num += float(np.mean(coh[sel])) * e_band
        den += e_band
    return float(num / den) if den > 0 else 0.0


# ----------------------------------------------------------------------
# 8. bandwise analysis
# ----------------------------------------------------------------------

DEFAULT_BANDS = [
    ("sub", 20, 60),
    ("bass", 60, 250),
    ("low_mid", 250, 500),
    ("mid", 500, 2000),
    ("high_mid", 2000, 6000),
    ("high", 6000, 16000),
]


def band_filter(x, fs, lo, hi):
    nyq = fs / 2
    hi = min(hi, nyq * 0.98)
    lo = min(lo, nyq * 0.9)
    if lo <= 20:
        sos = sps.butter(4, hi, btype="low", fs=fs, output="sos")
    elif hi >= nyq:
        sos = sps.butter(4, lo, btype="high", fs=fs, output="sos")
    else:
        sos = sps.butter(4, [lo, hi], btype="band", fs=fs, output="sos")
    return sps.sosfiltfilt(sos, x)


def bandwise_analysis(a, b, fs, max_lag, bands=None):
    bands = bands or DEFAULT_BANDS
    out = {}
    for name, lo, hi in bands:
        fa_raw, fb_raw = _prep(a), _prep(b)
        # Tukey taper kills filtfilt edge transients that otherwise create
        # spurious zero-lag correlation (identical taper on both preserves
        # relative timing).
        taper = sps.windows.tukey(len(fa_raw), alpha=0.08)
        fa = band_filter(fa_raw * taper, fs, lo, hi)
        fb = band_filter(fb_raw * taper, fs, lo, hi)
        ea, eb = float(np.mean(fa ** 2)), float(np.mean(fb ** 2))
        ref = max(ea, eb)
        if ref < 1e-10:
            out[name] = {"active": False}
            continue
        g = gcc_phat(fa, fb, max_lag, fs, gamma=0.0)
        cs = coherence_summary(fa, fb, fs, bands=((lo, min(hi, fs * 0.45)),))
        e_sum = float(np.mean((fa + fb) ** 2))
        out[name] = {
            "active": True,
            "level_db": float(10 * np.log10(ref + EPS)),
            "offset_samples": g["offset_samples"],
            "abs_peak": g["abs_peak"],
            "prominence": g.get("prominence", 0.0),
            "coherence": cs.get(f"{lo}-{min(hi, int(fs * 0.45))}", 0.0),
            "interaction_db": float(
                10 * np.log10((e_sum + EPS) / (ea + eb + EPS))),
        }
    return out


# ----------------------------------------------------------------------
# 9. transient/onset alignment
# ----------------------------------------------------------------------

def onset_alignment(a, b, fs, max_ms=30.0, win_ms=5.0, hop_ms=1.0):
    win = max(4, int(win_ms * fs / 1000))
    hop = max(1, int(hop_ms * fs / 1000))

    def env(x):
        e = np.convolve(_prep(x) ** 2, np.ones(win) / win, mode="same")
        return np.sqrt(e)[::hop]

    ea, eb = env(a), env(b)
    nfft = 1 << int(np.ceil(np.log2(len(ea) + len(eb) - 1)))
    cc = np.fft.irfft(np.fft.rfft(ea, nfft) * np.conj(np.fft.rfft(eb, nfft)),
                      nfft)
    max_lag_env = max(1, int(max_ms * fs / 1000 / hop))
    lags_idx = np.concatenate([np.arange(0, max_lag_env + 1),
                               np.arange(-max_lag_env, 0)])
    idx = np.where(lags_idx >= 0, lags_idx, nfft + lags_idx)
    vals = cc[idx]
    lag_vals = -lags_idx * hop          # positive == B lags A
    order = np.argsort(lag_vals)
    lag_vals, vals = lag_vals[order], vals[order]
    k = int(np.argmax(vals))
    frac = _parabolic(vals, k) * hop

    def first_onset(e):
        thr = 0.05 * e.max() + EPS
        idxo = np.where(e > thr)[0]
        return int(idxo[0]) * hop if len(idxo) else None

    oa, ob = first_onset(ea), first_onset(eb)
    denom = np.linalg.norm(ea) * np.linalg.norm(eb) + EPS
    return {"offset_samples": float(lag_vals[k]) + frac,
            "onset_a": oa, "onset_b": ob,
            "onset_diff": (ob - oa) if (oa is not None and ob is not None)
                          else None,
            "envelope_corr_peak": float(cc[idx][k] / denom)}


# ----------------------------------------------------------------------
# 10. spectral-flux onset detector
# ----------------------------------------------------------------------

def spectral_flux_onsets(x, fs, n_fft=1024, hop=128, delta_ratio=0.15):
    x = _prep(x)
    frames = max(1, (len(x) - n_fft) // hop)
    if frames < 4:
        return np.array([], dtype=int)
    w = np.hanning(n_fft)
    S = np.abs(np.array([np.fft.rfft(x[i * hop:i * hop + n_fft] * w)
                         for i in range(frames)]))
    flux = np.maximum(0.0, np.diff(S, axis=0)).sum(axis=1)
    thr = np.median(flux) + delta_ratio * (np.percentile(flux, 90) + EPS)
    peaks = []
    for i in range(1, len(flux) - 1):
        if flux[i] > thr and flux[i] >= flux[i - 1] and flux[i] >= flux[i + 1]:
            peaks.append(i)
    return np.array(peaks, dtype=int) * hop + n_fft // 2
